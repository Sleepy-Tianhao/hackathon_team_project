"""Framework-agnostic business logic for the sales analytics API.

Every function takes a SQLAlchemy Session plus plain Python arguments and returns
plain JSON-serialisable dicts. Nothing in here imports a web framework, which is
what lets the same logic be served by both entry points:

* backend.main   - the FastAPI application (intended deployment)
* backend.server - a zero-dependency standard-library HTTP server (offline demo)

Failures raise ServiceError, which each entry point maps to its own error shape.
"""
from __future__ import annotations

import os
import time
from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import ai as ai_layer
from . import model_api
from . import predictor
from . import template_config
from .database import DATABASE_URL, SessionLocal
from .models import PredictionRun, SalesRecord

GRANULARITIES = ("day", "week", "month")
DIMENSIONS = ("category", "store")
MAX_HORIZON = 180
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 200


class ServiceError(Exception):
    """A request problem that maps onto an HTTP status code."""

    def __init__(self, detail: str, status: int = 400) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status = status


# --------------------------------------------------------------------------- #
# internal helpers
# --------------------------------------------------------------------------- #
def _resolve_range(db: Session, start: date | None, end: date | None) -> tuple[pd.Timestamp, pd.Timestamp]:
    df = predictor.get_frame(db)
    if df.empty:
        raise ServiceError("no sales data available - seed data/sales.csv first", 404)
    lo = pd.Timestamp(start) if start else pd.Timestamp(df["date"].min())
    hi = pd.Timestamp(end) if end else pd.Timestamp(df["date"].max())
    if lo > hi:
        raise ServiceError("start must be earlier than or equal to end")
    return lo.normalize(), hi.normalize()


def _filtered_frame(db: Session, store: str | None = None, category: str | None = None,
                    start: pd.Timestamp | date | None = None,
                    end: pd.Timestamp | date | None = None) -> pd.DataFrame:
    df = predictor.get_frame(db)
    if df.empty:
        return df
    mask = pd.Series(True, index=df.index)
    if store:
        mask &= df["store"] == store
    if category:
        mask &= df["category"] == category
    if start is not None:
        mask &= df["date"] >= pd.Timestamp(start)
    if end is not None:
        mask &= df["date"] <= pd.Timestamp(end)
    return df[mask]


def _scope_label(store: str | None, category: str | None) -> str:
    return f"{store or '全部门店'} / {category or '全部品类'}"


def _kpis(frame: pd.DataFrame) -> dict:
    if frame.empty:
        return {}
    revenue = float(frame["revenue"].sum())
    units_total = float(frame["units_sold"].sum())
    daily = (
        frame.groupby(frame["date"].dt.normalize())
        .agg(revenue=("revenue", "sum"), units_sold=("units_sold", "sum"),
             promotion=("promotion", "max"), is_weekend=("is_weekend", "max"))
    )
    promo_days = daily[daily["promotion"] > 0]
    regular_days = daily[daily["promotion"] == 0]
    weekend_days = daily[daily["is_weekend"] > 0]
    weekday_days = daily[daily["is_weekend"] == 0]

    avg_promo = float(promo_days["revenue"].mean()) if len(promo_days) else 0.0
    avg_regular = float(regular_days["revenue"].mean()) if len(regular_days) else 0.0
    avg_weekend = float(weekend_days["revenue"].mean()) if len(weekend_days) else 0.0
    avg_weekday = float(weekday_days["revenue"].mean()) if len(weekday_days) else 0.0

    promo_uplift = (avg_promo / avg_regular - 1.0) if avg_promo and avg_regular else None
    weekend_uplift = (avg_weekend / avg_weekday - 1.0) if avg_weekend and avg_weekday else None

    return {
        "revenue": round(revenue, 2),
        "units": round(units_total, 1),
        "avg_unit_price": round(revenue / units_total, 2) if units_total else 0.0,
        "avg_daily_revenue": round(float(daily["revenue"].mean()), 2) if len(daily) else 0.0,
        "avg_daily_units": round(float(daily["units_sold"].mean()), 1) if len(daily) else 0.0,
        "active_days": int(len(daily)),
        "sales_rows": int(len(frame)),
        "promo_day_share": round(len(promo_days) / len(daily), 4) if len(daily) else 0.0,
        "promo_revenue_share": round(float(promo_days["revenue"].sum()) / revenue, 4) if revenue > 0 else 0.0,
        "avg_daily_revenue_promo": round(avg_promo, 2),
        "avg_daily_revenue_regular": round(avg_regular, 2),
        "promo_uplift": round(promo_uplift, 4) if promo_uplift is not None else None,
        "avg_daily_revenue_weekend": round(avg_weekend, 2),
        "avg_daily_revenue_weekday": round(avg_weekday, 2),
        "weekend_uplift": round(weekend_uplift, 4) if weekend_uplift is not None else None,
    }


