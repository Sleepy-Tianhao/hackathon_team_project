"""Model plugin interface - the single seam where your own model plugs in.

Three plugins ship with the template:

  group-baseline   local, fully generic, no training. A conditional-mean factor
                   model: predicted = baseline * product(effect of each chosen
                   value), where effect = mean(target | value) / baseline. It
                   works with any CSV and any field set declared in template.json,
                   and - unlike a black box - the sentence it explains is built
                   from the very terms it multiplied, so the explanation is
                   genuinely the model's reasoning.

  sales-forecast   the bundled scikit-learn forecaster (retail demo). Maps the
                   template fields store/category/horizon onto predictor.forecast.

  http             THE INTEGRATION POINT for your own model service. It POSTs the
                   form values to MODEL_API_URL and normalises the answer.

-------------------------------------------------------------------------------
External model API contract (plugin "http")
-------------------------------------------------------------------------------
Request  POST $MODEL_API_URL          Content-Type: application/json
         Authorization: Bearer $MODEL_API_KEY        (only when the key is set)

{
  "template_id": "food-demand",
  "fields": {"menu": "Chicken Rice", "day": "Friday", "weather": "Rain", "event": ""},
  "unit": "portions",
  "context": {"target": "portions", "target_label": "需求份数", "requested_at": "..."}
}

Response 200  (only "value" is required; everything else is optional)
{
  "value": 132,                       // or prediction / predicted / demand / result
  "unit": "portions",
  "baseline": 143,                    // enables the "x% lower than normal" line
  "delta": -0.077,                    // optional; computed from baseline when absent
  "explanation": "Friday demand is historically lower, and rain is expected.",
  "model": "canteen-xgb-v3",
  "evidence": [{"label": "Friday", "effect": -0.11}],
  "meta": {"version": "2026-03-01"}
}

Nested under "data" is also accepted. Any transport error, non-2xx status, or a
response without a numeric value raises ModelError. When MODEL_API_FALLBACK is
not "off" (default "local"), the request silently falls back to the template's
local plugin so a dead API never blocks a demo; set MODEL_API_FALLBACK=off to
surface it as HTTP 502 instead.
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import requests

from . import predictor

VALUE_KEYS = ("value", "prediction", "predicted", "demand", "result")

PHRASES: dict[str, dict[str, str]] = {
    "zh": {
        "factor": "{label} 条件均值 {mean}（{effect}）",
        "summary": "以{baseline_label} {baseline} 为基准，综合预测 {value} {unit}。",
        "no_evidence": "没有找到匹配的历史记录，直接采用{baseline_label} {baseline} {unit}。",
        "higher": "高 {pct}",
        "lower": "低 {pct}",
        "join": "；",
        "factor_end": "。",
        "clamped": "（因子已做上下限截断）",
        "forecast": "{model} 模型（验证集 MAPE {mape}，优于季节朴素基线 {improvement}）。未来 {horizon} 天日均 {value} {unit}，较历史日均{dir}{pct}；峰值日 {peak_date} 预计 {peak_value} {unit}。",
        "flat": "基本持平",
        "delta": "比历史正常水平{dir}{pct}",
    },
    "en": {
        "factor": "{label} averages {mean} ({effect})",
        "summary": "Against {baseline_label} of {baseline}, the combined forecast is {value} {unit}.",
        "no_evidence": "No matching history was found, so {baseline_label} of {baseline} {unit} is used.",
        "higher": "{pct} above",
        "lower": "{pct} below",
        "join": "; ",
        "factor_end": ". ",
        "clamped": " (factors clamped)",
        "forecast": "{model} model (hold-out MAPE {mape}, {improvement} better than the seasonal-naive baseline). Next {horizon} days average {value} {unit} per day, {dir}{pct} versus history; the peak day is {peak_date} at {peak_value} {unit}.",
        "flat": "roughly flat",
        "delta": "{pct} {dir} than normal",
    },
}


class ModelError(Exception):
    """A model could not produce a prediction."""

    def __init__(self, message: str, status: int = 502) -> None:
        super().__init__(message)
        self.status = status


# --------------------------------------------------------------------------- #
# result envelope
# --------------------------------------------------------------------------- #
@dataclass
class PredictionResult:
    """Normalised answer every plugin returns, whatever the underlying model."""

    value: float
    unit: str = ""
    baseline: float | None = None
    delta: float | None = None
    explanation: str = ""
    explanation_source: str = "local"
    model: str = ""
    evidence: list[dict] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    def to_payload(self, template: dict, fields: dict, elapsed_ms: float | None = None) -> dict:
        """Shape the answer for the browser, using the template's output copy."""
        output = template.get("output") or {}
        locale = output.get("locale", "zh")
        decimals = int(output.get("decimals", 0) or 0)

        value = round(float(self.value), decimals)
        baseline = None if self.baseline is None else round(float(self.baseline), decimals)
        delta = self.delta
        if delta is None and self.baseline:
            delta = float(self.value) / float(self.baseline) - 1.0

        direction = "flat"
        if delta is not None and delta > 0.005:
            direction = "up"
        elif delta is not None and delta < -0.005:
            direction = "down"

        meta = dict(self.meta)
        if elapsed_ms is not None:
            meta["elapsed_ms"] = round(float(elapsed_ms), 2)

        return {
            "value": value,
            "formatted": f"{value:,.{decimals}f}",
            "unit": self.unit or output.get("unit", ""),
            "baseline": baseline,
            "delta": None if delta is None else round(float(delta), 4),
            "delta_text": _delta_text(delta, locale),
            "delta_label": output.get("delta_label", ""),
            "direction": direction,
            "headline": output.get("headline", ""),
            "subheadline": output.get("subheadline", ""),
            "explanation": self.explanation,
            "explanation_title": output.get("explanation_title", "AI Explanation"),
            "explanation_source": self.explanation_source,
            "model": self.model or self.__class__.__name__,
            "fields": fields,
            "evidence": self.evidence,
            "meta": meta,
        }


