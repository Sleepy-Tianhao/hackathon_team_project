"""FastAPI entry point (intended deployment).

Run:
    pip install -r requirement.txt
    uvicorn backend.main:app --reload

Endpoint bodies are one-liners because all business logic lives in
backend.service, which is framework agnostic and tested directly.
"""
from __future__ import annotations

import threading
from contextlib import asynccontextmanager
from datetime import date

from fastapi import Body, Depends, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from . import service
from .database import BASE_DIR, ensure_seeded, get_db

FRONTEND_DIR = BASE_DIR / "frontend"
MAX_HORIZON = service.MAX_HORIZON


@asynccontextmanager
async def lifespan(app: FastAPI):
    inserted = ensure_seeded()
    if inserted:
        print(f"[startup] seeded {inserted} sales rows from data/sales.csv")
    # Fit the forecast models off the event loop so the first request is warm.
    threading.Thread(target=service.warm_up, name="warm-up", daemon=True).start()
    yield


app = FastAPI(
    title="SDC Hackathon - Sales Analytics & Forecast API",
    description="Retail sales analytics with machine-learning forecasting and AI insights.",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(service.ServiceError)
async def service_error_handler(request, exc: service.ServiceError) -> JSONResponse:
    """Map service-layer failures onto HTTP status codes."""
    return JSONResponse(status_code=exc.status, content={"detail": exc.detail})


@app.get("/api/health", tags=["system"])
def health(db: Session = Depends(get_db)) -> dict:
    """Liveness plus dataset shape - a good first call in a demo."""
    return service.get_health(db)


@app.get("/api/filters", tags=["system"])
def filters(db: Session = Depends(get_db)) -> dict:
    """Available filter values for the dashboard controls."""
    return service.get_filters(db)


@app.get("/api/config", tags=["template"])
def config() -> dict:
    """Template + field options + dataset summary: everything the UI renders from."""
    return service.get_config()


@app.get("/api/options", tags=["template"])
def options() -> dict:
    """Just the dropdown values, for refreshing them without reloading the template."""
    return service.get_field_options()


@app.post("/api/predict", tags=["template"])
def predict(payload: dict = Body(...), db: Session = Depends(get_db)) -> dict:
    """Run the configured model plugin for one set of form values.

    Body: {"fields": {"<field name>": "<value>", ...}}
    """
    return service.run_prediction(payload, db=db)


@app.post("/analyze", tags=["template"])
def analyze(payload: dict = Body(...), db: Session = Depends(get_db)) -> dict:
    """Frontend contract used by frontend/js/services/api.js.

    Body: flat field map, e.g. {"menu": "Chicken Rice", "day": "Friday", ...}
    """
    return service.analyze(payload, db=db)


@app.get("/api/summary", tags=["analytics"])
def summary(
    store: str | None = Query(None, description="Filter by store name"),
    category: str | None = Query(None, description="Filter by category name"),
    start: date | None = Query(None, description="Inclusive start date (YYYY-MM-DD)"),
    end: date | None = Query(None, description="Inclusive end date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
) -> dict:
    """Headline KPIs for a period plus growth versus the previous period."""
    return service.get_summary(db, store=store, category=category, start=start, end=end)


@app.get("/api/timeseries", tags=["analytics"])
def timeseries(
    granularity: str = Query("day", pattern="^(day|week|month)$"),
    store: str | None = None,
    category: str | None = None,
    start: date | None = None,
    end: date | None = None,
    db: Session = Depends(get_db),
) -> dict:
    """Revenue and units aggregated to day, week or month buckets."""
    return service.get_timeseries(db, granularity=granularity, store=store, category=category,
                                  start=start, end=end)


@app.get("/api/breakdown", tags=["analytics"])
def breakdown(
    dimension: str = Query("category", pattern="^(category|store)$"),
    store: str | None = None,
    category: str | None = None,
    start: date | None = None,
    end: date | None = None,
    db: Session = Depends(get_db),
) -> dict:
    """Revenue contribution ranked by store or category."""
    return service.get_breakdown(db, dimension=dimension, store=store, category=category,
                                 start=start, end=end)


@app.get("/api/momentum", tags=["analytics"])
def momentum(
    dimension: str = Query("category", pattern="^(category|store)$"),
    window: int = Query(30, ge=7, le=180),
    store: str | None = None,
    category: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    """Revenue change over the trailing window versus the window before it."""
    return service.get_momentum(db, dimension=dimension, window=window, store=store, category=category)


@app.get("/api/sales", tags=["analytics"])
def sales(
    store: str | None = None,
    category: str | None = None,
    start: date | None = None,
    end: date | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(service.DEFAULT_PAGE_SIZE, ge=1, le=service.MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
) -> dict:
    """Paginated raw fact rows, newest first."""
    return service.get_sales(db, store=store, category=category, start=start, end=end,
                             page=page, page_size=page_size)


@app.get("/api/anomalies", tags=["analytics"])
def anomalies(
    store: str | None = None,
    category: str | None = None,
    days: int = Query(90, ge=30, le=400),
    db: Session = Depends(get_db),
) -> dict:
    """Days whose revenue deviates sharply from their trailing baseline."""
    return service.get_anomalies(db, store=store, category=category, days=days)


@app.get("/api/forecast", tags=["forecast"])
def forecast(
    store: str | None = None,
    category: str | None = None,
    horizon: int = Query(30, ge=1, le=MAX_HORIZON),
    db: Session = Depends(get_db),
) -> dict:
    """Recursive multi-step revenue/units forecast with a 95% interval."""
    return service.get_forecast(db, store=store, category=category, horizon=horizon)


@app.get("/api/predictions", tags=["forecast"])
def predictions(limit: int = Query(10, ge=1, le=50), db: Session = Depends(get_db)) -> dict:
    """Forecast audit trail, newest first."""
    return service.get_predictions(db, limit=limit)


@app.get("/api/insights", tags=["forecast"])
def insights(
    store: str | None = None,
    category: str | None = None,
    start: date | None = None,
    end: date | None = None,
    horizon: int = Query(30, ge=1, le=MAX_HORIZON),
    use_llm: bool = Query(True, description="Use the configured LLM for the narrative when available"),
    db: Session = Depends(get_db),
) -> dict:
    """Rule-based insights, anomaly detection and an optional LLM narrative."""
    return service.get_insights(db, store=store, category=category, start=start, end=end,
                                horizon=horizon, use_llm=use_llm)


# Static dashboard mounted last so the /api routes keep priority.
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="dashboard")
else:  # pragma: no cover
    @app.get("/", include_in_schema=False)
    def missing_frontend() -> dict:
        return {"detail": "frontend/ directory not found", "api_docs": "/docs"}