def _growth(current: dict, previous: dict) -> dict:
    out: dict[str, Any] = {}
    for key in ("revenue", "units", "avg_daily_revenue"):
        now = current.get(key)
        before = previous.get(key)
        out[key] = None if now is None or not before else round(float(now) / float(before) - 1.0, 4)
    return out


def _breakdown(frame: pd.DataFrame, dimension: str) -> list[dict]:
    if frame.empty or dimension not in DIMENSIONS:
        return []
    grouped = (
        frame.groupby(dimension)
        .agg(revenue=("revenue", "sum"), units_sold=("units_sold", "sum"), days=("date", "nunique"))
        .reset_index()
        .sort_values("revenue", ascending=False)
    )
    total = float(grouped["revenue"].sum())
    return [{
        "name": str(row[dimension]),
        "revenue": round(float(row["revenue"]), 2),
        "units_sold": round(float(row["units_sold"]), 1),
        "days": int(row["days"]),
        "avg_daily_revenue": round(float(row["revenue"]) / max(1, int(row["days"])), 2),
        "share": round(float(row["revenue"]) / total, 4) if total > 0 else 0.0,
    } for _, row in grouped.iterrows()]


def _momentum(frame: pd.DataFrame, dimension: str = "category", window: int = 30) -> list[dict]:
    if frame.empty:
        return []
    latest = frame["date"].max().normalize()
    recent_start = latest - pd.Timedelta(days=window - 1)
    prior_start = recent_start - pd.Timedelta(days=window)
    recent = frame[frame["date"] >= recent_start].groupby(dimension)["revenue"].sum()
    prior = frame[(frame["date"] >= prior_start) & (frame["date"] < recent_start)].groupby(dimension)["revenue"].sum()

    out: list[dict] = []
    for name in sorted(set(recent.index) | set(prior.index)):
        now = float(recent.get(name, 0.0))
        before = float(prior.get(name, 0.0))
        if now <= 0 and before <= 0:
            continue
        change = (now / before - 1.0) if before > 0 else None
        out.append({
            "name": str(name),
            "recent": round(now, 2),
            "prior": round(before, 2),
            "change": round(change, 4) if change is not None else None,
        })
    out.sort(key=lambda item: (item["change"] is None, -(item["change"] or 0.0)))
    return out


def _timeseries(frame: pd.DataFrame, granularity: str = "day") -> list[dict]:
    if frame.empty:
        return []
    if granularity == "day":
        bucket = frame["date"].dt.normalize()
    elif granularity == "week":
        bucket = frame["date"].dt.to_period("W").dt.start_time
    else:
        bucket = frame["date"].dt.to_period("M").dt.start_time

    grouped = (
        frame.groupby(bucket)
        .agg(revenue=("revenue", "sum"), units_sold=("units_sold", "sum"))
        .reset_index()
        .sort_values("date")
    )
    return [{
        "period": row.date.strftime("%Y-%m-%d"),
        "revenue": round(float(row.revenue), 2),
        "units_sold": round(float(row.units_sold), 1),
    } for row in grouped.itertuples()]


