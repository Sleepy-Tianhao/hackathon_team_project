"""Validate your own dataset before wiring it into the API.

Bring-your-own-data in one command. The CSV is read through exactly the same code
path the running API uses (backend.template_config.dataset_frame), so a green
report means the service will see the same thing - including the same handling of
missing values and non-numeric targets.

    python -m backend.check_data                                  # check the active template
    python -m backend.check_data --template templates/retail-sales.json
    python -m backend.check_data --csv my.csv --target yield --field crop --field soil
    python -m backend.check_data --sample data/samples/my.csv     # write a starter CSV
    python -m backend.check_data --csv my.csv --target yield --field crop --write-template my.json
    python -m backend.check_data --csv my.csv --target yield --field crop --check-api

Exit code 0 = ready to serve, 1 = at least one ERROR.

This tool adds nothing to the HTTP surface: no new endpoint, no changed response.
It only reports on data that /api/config and /analyze would already consume.
"""
from __future__ import annotations

import argparse
import json
import os
import random
from pathlib import Path
from typing import Any

import pandas as pd

from . import template_config
from .database import BASE_DIR

ERROR, WARN, INFO, GOOD = "ERROR", "WARN", "INFO", "OK"

# A deliberately different domain from the bundled food/sales examples, so the
# sample proves the template machinery is not tied to one problem statement.
SAMPLE_DRINKS = {"Latte": 95.0, "Americano": 70.0, "Matcha": 45.0, "Cold Brew": 60.0, "Cocoa": 40.0}
SAMPLE_WEATHER = {"Sunny": 1.08, "Cloudy": 1.00, "Rain": 0.86, "Hot": 0.95}
SAMPLE_TERM = {"Term": 1.00, "Exam Week": 1.22, "Vacation": 0.35}
SAMPLE_WEEKDAY = {0: 1.10, 1: 1.06, 2: 1.02, 3: 1.00, 4: 0.94, 5: 0.55, 6: 0.45}


class Report:
    """Collects findings and prints them as they happen."""

    def __init__(self, quiet: bool = False) -> None:
        self.quiet = quiet
        self.items: list[tuple[str, str]] = []

    def add(self, level: str, message: str) -> None:
        self.items.append((level, message))
        if self.quiet and level in (INFO, GOOD):
            return
        print(f"  [{level:<5}] {message}")

    def error(self, message: str) -> None:
        self.add(ERROR, message)

    def warn(self, message: str) -> None:
        self.add(WARN, message)

    def info(self, message: str) -> None:
        self.add(INFO, message)

    def good(self, message: str) -> None:
        self.add(GOOD, message)

    @property
    def errors(self) -> list[str]:
        return [message for level, message in self.items if level == ERROR]

    @property
    def warnings(self) -> list[str]:
        return [message for level, message in self.items if level == WARN]


