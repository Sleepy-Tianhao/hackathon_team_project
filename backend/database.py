"""Database engine, session factory and CSV seeding helpers.

The whole backend talks to SQLite through this module. Set DATABASE_URL in
.env to point somewhere else (Postgres works too - only the SQLite
check_same_thread flag is conditional).
"""
from __future__ import annotations

import csv
import os
from datetime import datetime
from pathlib import Path
from typing import Iterator

from dotenv import load_dotenv
from sqlalchemy import create_engine, func, insert, select
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
SALES_CSV = DATA_DIR / "sales.csv"

load_dotenv(BASE_DIR / ".env")


def _default_url() -> str:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return "sqlite:///" + (DATA_DIR / "sales.db").as_posix()


DATABASE_URL = os.getenv("DATABASE_URL") or _default_url()


class Base(DeclarativeBase):
    """Declarative base shared by every ORM model."""


_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def get_db() -> Iterator[Session]:
    """FastAPI dependency that yields a scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create every table declared on Base."""
    from . import models  # noqa: F401  (import registers the mappers)

    Base.metadata.create_all(bind=engine)


def _row_to_record(row: dict) -> dict:
    return {
        "date": datetime.strptime(row["date"].strip(), "%Y-%m-%d").date(),
        "store": row["store"].strip(),
        "category": row["category"].strip(),
        "units_sold": int(float(row["units_sold"])),
        "unit_price": float(row["unit_price"]),
        "discount": float(row["discount"]),
        "revenue": float(row["revenue"]),
        "promotion": int(float(row.get("promotion") or 0)),
        "is_weekend": int(float(row.get("is_weekend") or 0)),
    }


def load_csv(force: bool = False, path: Path | str | None = None, db: Session | None = None) -> int:
    """Seed the sales table from the CSV. No-op when data is already present.

    Returns the number of rows inserted.
    """
    from .models import SalesRecord

    csv_path = Path(path) if path else SALES_CSV
    if not csv_path.exists():
        return 0

    owns_session = db is None
    if owns_session:
        init_db()
        db = SessionLocal()

    try:
        existing = db.scalar(select(func.count()).select_from(SalesRecord)) or 0
        if existing and not force:
            return 0
        if force:
            db.query(SalesRecord).delete()
            db.commit()

        records: list[dict] = []
        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                if not row.get("date"):
                    continue
                records.append(_row_to_record(row))

        for start in range(0, len(records), 5000):
            chunk = records[start:start + 5000]
            if chunk:
                db.execute(insert(SalesRecord), chunk)
                db.commit()
        return len(records)
    finally:
        if owns_session:
            db.close()


def ensure_seeded() -> int:
    """Called on API startup so a fresh checkout works with zero setup."""
    if os.getenv("SKIP_DB_SEED") == "1":
        return 0
    try:
        return load_csv()
    except Exception as exc:  # pragma: no cover - startup must never hard-fail
        print(f"[database] seeding skipped: {exc}")
        return 0


def reset_db() -> None:
    """Drop and recreate every table (used by tooling and tests)."""
    from . import models  # noqa: F401

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