def _daily_series(frame: pd.DataFrame) -> list[dict]:
    if frame.empty:
        return []
    daily = (
        frame.groupby(frame["date"].dt.normalize())
        .agg(revenue=("revenue", "sum"), units_sold=("units_sold", "sum"),
             promotion=("promotion", "max"), is_weekend=("is_weekend", "max"))
        .reset_index()
        .sort_values("date")
    )
    return [{
        "date": row.date.strftime("%Y-%m-%d"),
        "revenue": round(float(row.revenue), 2),
        "units_sold": round(float(row.units_sold), 1),
        "promotion": bool(row.promotion),
        "is_weekend": bool(row.is_weekend),
    } for row in daily.itertuples()]


def _validate_horizon(horizon: int) -> int:
    horizon = int(horizon)
    if not 1 <= horizon <= MAX_HORIZON:
        raise ServiceError(f"horizon must be between 1 and {MAX_HORIZON}")
    return horizon


def _validate_granularity(granularity: str) -> str:
    if granularity not in GRANULARITIES:
        raise ServiceError(f"granularity must be one of {', '.join(GRANULARITIES)}")
    return granularity


def _validate_dimension(dimension: str) -> str:
    if dimension not in DIMENSIONS:
        raise ServiceError(f"dimension must be one of {', '.join(DIMENSIONS)}")
    return dimension


# --------------------------------------------------------------------------- #
# public service functions
# --------------------------------------------------------------------------- #
def active_plugin_name(template: dict) -> str:
    """MODEL_BACKEND overrides the template's plugin choice."""
    return (os.getenv("MODEL_BACKEND") or template["model"]["plugin"]).strip()


def warm_up(db: Session | None = None) -> bool:
    """Precompute whatever the first real request would otherwise have to do.

    Model fitting and the backtest are the only slow paths in this API (seconds,
    once). Both entry points call this from a background thread at startup so the
    first click during a demo is already warm.
    """
    owns_session = db is None
    if owns_session:
        db = SessionLocal()
    try:
        template = template_config.load_template()
        if active_plugin_name(template) == "sales-forecast":
            frame = predictor.get_frame(db)
            if frame.empty:
                return False
            predictor.get_engine(frame)
            return True
        return model_api.warm_up(template, template_config.dataset_frame(template))
    except Exception as exc:  # pragma: no cover - warm-up is best effort
        print(f"[service] warm-up skipped: {exc}")
        return False
    finally:
        if owns_session and db is not None:
            db.close()


def get_health(db: Session) -> dict:
    total = db.scalar(select(func.count()).select_from(SalesRecord)) or 0
    first = db.scalar(select(func.min(SalesRecord.date)))
    last = db.scalar(select(func.max(SalesRecord.date)))
    runs = db.scalar(select(func.count()).select_from(PredictionRun)) or 0
    return {
        "status": "ok",
        "rows": int(total),
        "date_min": first.isoformat() if first else None,
        "date_max": last.isoformat() if last else None,
        "forecast_runs": int(runs),
        "database": DATABASE_URL,
        "llm_configured": bool(os.getenv("OPENAI_API_KEY")),
    }


def get_filters(db: Session) -> dict:
    df = predictor.get_frame(db)
    if df.empty:
        return {"stores": [], "categories": [], "series": [], "date_min": None, "date_max": None,
                "granularities": list(GRANULARITIES), "horizon_max": MAX_HORIZON}
    return {
        "stores": sorted(df["store"].unique().tolist()),
        "categories": sorted(df["category"].unique().tolist()),
        "series": sorted(df["series_id"].unique().tolist()),
        "date_min": df["date"].min().date().isoformat(),
        "date_max": df["date"].max().date().isoformat(),
        "granularities": list(GRANULARITIES),
        "horizon_max": MAX_HORIZON,
    }