def _pct(value: float) -> str:
    return f"{abs(float(value)) * 100:.0f}%"


def _delta_text(delta: float | None, locale: str) -> str:
    phrases = PHRASES.get(locale, PHRASES["zh"])
    if delta is None:
        return ""
    if abs(delta) < 0.005:
        return phrases["flat"]
    direction = phrases["higher"] if delta > 0 else phrases["lower"]
    if locale == "en":
        direction = "higher" if delta > 0 else "lower"
        return phrases["delta"].format(pct=_pct(delta), dir=direction)
    return phrases["delta"].format(dir="高" if delta > 0 else "低", pct=_pct(delta))


def _effect_text(effect: float, locale: str) -> str:
    phrases = PHRASES.get(locale, PHRASES["zh"])
    key = "higher" if effect >= 0 else "lower"
    return phrases[key].format(pct=_pct(effect))


# --------------------------------------------------------------------------- #
# plugin base
# --------------------------------------------------------------------------- #
class ModelPlugin(ABC):
    """Subclass this, register it in PLUGINS, point template.json at it."""

    name = "abstract"
    requires_network = False

    def __init__(self, template: dict, options: dict | None = None) -> None:
        self.template = template
        self.options = options or {}

    @abstractmethod
    def predict(self, fields: dict[str, Any], frame: pd.DataFrame | None, db: Any = None) -> PredictionResult:
        """Return a PredictionResult for one set of form values."""


