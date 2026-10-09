"""AI insight layer for the sales dashboard.

Two tiers:

1. A deterministic rule engine that always runs. It reads the KPI / forecast /
   breakdown context and produces analyst-style insights, so the dashboard is
   fully functional offline (important on a hackathon demo stage).
2. An optional LLM narrative. When OPENAI_API_KEY is set (any OpenAI-compatible
   gateway works via OPENAI_BASE_URL), the context is sent to /chat/completions.
   Any error falls back to a template narrative instead of failing the request.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
import requests

LLM_TIMEOUT = float(os.getenv("OPENAI_TIMEOUT", "25"))

def system_prompt(context: dict) -> str:
    """Derive the analyst role from the metrics actually present in the context,
    instead of hardcoding "retail" - the wording follows the data, not the module."""
    kpis = context.get("kpis") or {}
    labels: list[str] = []
    for key, label in (
        ("revenue", "营收"),
        ("units", "销量"),
        ("orders", "订单量"),
        ("profit", "利润"),
    ):
        if key in kpis:
            labels.append(label)
    subject = "、".join(labels) or "经营指标"
    return (
        f"你是一名数据分析师。请根据给定的数据与已计算出的洞察，围绕「{subject}」"
        "写一段 120-200 字的中文简报：先给结论，再点出最关键的风险或机会，"
        "最后给出一条可执行的建议。不要罗列数字清单，不要编造数据中不存在的信息。"
    )


# --------------------------------------------------------------------------- #
# formatting helpers
# --------------------------------------------------------------------------- #
def _f(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if np.isfinite(out) else default


def money(value: Any) -> str:
    amount = _f(value)
    if abs(amount) >= 1e8:
        return f"{amount / 1e8:.2f} 亿元"
    if abs(amount) >= 1e4:
        return f"{amount / 1e4:.1f} 万元"
    return f"{amount:,.0f} 元"


def units(value: Any) -> str:
    return f"{_f(value):,.0f} 件"


def pct(value: Any, digits: int = 1) -> str:
    return f"{_f(value) * 100:.{digits}f}%"


def _insight(kind: str, severity: str, title: str, detail: str,
             metric: str | None = None, value: Any = None,
             recommendation: str | None = None) -> dict:
    return {
        "kind": kind,
        "severity": severity,
        "title": title,
        "detail": detail,
        "metric": metric,
        "value": value,
        "recommendation": recommendation,
    }


# --------------------------------------------------------------------------- #
# rule engine
# --------------------------------------------------------------------------- #
def rule_insights(context: dict) -> list[dict]:
    """Derive insights from the aggregated context. Pure function, no I/O."""
    out: list[dict] = []
    kpis = context.get("kpis") or {}
    growth = context.get("growth") or {}
    previous = context.get("previous") or {}
    scope = context.get("scope") or {}
    label = scope.get("label") or "当前范围"
    days = int(_f((context.get("range") or {}).get("days"), 0))

    # 1. period-over-period revenue
    g = growth.get("revenue")
    if g is not None:
        g = _f(g)
        severity = "positive" if g >= 0.02 else ("warning" if g <= -0.05 else "info")
        out.append(_insight(
            "growth", severity,
            f"营收环比{'增长' if g >= 0 else '下滑'} {pct(abs(g))}",
            f"{label}最近 {days} 天营收 {money(kpis.get('revenue'))}，"
            f"上一周期为 {money(previous.get('revenue'))}，"
            f"{'增长' if g >= 0 else '下滑'} {pct(abs(g))}；"
            f"销量 {units(kpis.get('units'))}，环比 {'+' if _f(growth.get('units')) >= 0 else ''}"
            f"{pct(_f(growth.get('units')))}。",
            metric="revenue_growth", value=round(g, 4),
            recommendation="维持当前投放节奏并复制高增长门店的打法"
            if g >= 0 else "复盘流量与转化漏斗，优先定位下滑最严重的门店和品类",
        ))

    # 2. promotion effectiveness
    uplift = kpis.get("promo_uplift")
    if uplift is not None:
        u = _f(uplift)
        share = _f(kpis.get("promo_revenue_share"))
        severity = "positive" if u >= 0.10 else ("warning" if u <= 0 else "info")
        out.append(_insight(
            "promotion", severity,
            f"促销日日均营收比平日{'高' if u >= 0 else '低'} {pct(abs(u))}",
            f"促销贡献了 {pct(share)} 的营收，促销日日均 {money(kpis.get('avg_daily_revenue_promo'))}，"
            f"非促销日 {money(kpis.get('avg_daily_revenue_regular'))}。",
            metric="promo_uplift", value=round(u, 4),
            recommendation="促销加权仍在正收益区间，可把折扣集中到高弹性品类"
            if u >= 0.10 else "促销增量有限，建议收窄折扣力度并测试非价格型权益",
        ))

    # 3. weekend effect
    weekend_uplift = kpis.get("weekend_uplift")
    if weekend_uplift is not None:
        w = _f(weekend_uplift)
        out.append(_insight(
            "seasonality",
            "info",
            f"周末日均营收{'高于' if w >= 0 else '低于'}工作日 {pct(abs(w))}",
            f"周末日均 {money(kpis.get('avg_daily_revenue_weekend'))}，"
            f"工作日日均 {money(kpis.get('avg_daily_revenue_weekday'))}，"
            f"排班与库存应围绕这一节奏配置。",
            metric="weekend_uplift", value=round(w, 4),
            recommendation="把主推活动与人力高峰放在周末，并把补货节奏提前到周四"
            if w >= 0 else "工作日流量更高，考虑把营销预算向周中倾斜",
        ))

    # 4. category concentration
    breakdown = context.get("breakdown") or {}
    categories = breakdown.get("category") or []
    if categories:
        top = categories[0]
        share = _f(top.get("share"))
        severity = "warning" if share >= 0.45 else "info"
        out.append(_insight(
            "concentration", severity,
            f"{top.get('name')} 贡献 {pct(share)} 的营收",
            f"最高品类 {top.get('name')}（{money(top.get('revenue'))}）与最低品类 "
            f"{categories[-1].get('name')}（{money(categories[-1].get('revenue'))}）差距明显。",
            metric="top_category_share", value=round(share, 4),
            recommendation="营收过度集中，建议提高腰部品类的曝光与连带销售"
            if share >= 0.45 else "品类结构相对均衡，可继续放大头部品类的引流作用",
        ))

    # 5. momentum: fastest riser and fastest faller
    momentum = context.get("momentum") or []
    if momentum:
        riser = max(momentum, key=lambda item: _f(item.get("change")))
        faller = min(momentum, key=lambda item: _f(item.get("change")))
        if _f(faller.get("change")) < 0:
            out.append(_insight(
                "momentum", "warning",
                f"{faller.get('name')} 近 30 天掉头向下 {pct(abs(_f(faller.get('change'))))}",
                f"{faller.get('name')} 由 {money(faller.get('prior'))} 降至 {money(faller.get('recent'))}；"
                f"同期 {riser.get('name')} 增长 {pct(_f(riser.get('change')))}，是最强增长点。",
                metric="momentum_gap",
                value=round(_f(riser.get("change")) - _f(faller.get("change")), 4),
                recommendation=f"对 {faller.get('name')} 做一次专题诊断，把 {riser.get('name')} 的打法横向复制",
            ))
        else:
            out.append(_insight(
                "momentum", "positive",
                f"全部品类近 30 天均为正增长，{riser.get('name')} 领先",
                f"{riser.get('name')} 环比 {pct(_f(riser.get('change')))}，"
                f"最低的 {faller.get('name')} 也有 {pct(_f(faller.get('change')))}。",
                metric="momentum_leader", value=round(_f(riser.get("change")), 4),
                recommendation="整体向上，重点保证供应链跟得上增长最快的品类",
            ))

    # 6. forecast outlook
    forecast = context.get("forecast")
    if forecast:
        totals = forecast.get("totals") or {}
        horizon = int(_f(forecast.get("horizon"), 0))
        predicted_daily = _f(totals.get("avg_daily_revenue"))
        actual_daily = _f(kpis.get("avg_daily_revenue"))
        if actual_daily > 0:
            delta = predicted_daily / actual_daily - 1.0
            model = (forecast.get("model") or {}).get("revenue") or {}
            severity = "positive" if delta >= 0 else "warning"
            out.append(_insight(
                "forecast", severity,
                f"未来 {horizon} 天预计营收 {money(totals.get('revenue'))}",
                f"日均 {money(predicted_daily)}，较当前历史日均 "
                f"{'高' if delta >= 0 else '低'} {pct(abs(delta))}；模型 {model.get('model')} "
                f"验证集 MAPE {pct(_f(model.get('mape')))}，"
                f"优于季节朴素基线 {pct(_f(model.get('improvement_vs_baseline')))}。",
                metric="forecast_daily_delta", value=round(delta, 4),
                recommendation="按预测上沿备货，并锁定预测峰值日的人力与库存"
                if delta >= 0 else "需求走弱，建议收紧补货节奏、优先清理长库龄库存",
            ))
            peak = forecast.get("peak") or {}
            if peak:
                out.append(_insight(
                    "planning", "info",
                    f"预计峰值日 {peak.get('date')} 单日 {money(peak.get('revenue'))}",
                    f"峰值日约为预测日均的 "
                    f"{(_f(peak.get('revenue')) / max(predicted_daily, 1e-6)):.2f} 倍，"
                    f"需要提前锁定人力和库存。",
                    metric="peak_revenue", value=round(_f(peak.get("revenue")), 2),
                    recommendation="把促销与直播资源对齐峰值日，提前 2 天完成补货",
                ))

    return out


# --------------------------------------------------------------------------- #
# anomaly detection
# --------------------------------------------------------------------------- #
def detect_anomalies(daily: list[dict] | None, window: int = 28,
                     z_threshold: float = 2.5, limit: int = 5) -> list[dict]:
    """Flag days whose revenue deviates from its trailing rolling baseline."""
    if not daily or len(daily) < window + 5:
        return []

    values = np.array([_f(entry.get("revenue")) for entry in daily], dtype=float)
    series = pd.Series(values)
    baseline = series.shift(1).rolling(window, min_periods=max(5, window // 2)).mean()
    spread = series.shift(1).rolling(window, min_periods=max(5, window // 2)).std()
    zscores = (series - baseline) / spread.replace(0.0, np.nan)

    found: list[dict] = []
    for index, entry in enumerate(daily):
        score = zscores.iloc[index]
        if np.isfinite(score) and abs(float(score)) >= z_threshold:
            found.append({
                "date": entry.get("date"),
                "revenue": round(values[index], 2),
                "expected": round(float(baseline.iloc[index]), 2),
                "zscore": round(float(score), 2),
                "direction": "spike" if score > 0 else "drop",
            })
    found.sort(key=lambda item: abs(item["zscore"]), reverse=True)
    return found[:limit]


def anomalies_to_insights(anomalies: list[dict]) -> list[dict]:
    if not anomalies:
        return []
    spikes = [item for item in anomalies if item["direction"] == "spike"]
    drops = [item for item in anomalies if item["direction"] == "drop"]
    parts = []
    if spikes:
        parts.append(f"{len(spikes)} 个异常高值日（最高 {spikes[0]['date']}，"
                     f"{money(spikes[0]['revenue'])}，偏离基线 {spikes[0]['zscore']:.1f}σ）")
    if drops:
        parts.append(f"{len(drops)} 个异常低值日（最低 {drops[0]['date']}，"
                     f"{money(drops[0]['revenue'])}，偏离基线 {drops[0]['zscore']:.1f}σ）")
    return [_insight(
        "anomaly", "warning" if drops else "info",
        f"近 90 天检测到 {len(anomalies)} 个营收异常日",
        "；".join(parts) + "。异常多为大促脉冲或单日缺货，建议与运营日历交叉核对。",
        metric="anomaly_count", value=len(anomalies),
        recommendation="把异常日与促销日历、缺货记录对齐，确认是机会型脉冲还是履约问题",
    )]


# --------------------------------------------------------------------------- #
# narrative
# --------------------------------------------------------------------------- #
def template_narrative(context: dict, insights: list[dict]) -> str:
    """Offline narrative so the panel is never empty."""
    scope = context.get("scope") or {}
    kpis = context.get("kpis") or {}
    growth = context.get("growth") or {}
    label = scope.get("label") or "当前范围"
    sentences = [
        f"{label}在统计区间内实现营收 {money(kpis.get('revenue'))}、销量 {units(kpis.get('units'))}，"
        f"营收环比 {'+' if _f(growth.get('revenue')) >= 0 else ''}{pct(_f(growth.get('revenue')))}。"
    ]
    ranked = sorted(
        insights,
        key=lambda item: {"critical": 0, "warning": 1, "positive": 2, "info": 3}.get(item.get("severity"), 4),
    )
    for item in ranked[:2]:
        sentences.append(f"{item.get('title')}。")
    actions = [item.get("recommendation") for item in ranked if item.get("recommendation")]
    if actions:
        sentences.append(f"建议：{actions[0]}。")
    return "".join(sentences)


def build_prompt(context: dict, insights: list[dict]) -> str:
    slim_context = {
        "scope": context.get("scope"),
        "range": context.get("range"),
        "kpis": context.get("kpis"),
        "growth": context.get("growth"),
        "top_categories": (context.get("breakdown") or {}).get("category", [])[:5],
        "top_stores": (context.get("breakdown") or {}).get("store", [])[:5],
        "momentum": context.get("momentum"),
        "forecast_totals": (context.get("forecast") or {}).get("totals"),
        "forecast_model": ((context.get("forecast") or {}).get("model") or {}).get("revenue"),
        "anomalies": context.get("anomalies"),
    }
    insight_lines = [f"- [{item.get('severity')}] {item.get('title')}：{item.get('detail')}"
                     for item in insights]
    return (
        "经营上下文（JSON）：\n"
        + json.dumps(slim_context, ensure_ascii=False, indent=1, default=str)
        + "\n\n已计算出的洞察：\n"
        + "\n".join(insight_lines)
        + "\n\n请输出一段中文经营简报。"
    )


def llm_narrative(prompt: str, api_key: str | None = None,
                  base_url: str | None = None, model: str | None = None,
                  system: str | None = None) -> str | None:
    """Call any OpenAI-compatible chat endpoint. Returns None on any failure."""
    api_key = api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    base_url = (base_url or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    model = model or os.getenv("OPENAI_MODEL") or "gpt-4o-mini"
    try:
        response = requests.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "temperature": 0.4,
                "messages": [
                    {"role": "system", "content": system or system_prompt({})},
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=LLM_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
        text = ((payload.get("choices") or [{}])[0].get("message") or {}).get("content")
        if isinstance(text, str) and text.strip():
            return text.strip()
        return None
    except Exception as exc:  # pragma: no cover - network dependent
        print(f"[ai] LLM narrative unavailable, using rules: {exc}")
        return None


def generate_insights(context: dict, use_llm: bool = True) -> dict:
    """Full insight payload: rule insights + anomalies + narrative."""
    insights = rule_insights(context)
    anomalies = detect_anomalies(context.get("daily"))
    context = {**context, "anomalies": anomalies}
    insights.extend(anomalies_to_insights(anomalies))

    narrative = None
    source = "rules"
    if use_llm and os.getenv("OPENAI_API_KEY"):
        narrative = llm_narrative(build_prompt(context, insights), system=system_prompt(context))
        if narrative:
            source = "llm"
    if not narrative:
        narrative = template_narrative(context, insights)

    severity_rank = {"critical": 0, "warning": 1, "positive": 2, "info": 3}
    insights.sort(key=lambda item: severity_rank.get(item.get("severity"), 4))
    return {
        "narrative": narrative,
        "narrative_source": source,
        "llm_configured": bool(os.getenv("OPENAI_API_KEY")),
        "insights": insights,
        "anomalies": anomalies,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