def get_summary(db: Session, store: str | None = None, category: str | None = None,
                start: date | None = None, end: date | None = None) -> dict:
    lo, hi = _resolve_range(db, start, end)
    frame = _filtered_frame(db, store, category, lo, hi)
    if frame.empty:
        raise ServiceError("no sales data in the requested scope", 404)

    days = (hi - lo).days + 1
    previous_frame = _filtered_frame(db, store, category, lo - pd.Timedelta(days=days), lo - pd.Timedelta(days=1))
    kpis = _kpis(frame)
    previous = _kpis(previous_frame) if not previous_frame.empty else {}
    return {
        "scope": {"store": store, "category": category, "label": _scope_label(store, category)},
        "range": {"start": lo.date().isoformat(), "end": hi.date().isoformat(), "days": days},
        "kpis": kpis,
        "previous": {key: previous.get(key) for key in ("revenue", "units", "avg_daily_revenue")},
        "growth": _growth(kpis, previous),
        "breakdown": {
            "category": _breakdown(frame, "category"),
            "store": _breakdown(frame, "store"),
        },
    }


def get_timeseries(db: Session, granularity: str = "day", store: str | None = None,
                   category: str | None = None, start: date | None = None, end: date | None = None) -> dict:
    granularity = _validate_granularity(granularity)
    lo, hi = _resolve_range(db, start, end)
    frame = _filtered_frame(db, store, category, lo, hi)
    return {
        "granularity": granularity,
        "scope": {"store": store, "category": category, "label": _scope_label(store, category)},
        "range": {"start": lo.date().isoformat(), "end": hi.date().isoformat()},
        "points": _timeseries(frame, granularity),
    }


def get_breakdown(db: Session, dimension: str = "category", store: str | None = None,
                  category: str | None = None, start: date | None = None, end: date | None = None) -> dict:
    dimension = _validate_dimension(dimension)
    lo, hi = _resolve_range(db, start, end)
    frame = _filtered_frame(db, store, category, lo, hi)
    return {"dimension": dimension, "items": _breakdown(frame, dimension)}


def get_momentum(db: Session, dimension: str = "category", window: int = 30,
                 store: str | None = None, category: str | None = None) -> dict:
    dimension = _validate_dimension(dimension)
    window = int(window)
    if not 7 <= window <= 180:
        raise ServiceError("window must be between 7 and 180")
    lo, hi = _resolve_range(db, None, None)
    frame = _filtered_frame(db, store, category, lo, hi)
    return {"dimension": dimension, "window_days": window, "items": _momentum(frame, dimension, window)}


def get_sales(db: Session, store: str | None = None, category: str | None = None,
              start: date | None = None, end: date | None = None,
              page: int = 1, page_size: int = DEFAULT_PAGE_SIZE) -> dict:
    page = int(page)
    page_size = int(page_size)
    if page < 1:
        raise ServiceError("page must be >= 1")
    if not 1 <= page_size <= MAX_PAGE_SIZE:
        raise ServiceError(f"page_size must be between 1 and {MAX_PAGE_SIZE}")

    lo, hi = _resolve_range(db, start, end)
    frame = _filtered_frame(db, store, category, lo, hi).sort_values("date", ascending=False)
    total = int(len(frame))
    page_frame = frame.iloc[(page - 1) * page_size:(page - 1) * page_size + page_size]
    items = [{
        "date": row.date.strftime("%Y-%m-%d"),
        "store": str(row.store),
        "category": str(row.category),
        "units_sold": int(row.units_sold),
        "unit_price": round(float(row.unit_price), 2),
        "discount": round(float(row.discount), 4),
        "revenue": round(float(row.revenue), 2),
        "promotion": bool(row.promotion),
        "is_weekend": bool(row.is_weekend),
    } for row in page_frame.itertuples()]
    pages = (total + page_size - 1) // page_size if page_size else 1
    return {"total": total, "page": page, "page_size": page_size, "pages": pages, "items": items}


def get_anomalies(db: Session, store: str | None = None, category: str | None = None, days: int = 90) -> dict:
    days = int(days)
    if not 30 <= days <= 400:
        raise ServiceError("days must be between 30 and 400")
    lo, hi = _resolve_range(db, None, None)
    frame = _filtered_frame(db, store, category, lo, hi)
    return {
        "scope": {"store": store, "category": category, "label": _scope_label(store, category)},
        "window_days": days,
        "anomalies": ai_layer.detect_anomalies(_daily_series(frame)[-days:]),
    }


