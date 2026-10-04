"""SQLAlchemy ORM models.

SalesRecord mirrors data/sales.csv one-to-one. PredictionRun keeps an audit
trail of forecasts so the dashboard can show what was predicted when.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class SalesRecord(Base):
    """A single store/category/day sales fact."""

    __tablename__ = "sales_records"
    __table_args__ = (
        UniqueConstraint("date", "store", "category", name="uq_sales_date_store_category"),
        Index("ix_sales_store_category_date", "store", "category", "date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    store: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    units_sold: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unit_price: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    discount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    revenue: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    promotion: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_weekend: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "date": self.date.isoformat(),
            "store": self.store,
            "category": self.category,
            "units_sold": self.units_sold,
            "unit_price": round(float(self.unit_price), 2),
            "discount": round(float(self.discount), 4),
            "revenue": round(float(self.revenue), 2),
            "promotion": bool(self.promotion),
            "is_weekend": bool(self.is_weekend),
        }

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<SalesRecord {self.date} {self.store} {self.category} {self.revenue}>"


class PredictionRun(Base):
    """Audit trail entry for one served forecast."""

    __tablename__ = "prediction_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    store: Mapped[str | None] = mapped_column(String(64), nullable=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    horizon: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    model_name: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    mae: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    rmse: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    mape: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    baseline_mape: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_revenue: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_units: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    payload: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "store": self.store,
            "category": self.category,
            "horizon": self.horizon,
            "model_name": self.model_name,
            "mae": round(float(self.mae), 2),
            "rmse": round(float(self.rmse), 2),
            "mape": round(float(self.mape), 4),
            "baseline_mape": round(float(self.baseline_mape), 4),
            "total_revenue": round(float(self.total_revenue), 2),
            "total_units": round(float(self.total_units), 2),
        }