# --------------------------------------------------------------------------- #
# starter data
# --------------------------------------------------------------------------- #
def write_sample(path: Path, days: int = 200, seed: int = 11) -> int:
    """Write a small, well-formed example: date column + 3 dimensions + numeric target."""
    rng = random.Random(seed)
    start = pd.Timestamp("2025-01-06")          # a Monday, so weekday effects are visible
    rows: list[dict[str, Any]] = []

    for offset in range(days):
        day = start + pd.Timedelta(days=offset)
        weather = rng.choices(list(SAMPLE_WEATHER), weights=[34, 31, 24, 11])[0]
        phase = rng.choices(list(SAMPLE_TERM), weights=[80, 12, 8])[0]
        for drink, base in SAMPLE_DRINKS.items():
            expected = (base * SAMPLE_WEATHER[weather] * SAMPLE_TERM[phase]
                        * SAMPLE_WEEKDAY[day.dayofweek])
            cups = max(1, int(round(expected * rng.lognormvariate(0.0, 0.10))))
            rows.append({
                "date": day.strftime("%Y-%m-%d"),
                "drink": drink,
                "weekday": day.day_name(),
                "weather": weather,
                "term_phase": phase,
                "cups": cups,
            })

    frame = pd.DataFrame(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8-sig")
    return len(frame)


# --------------------------------------------------------------------------- #
# checks
# --------------------------------------------------------------------------- #
def check_dataset(template: dict, report: Report) -> pd.DataFrame | None:
    dataset = template["dataset"]
    path = template_config.dataset_path(template)
    origin = " (来自 DATASET_FILE)" if os.getenv("DATASET_FILE") else ""
    report.info(f"数据文件       {path}{origin}")

    if not path.is_file():
        report.error(f"找不到文件：{path}")
        return None
    if path.stat().st_size == 0:
        report.error("文件是空的")
        return None

    try:
        raw = pd.read_csv(path, encoding="utf-8-sig", keep_default_na=False, na_values=[""])
    except UnicodeDecodeError:
        report.error("不是 UTF-8 编码的 CSV（Excel 另存为 CSV UTF-8）")
        return None
    except Exception as exc:
        report.error(f"CSV 解析失败：{type(exc).__name__}: {exc}")
        return None

    report.info(f"列             {', '.join(map(str, raw.columns))}")

    target = dataset["target"]
    if target not in raw.columns:
        report.error(f"dataset.target = '{target}' 不在 CSV 里；可用列：{', '.join(map(str, raw.columns))}")
        return None

    numeric = pd.to_numeric(raw[target], errors="coerce")
    invalid = int(numeric.isna().sum())
    if invalid:
        samples = raw.loc[numeric.isna(), target].head(3).tolist()
        report.error(f"目标列 '{target}' 有 {invalid} 行不是数字，这些行会被静默丢弃；例如 {samples}")
    else:
        report.good(f"目标列 '{target}' 全部可转成数字（{len(raw):,} 行）")

    try:
        frame = template_config.dataset_frame(template)
    except template_config.TemplateError as exc:
        report.error(str(exc))
        return None

    dropped = len(raw) - len(frame)
    if dropped:
        report.warn(f"读取后丢掉 {dropped} 行（目标列为空或非数值）")
    if frame.empty:
        report.error("清理后没有可用数据行")
        return None

    rows = len(frame)
    if rows < 30:
        report.error(f"只有 {rows} 行：本地统计插件基本无法工作，建议 >= 300")
    elif rows < 300:
        report.warn(f"{rows} 行偏少，建议 >= 300 行")
    else:
        report.good(f"行数充足（{rows:,}）")

    _check_date(frame, dataset, report)
    _check_fields(frame, template, report)
    _check_unused_columns(frame, template, report)
    _check_baseline_filter(frame, template, report)
    return frame


def _check_unused_columns(frame: pd.DataFrame, template: dict, report: Report) -> None:
    """Columns nobody reads are usually dimensions you forgot to expose.

    Only meaningful for the local statistics plugin: the ML plugin reads several
    columns (price, discount, ...) implicitly, so it would be a false alarm there.
    """
    plugin = (os.getenv("MODEL_BACKEND") or template["model"]["plugin"]).strip()
    if plugin != "group-baseline":
        return

    dataset = template["dataset"]
    used = {dataset.get("date_column"), dataset.get("target")}
    used |= {field.get("column") for field in template["fields"] if field.get("column")}
    unused = [column for column in frame.columns if column not in used]
    if unused:
        listed = ", ".join(map(str, unused))
        report.info(f"未使用的列     {listed}")
        report.warn(f"  这些列没有作为字段参与预测；如果它们是有效维度，"
                    f"在 template.json 的 fields 里加一项通常能明显提升精度")


def _check_date(frame: pd.DataFrame, dataset: dict, report: Report) -> None:
    date_column = dataset.get("date_column")
    if not date_column:
        report.warn("没有配置 dataset.date_column —— 无法回测，也看不到时间范围")
        return
    if date_column not in frame.columns:
        report.error(f"dataset.date_column = '{date_column}' 不在 CSV 里")
        return

    stamps = pd.to_datetime(frame[date_column], errors="coerce")
    unparsed = int(stamps.isna().sum())
    if unparsed:
        report.error(f"日期列 '{date_column}' 有 {unparsed} 行无法解析（建议 YYYY-MM-DD）")
        return

    distinct = int(stamps.dt.normalize().nunique())
    span = int((stamps.max() - stamps.min()).days) + 1
    report.info(f"日期范围       {stamps.min().date()} ~ {stamps.max().date()}（{span} 天 / {distinct} 个日期）")
    if distinct < 20:
        report.warn("不同日期少于 20 天，回测结果不可靠")
    else:
        report.good(f"日期覆盖 {distinct} 天，可以回测")


def _check_fields(frame: pd.DataFrame, template: dict, report: Report) -> None:
    min_rows = int((template["model"].get("options") or {}).get("effect_min_rows", 5))
    dataset_fields = 0

    for field in template["fields"]:
        column = field.get("column")
        if not column:
            report.info(f"字段 {field['name']:<12} source={field['source']:<7} 自由输入，本地统计插件忽略它")
            continue
        if column not in frame.columns:
            report.error(f"字段 '{field['name']}' 指向的列 '{column}' 不存在")
            continue

        dataset_fields += 1
        counts = frame[column].value_counts()
        report.info(f"字段 {field['name']:<12} 列={column:<12} 取值={len(counts):<4} "
                    f"最少样本={int(counts.min()):<4} 最多样本={int(counts.max())}")
        thin = counts[counts < min_rows]
        if len(thin):
            listed = ", ".join(map(str, thin.index[:6]))
            report.warn(f"  {len(thin)} 个取值样本 < {min_rows}，这些因子会被忽略：{listed}")

    if dataset_fields == 0:
        report.warn("没有任何 source=dataset 的字段：模型没有维度可用，只会输出恒定基准值")


def _check_baseline_filter(frame: pd.DataFrame, template: dict, report: Report) -> None:
    options = template["model"].get("options") or {}
    baseline_filter = options.get("baseline_filter") or {}
    if not baseline_filter:
        return

    scope = frame
    usable = True
    for column, allowed in baseline_filter.items():
        if column not in frame.columns:
            report.error(f"baseline_filter 引用了不存在的列 '{column}'")
            usable = False
            continue
        present = set(frame[column].unique().tolist())
        missing = [value for value in allowed if value not in present]
        if missing:
            report.error(f"baseline_filter['{column}'] 里这些取值在数据中不存在：{missing}")
            usable = False
        scope = scope[scope[column].isin(allowed)]

    if not usable:
        return
    if scope.empty:
        report.error("baseline_filter 过滤后没有任何行，基准值无法计算")
        return
    label = options.get("baseline_label") or "基准口径"
    report.info(f"基准口径       {label}：过滤后 {len(scope):,} 行作为 正常水平")


def check_backtest(template: dict, frame: pd.DataFrame, report: Report, days: int) -> None:
    if days <= 0:
        return

    plugin = (os.getenv("MODEL_BACKEND") or template["model"]["plugin"]).strip()
    if plugin != "group-baseline":
        report.info(f"回测           插件为 {plugin}，不提供留一天回测（用 /api/predict 看验证集指标）")
        return

    from . import model_api

    try:
        result = model_api.backtest_group_baseline(template, frame, days=days)
    except Exception as exc:
        report.warn(f"回测无法执行：{type(exc).__name__}: {exc}")
        return
    if not result:
        report.warn("回测跳过：需要有效的日期列和至少一个维度列")
        return

    report.info(f"回测           {result['days']} 天 / {result['samples']} 个样本")
    report.info(f"  MAPE {result['mape']:.2%}   准确率 {result['accuracy']:.1%}   "
                f"平均绝对误差 {result['mae']:.2f}")
    report.info(f"  参照系 {result['naive_mae']:.2f}（{result.get('naive_label', 'naive')}）")

    improvement = float(result.get("mape_improvement") or 0.0)
    if improvement <= 0.05:
        report.warn(f"  相对参照系只提升 {improvement:.1%}：检查维度列是否真的能区分需求")
    else:
        report.good(f"  相对参照系误差降低 {improvement:.1%}")

    mape = float(result.get("mape") or 0.0)
    if mape >= 0.25:
        report.warn(f"  MAPE {mape:.1%} 偏高：通常说明还有重要维度没做成字段"
                    f"（例如 weekday、天气、节假日），或者目标本身噪声很大")
    elif mape >= 0.15:
        report.info(f"  MAPE {mape:.1%} 中等；补上更多维度列可以更好")
    else:
        report.good(f"  MAPE {mape:.1%} 表现良好")


def check_api(template: dict, report: Report) -> None:
    """Prove the unchanged API contract already serves this data."""
    from . import service

    temp = BASE_DIR / ".check_data.template.json"
    temp.write_text(json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8")
    saved = os.environ.get("TEMPLATE_FILE")
    os.environ["TEMPLATE_FILE"] = temp.name
    template_config.clear_cache()

    try:
        config = service.get_config()
        fields = config["template"]["fields"]
        report.good(f"GET  /api/config   OK   id={config['template']['id']}  rows={config['dataset']['rows']}  "
                    f"fields={[field['name'] for field in fields]}")

        payload: dict[str, Any] = {}
        for field in fields:
            values = config["options"].get(field["name"]) or []
            default = field.get("default")
            payload[field["name"]] = default if default is not None else (values[0] if values else "")

        result = service.analyze(payload)
        report.good(f"POST /analyze      OK   {json.dumps(payload, ensure_ascii=False)}")
        report.info(f"                   -> prediction={result['prediction']}  average={result['average']}  "
                    f"change={result['change_percent']}%  confidence={result['confidence']}%")
        if not result.get("explanation"):
            report.warn("explanation 是空的，前端会显示空段落")
    except Exception as exc:
        report.error(f"API 预演失败（这份数据还不能被现有接口直接使用）：{type(exc).__name__}: {exc}")
    finally:
        template_config.clear_cache()
        if saved is None:
            os.environ.pop("TEMPLATE_FILE", None)
        else:
            os.environ["TEMPLATE_FILE"] = saved
        temp.unlink(missing_ok=True)


# --------------------------------------------------------------------------- #
# template construction / output
# --------------------------------------------------------------------------- #
def build_template(args: argparse.Namespace) -> dict:
    if not args.csv:
        path = Path(args.template) if args.template else template_config.template_path()
        if not path.is_absolute():
            path = BASE_DIR / path
        os.environ["TEMPLATE_FILE"] = str(path)
        template_config.clear_cache()
        return template_config.load_template()

    if not args.target:
        raise SystemExit("--csv 必须同时指定 --target（要预测的数值列）")

    fields: list[dict] = []
    for name in (args.field or []):
        fields.append({"name": name, "label": name, "type": "select",
                       "source": "dataset", "column": name, "required": True})
    fields.append({"name": "notes", "label": "Additional Information", "type": "text",
                   "source": "input", "required": False, "placeholder": "Enter extra context..."})

    options: dict[str, Any] = {
        "effect_min_rows": args.effect_min_rows,
        "fallback_plugin": "group-baseline",
    }
    if args.baseline_filter:
        parsed: dict[str, list[str]] = {}
        for item in args.baseline_filter:
            column, _, values = item.partition("=")
            parsed[column.strip()] = [value.strip() for value in values.split(",") if value.strip()]
        options["baseline_filter"] = parsed
        if args.baseline_label:
            options["baseline_label"] = args.baseline_label

    return {
        "id": "custom-data",
        "app": {"brand": "CUSTOM", "title": "CUSTOM DATA CHECK", "subtitle": "checked by check_data.py"},
        "dataset": {
            "path": args.csv,
            "date_column": args.date_column,
            "target": args.target,
            "unit": args.unit,
            "target_label": args.target,
        },
        "model": {"plugin": args.plugin, "options": options},
        "fields": fields,
        "output": {
            "locale": "zh", "headline": "Prediction", "subheadline": "",
            "unit": args.unit, "decimals": 0, "delta_label": "vs. normal",
            "explanation_title": "AI Explanation", "submit_label": "Predict",
        },
    }


def print_wiring(template: dict) -> None:
    snippet = {
        "dataset": {key: template["dataset"][key]
                    for key in ("path", "date_column", "target", "unit", "target_label")
                    if template["dataset"].get(key) is not None},
        "fields": [],
    }
    for field in template["fields"]:
        entry = {"name": field["name"], "label": field["label"],
                 "type": field["type"], "source": field["source"]}
        if field.get("column"):
            entry["column"] = field["column"]
        if field.get("options"):
            entry["options"] = field["options"]
        entry["required"] = field.get("required", True)
        if field.get("placeholder"):
            entry["placeholder"] = field["placeholder"]
        snippet["fields"].append(entry)

    print()
    print("  把这段贴进 template.json 的 dataset / fields 两段，即可接上这份数据：")
    print()
    for line in json.dumps(snippet, ensure_ascii=False, indent=2).splitlines():
        print("    " + line)


# --------------------------------------------------------------------------- #
# entry point
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m backend.check_data",
        description="Validate a dataset (and its template wiring) before wiring it into the API",
    )
    parser.add_argument("--template", help="template.json to check (default: the active one)")
    parser.add_argument("--csv", help="check this CSV directly, no template needed")
    parser.add_argument("--target", help="numeric column to predict (with --csv)")
    parser.add_argument("--field", action="append", help="dimension column used as a form field (repeatable)")
    parser.add_argument("--date-column", default="date", help="name of the date column (default: date)")
    parser.add_argument("--unit", default="", help="unit shown next to the prediction")
    parser.add_argument("--plugin", default="group-baseline", help="model plugin to check against")
    parser.add_argument("--effect-min-rows", type=int, default=5, help="min rows per value (default 5)")
    parser.add_argument("--baseline-filter", action="append",
                        help="restrict the baseline, e.g. --baseline-filter weekday=Monday,Tuesday")
    parser.add_argument("--baseline-label", default="", help="label for that baseline口径")
    parser.add_argument("--backtest-days", type=int, default=60, help="backtest window (0 disables)")
    parser.add_argument("--check-api", action="store_true",
                        help="also prove GET /api/config and POST /analyze serve this data")
    parser.add_argument("--write-template", help="write a ready-to-use template.json here")
    parser.add_argument("--print-wiring", action="store_true", help="print the template snippet")
    parser.add_argument("--sample", help="write a starter CSV here and exit")
    parser.add_argument("--quiet", action="store_true", help="only show warnings and errors")
    args = parser.parse_args(argv)

    if args.sample:
        path = Path(args.sample)
        count = write_sample(path)
        print(f"已写出示例数据：{path}（{count:,} 行）")
        print("列：date, drink, weather, term_phase, cups")
        print("配套模板：data/samples/coffee_shop.template.json")
        print()
        print("试着跑一遍：")
        print(f"  python -m backend.check_data --csv {path} --target cups "
              f"--field drink --field weather --field term_phase --check-api")
        return 0

    saved = os.environ.get("TEMPLATE_FILE")
    try:
        return _run(args)
    finally:
        # Never leak the template override to the caller: the test suite runs
        # this entry point in-process.
        template_config.clear_cache()
        if saved is None:
            os.environ.pop("TEMPLATE_FILE", None)
        else:
            os.environ["TEMPLATE_FILE"] = saved


def _run(args: argparse.Namespace) -> int:
    try:
        template = build_template(args)
    except template_config.TemplateError as exc:
        print(f"  [ERROR] 模板有问题：{exc}")
        return 1

    if args.write_template:
        out = Path(args.write_template)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(template, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"已写出模板：{out}")

    report = Report(quiet=args.quiet)
    print()
    print("=" * 74)
    print(f"  数据校验  id={template['id']}  plugin={template['model']['plugin']}")
    print("=" * 74)

    frame = check_dataset(template, report)
    if frame is not None:
        check_backtest(template, frame, report, args.backtest_days)
        if args.check_api:
            check_api(template, report)

    if args.print_wiring or args.csv:
        print_wiring(template)

    print()
    print("-" * 74)
    if report.errors:
        print(f"  有 {len(report.errors)} 个错误、{len(report.warnings)} 个警告 —— 先修掉错误")
        for message in report.errors:
            print(f"      · {message}")
        return 1

    print(f"  通过（{len(report.warnings)} 个警告）—— 现有 API 无需任何改动")
    print("    下一步：python -m backend.server   然后用同一套 /api/config 与 /analyze")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