def get_forecast(db: Session, store: str | None = None, category: str | None = None, horizon: int = 30) -> dict:
    horizon = _validate_horizon(horizon)
    try:
        result = predictor.forecast(db, store=store, category=category, horizon=horizon)
    except ValueError as exc:
        raise ServiceError(str(exc)) from exc
    predictor.log_prediction_run(db, result, store, category, horizon)
    return result


def get_predictions(db: Session, limit: int = 10) -> dict:
    limit = int(limit)
    if not 1 <= limit <= 50:
        raise ServiceError("limit must be between 1 and 50")
    rows = db.scalars(select(PredictionRun).order_by(PredictionRun.id.desc()).limit(limit)).all()
    return {"runs": [row.to_dict() for row in rows]}


# --------------------------------------------------------------------------- #
# template-driven prediction API (the contract the UI actually uses)
# --------------------------------------------------------------------------- #
def get_config() -> dict:
    """Everything the frontend needs in one call: template + options + dataset meta.

    Also reports which model plugin is active and, for the local statistical
    plugin, the measured backtest behind its confidence figure.
    """
    try:
        payload = template_config.get_config()
        template = template_config.load_template()
        plugin_name = active_plugin_name(template)
        backtest = None
        if plugin_name == "group-baseline":
            backtest = model_api.backtest_group_baseline(template, template_config.dataset_frame(template))
        payload["model"] = {"plugin": plugin_name, "backtest": backtest or None}
        return payload
    except template_config.TemplateError as exc:
        raise ServiceError(str(exc), 500) from exc
    except Exception as exc:  # pragma: no cover - config must still render
        print(f"[service] model summary unavailable: {exc}")
        payload = template_config.get_config()
        payload["model"] = {"plugin": None, "backtest": None}
        return payload


def get_field_options() -> dict:
    """Just the dropdown values + dataset summary (refresh without reloading the template)."""
    try:
        template = template_config.load_template()
        return {
            "options": template_config.field_options(template),
            "dataset": template_config.dataset_meta(template),
        }
    except template_config.TemplateError as exc:
        raise ServiceError(str(exc), 500) from exc


def _coerce_value(field: dict, raw: Any) -> Any:
    if raw is None:
        return None
    if isinstance(raw, str) and not raw.strip():
        return None
    if field["type"] == "number":
        try:
            return float(raw)
        except (TypeError, ValueError) as exc:
            raise ServiceError(f"字段 '{field['name']}' 需要数字，收到 {raw!r}", 422) from exc
    return raw.strip() if isinstance(raw, str) else raw


def validate_fields(template: dict, raw: Any, options: dict) -> dict:
    """Coerce and validate one submission against the template. Raises 422 on problems."""
    if not isinstance(raw, dict):
        raise ServiceError('请求体必须是 {"fields": {...}}', 422)

    declared = template["fields"]
    unknown = sorted(set(raw) - {field["name"] for field in declared})
    if unknown:
        raise ServiceError(f"未知字段: {', '.join(unknown)}", 422)

    values: dict[str, Any] = {}
    for field in declared:
        name = field["name"]
        value = _coerce_value(field, raw.get(name))
        if value is None:
            if field.get("required", True):
                raise ServiceError(f"缺少必填字段 '{name}' ({field['label']})", 422)
            values[name] = ""
            continue

        allowed = options.get(name) or []
        if field["type"] == "number":
            low, high = field.get("min"), field.get("max")
            if low is not None and float(value) < float(low):
                raise ServiceError(f"字段 '{name}' 不能小于 {low}", 422)
            if high is not None and float(value) > float(high):
                raise ServiceError(f"字段 '{name}' 不能大于 {high}", 422)
            if allowed and all(isinstance(item, (int, float)) for item in allowed):
                if float(value) not in [float(item) for item in allowed]:
                    raise ServiceError(f"字段 '{name}' 的值 {value!r} 不在可选范围内", 422)
        elif allowed:
            if str(value) not in [str(item) for item in allowed]:
                raise ServiceError(f"字段 '{name}' 的值 {value!r} 不在可选范围内", 422)

        values[name] = value
    return values