# --------------------------------------------------------------------------- #
# plugin: local conditional-mean baseline (generic)
# --------------------------------------------------------------------------- #
class GroupBaselineModel(ModelPlugin):
    """Generic local baseline: baseline x product(per-field conditional effects)."""

    name = "group-baseline"

    def predict(self, fields, frame, db=None) -> PredictionResult:
        if frame is None or frame.empty:
            raise ModelError("dataset is empty", status=500)

        dataset = self.template["dataset"]
        target = dataset["target"]
        unit = dataset.get("unit", "")
        locale = (self.template.get("output") or {}).get("locale", "zh")
        phrases = PHRASES.get(locale, PHRASES["zh"])
        min_rows = int(self.options.get("effect_min_rows", 5))

        # Baseline: global mean, optionally restricted (e.g. weekdays only).
        scope = frame
        baseline_filter = self.options.get("baseline_filter") or {}
        for column, allowed in baseline_filter.items():
            if column in scope.columns:
                scope = scope[scope[column].isin(allowed)]
        if scope.empty:
            scope = frame
        baseline = float(scope[target].mean())
        baseline_label = self.options.get("baseline_label") or ("整体均值" if locale == "zh" else "the overall average")

        evidence: list[dict] = []
        multiplier = 1.0
        for spec in self.template["fields"]:
            column = spec.get("column")
            if not column or column not in frame.columns:
                continue
            value = fields.get(spec["name"])
            if value is None or value == "":
                continue

            subset = frame[frame[column] == value]
            rows = int(len(subset))
            if rows < min_rows:
                evidence.append({"field": spec["name"], "label": spec["label"], "value": value,
                                 "rows": rows, "used": False,
                                 "reason": f"only {rows} historical rows"})
                continue
            mean = float(subset[target].mean())
            ratio = (mean / baseline) if baseline else 1.0
            evidence.append({"field": spec["name"], "label": spec["label"], "value": value,
                             "rows": rows, "used": True, "mean": round(mean, 2),
                             "effect": round(ratio - 1.0, 4)})
            multiplier *= ratio

        clamped = False
        if multiplier > 5.0:
            multiplier, clamped = 5.0, True
        elif multiplier < 0.2:
            multiplier, clamped = 0.2, True

        value = baseline * multiplier
        used = [item for item in evidence if item["used"]]
        used.sort(key=lambda item: abs(item["effect"]), reverse=True)

        if used:
            factors = phrases["join"].join(
                phrases["factor"].format(label=item["value"],
                                         mean=f"{item['mean']:,.0f}",
                                         effect=_effect_text(item["effect"], locale))
                for item in used
            )
            explanation = factors + phrases["factor_end"] + phrases["summary"].format(
                baseline_label=baseline_label,
                baseline=f"{baseline:,.0f}",
                value=f"{value:,.0f}",
                unit=unit,
            )
        else:
            explanation = phrases["no_evidence"].format(
                baseline_label=baseline_label, baseline=f"{baseline:,.0f}", unit=unit)

        if clamped:
            explanation += phrases["clamped"]

        return PredictionResult(
            value=value,
            unit=unit,
            baseline=baseline,
            explanation=explanation,
            explanation_source="local-baseline",
            model=self.name,
            evidence=evidence,
            meta={
                "plugin": self.name,
                "baseline_label": baseline_label,
                "baseline_rows": int(len(scope)),
                "multiplier": round(multiplier, 4),
                "clamped": clamped,
                "locale": locale,
                "note": "条件均值因子模型，非训练模型；每个因子都可在 evidence 中核对",
            },
        )


# --------------------------------------------------------------------------- #
# plugin: bundled ML forecaster (retail demo)
# --------------------------------------------------------------------------- #
class SalesForecastModel(ModelPlugin):
    """Adapts the bundled scikit-learn forecaster to the template contract."""

    name = "sales-forecast"

    def predict(self, fields, frame, db=None) -> PredictionResult:
        if db is None:
            raise ModelError("sales-forecast requires a database session", status=500)

        store = fields.get("store")
        category = fields.get("category")
        horizon = int(float(fields.get("horizon") or 30))
        locale = (self.template.get("output") or {}).get("locale", "zh")
        phrases = PHRASES.get(locale, PHRASES["zh"])
        unit = self.template["dataset"].get("unit", "")

        try:
            forecast = predictor.forecast(db, store=store, category=category, horizon=horizon)
        except ValueError as exc:
            raise ModelError(str(exc), status=400) from exc

        predictor.log_prediction_run(db, forecast, store, category, horizon)

        totals = forecast["totals"]
        metrics = (forecast["model"] or {}).get("revenue") or {}
        peak = forecast.get("peak") or {}

        # Historical daily average for the same scope = the "normal" baseline.
        scope = predictor.get_frame(db)
        if store and "store" in scope.columns:
            scope = scope[scope["store"] == store]
        if category and "category" in scope.columns:
            scope = scope[scope["category"] == category]
        daily = scope.groupby(scope["date"].dt.normalize())["revenue"].sum()
        baseline = float(daily.mean()) if len(daily) else 0.0
        value = float(totals["avg_daily_revenue"])
        delta = (value / baseline - 1.0) if baseline else None

        improvement = metrics.get("improvement_vs_baseline")
        explanation = phrases["forecast"].format(
            model=metrics.get("model", "ML"),
            mape=_pct(metrics.get("mape") or 0.0),
            improvement=("" if improvement is None else _pct(improvement) + (" " if locale == "en" else "")),
            horizon=horizon,
            value=f"{value:,.0f}",
            unit=unit,
            dir=("up " if (delta or 0) > 0 else "down ") if locale == "en" else ("高 " if (delta or 0) > 0 else "低 "),
            pct=_pct(delta or 0.0),
            peak_date=peak.get("date", "-"),
            peak_value=f"{float(peak.get('revenue') or 0):,.0f}",
        )

        return PredictionResult(
            value=value,
            unit=unit,
            baseline=baseline or None,
            delta=delta,
            explanation=explanation,
            explanation_source="ml-forecast",
            model=metrics.get("model", self.name),
            evidence=[{"model": metrics.get("model"), "mape": metrics.get("mape"),
                       "baseline_mape": metrics.get("baseline_mape"),
                       "train_rows": metrics.get("train_rows")}],
            meta={
                "plugin": self.name,
                "horizon_days": horizon,
                "forecast_total": totals.get("revenue"),
                "peak_date": peak.get("date"),
                "peak_revenue": peak.get("revenue"),
                "series_count": forecast.get("series_count"),
                "assumptions": forecast.get("assumptions"),
            },
        )


# --------------------------------------------------------------------------- #
# plugin: external HTTP model API  <- your own service goes here
# --------------------------------------------------------------------------- #
def _first_number(payload: dict, keys) -> float | None:
    for key in keys:
        if key in payload:
            try:
                return float(payload[key])
            except (TypeError, ValueError):
                continue
    return None


class ExternalModelClient(ModelPlugin):
    """Calls your model service. See the contract in this module's docstring."""

    name = "http"
    requires_network = True

    def __init__(self, template: dict, options: dict | None = None) -> None:
        super().__init__(template, options)
        self.url = str(os.getenv("MODEL_API_URL") or self.options.get("url") or "").strip()
        if not self.url:
            raise ModelError("MODEL_API_URL is not set; configure it or use a local plugin", status=500)
        self.api_key = os.getenv("MODEL_API_KEY", "")
        self.timeout = float(os.getenv("MODEL_API_TIMEOUT") or self.options.get("timeout") or 15)

    def predict(self, fields, frame, db=None) -> PredictionResult:
        dataset = self.template["dataset"]
        request_body = {
            "template_id": self.template["id"],
            "fields": fields,
            "unit": dataset.get("unit", ""),
            "context": {
                "target": dataset["target"],
                "target_label": dataset.get("target_label", dataset["target"]),
                "requested_at": datetime.now(timezone.utc).isoformat(),
            },
        }
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            response = requests.post(self.url, json=request_body, headers=headers, timeout=self.timeout)
        except requests.RequestException as exc:
            raise ModelError(f"model API request failed: {exc}") from exc

        if response.status_code >= 400:
            raise ModelError(f"model API returned HTTP {response.status_code}: {response.text[:200]}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise ModelError("model API did not return valid JSON") from exc
        if not isinstance(payload, dict):
            raise ModelError("model API response must be a JSON object")

        body = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        value = _first_number(body, VALUE_KEYS)
        if value is None:
            raise ModelError(f"model API response has no numeric value (looked for {', '.join(VALUE_KEYS)})")

        baseline = _first_number(body, ("baseline", "normal", "average", "expected"))
        delta = _first_number(body, ("delta", "change", "relative_change"))

        return PredictionResult(
            value=value,
            unit=str(body.get("unit") or dataset.get("unit", "")),
            baseline=baseline,
            delta=delta,
            explanation=str(body.get("explanation") or body.get("reason") or ""),
            explanation_source="external-api",
            model=str(body.get("model") or body.get("model_name") or "external-model"),
            evidence=body.get("evidence") if isinstance(body.get("evidence"), list) else [],
            meta={"plugin": self.name, "url": self.url,
                  "external_meta": body.get("meta") if isinstance(body.get("meta"), dict) else {}},
        )


# --------------------------------------------------------------------------- #
# registry
# --------------------------------------------------------------------------- #
PLUGINS: dict[str, type[ModelPlugin]] = {
    GroupBaselineModel.name: GroupBaselineModel,
    SalesForecastModel.name: SalesForecastModel,
    ExternalModelClient.name: ExternalModelClient,
}


def resolve_model(template: dict) -> ModelPlugin:
    """Pick the plugin from MODEL_BACKEND (override) or template.model.plugin."""
    requested = (os.getenv("MODEL_BACKEND") or template["model"]["plugin"]).strip()
    plugin_class = PLUGINS.get(requested)
    if plugin_class is None:
        raise ModelError(
            f"unknown model plugin '{requested}'; available: {', '.join(sorted(PLUGINS))}",
            status=500,
        )
    return plugin_class(template, template["model"].get("options") or {})


def fallback_plugin(template: dict) -> ModelPlugin | None:
    """Local plugin used when an external model API fails (MODEL_API_FALLBACK)."""
    if os.getenv("MODEL_API_FALLBACK", "local").strip().lower() == "off":
        return None
    name = (template["model"].get("options") or {}).get("fallback_plugin", GroupBaselineModel.name)
    plugin_class = PLUGINS.get(name)
    return plugin_class(template, template["model"].get("options") or {}) if plugin_class else None