def analyze(payload: Any, db: Session | None = None) -> dict:
    """The frontend contract (POST /analyze).

    frontend/js/app.js reads prediction / average / change_percent / confidence /
    explanation, so those flat aliases are added on top of the full envelope
    rather than maintained as a second, divergent response shape.
    """
    envelope = run_prediction(payload, db=db)
    delta = envelope.get("delta")
    return {
        **envelope,
        "prediction": envelope.get("value"),
        "average": envelope.get("baseline"),
        "change_percent": None if delta is None else round(float(delta) * 100.0, 1),
        "confidence": envelope.get("confidence"),
        "explanation": envelope.get("explanation", ""),
    }


def run_prediction(payload: Any, db: Session | None = None) -> dict:
    """The template contract: form values in, a normalised prediction payload out."""
    try:
        template = template_config.load_template()
    except template_config.TemplateError as exc:
        raise ServiceError(str(exc), 500) from exc

    raw = payload.get("fields") if isinstance(payload, dict) and "fields" in payload else payload
    options = template_config.field_options(template)
    values = validate_fields(template, raw if raw is not None else {}, options)

    try:
        frame = template_config.dataset_frame(template)
    except template_config.TemplateError as exc:
        raise ServiceError(str(exc), 500) from exc

    started = time.perf_counter()
    try:
        plugin = model_api.resolve_model(template)
    except model_api.ModelError as exc:
        raise ServiceError(str(exc), exc.status) from exc

    try:
        result = plugin.predict(values, frame, db=db)
    except model_api.ModelError as exc:
        # A dead external API must not kill a live demo: fall back locally.
        fallback = model_api.fallback_plugin(template) if plugin.requires_network else None
        if fallback is None:
            raise ServiceError(f"模型调用失败: {exc}", exc.status) from exc
        try:
            result = fallback.predict(values, frame, db=db)
        except model_api.ModelError as inner:
            raise ServiceError(f"模型调用失败: {exc}; 本地回退也失败: {inner}", exc.status) from inner
        result.meta = {
            **result.meta,
            "fallback": True,
            "fallback_reason": str(exc),
            "requested_plugin": plugin.name,
        }

    return result.to_payload(template, values, elapsed_ms=(time.perf_counter() - started) * 1000)


def get_insights(db: Session, store: str | None = None, category: str | None = None,
                 start: date | None = None, end: date | None = None,
                 horizon: int = 30, use_llm: bool = True) -> dict:
    horizon = _validate_horizon(horizon)
    lo, hi = _resolve_range(db, start, end)
    frame = _filtered_frame(db, store, category, lo, hi)
    if frame.empty:
        raise ServiceError("no sales data in the requested scope", 404)

    days = (hi - lo).days + 1
    previous_frame = _filtered_frame(db, store, category, lo - pd.Timedelta(days=days), lo - pd.Timedelta(days=1))
    kpis = _kpis(frame)
    previous = _kpis(previous_frame) if not previous_frame.empty else {}

    forecast_payload = None
    try:
        forecast_payload = predictor.forecast(db, store=store, category=category, horizon=horizon)
    except ValueError as exc:
        print(f"[service] forecast unavailable while building insights: {exc}")

    context = {
        "scope": {"store": store, "category": category, "label": _scope_label(store, category)},
        "range": {"start": lo.date().isoformat(), "end": hi.date().isoformat(), "days": days},
        "kpis": kpis,
        "previous": previous,
        "growth": _growth(kpis, previous),
        "breakdown": {"store": _breakdown(frame, "store"), "category": _breakdown(frame, "category")},
        "momentum": _momentum(frame, "category"),
        "daily": _daily_series(frame)[-90:],
        "timeseries": _timeseries(frame, "week")[-26:],
        "forecast": forecast_payload,
    }
    return ai_layer.generate_insights(context, use_llm=use_llm)
