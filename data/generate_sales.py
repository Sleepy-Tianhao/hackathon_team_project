"""Generate a realistic synthetic sales dataset for the SDC Hackathon demo.

Usage:
    python data/generate_sales.py

Output:
    data/sales.csv  (UTF-8 with BOM, so Excel opens the Chinese labels correctly)

The signal contains a yearly growth trend, weekday seasonality, holiday/month
seasonality (618 / Double-11 / CNY), promotion lift, discount effects and noise,
so the forecasting model in backend/predictor.py has something real to learn.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent

# store name -> relative traffic multiplier
STORES: dict[str, float] = {
    "\u4e0a\u6d77\u65d7\u8230\u5e97": 1.35,
    "\u5317\u4eac\u4e2d\u5173\u6751\u5e97": 1.20,
    "\u5e7f\u5dde\u5929\u6cb3\u5e97": 1.05,
    "\u6210\u90fd\u6625\u7199\u5e97": 0.85,
}

# category name -> (base daily units, base unit price in CNY)
CATEGORIES: dict[str, tuple[float, float]] = {
    "\u667a\u80fd\u624b\u673a": (42, 3999.0),
    "\u7b14\u8bb0\u672c\u7535\u8111": (18, 6499.0),
    "\u667a\u80fd\u7a7f\u6234": (30, 1299.0),
    "\u667a\u80fd\u5bb6\u5c45": (26, 899.0),
    "\u914d\u4ef6\u8017\u6750": (55, 199.0),
}

MONTH_SEASONAL = {
    1: 0.95, 2: 0.78, 3: 0.98, 4: 1.00, 5: 1.02, 6: 1.12,
    7: 0.97, 8: 0.95, 9: 1.05, 10: 1.08, 11: 1.25, 12: 1.18,
}
WEEKDAY_FACTOR = {0: 1.00, 1: 0.97, 2: 0.99, 3: 1.01, 4: 1.06, 5: 1.18, 6: 1.12}
PROMO_PROB = {
    1: 0.10, 2: 0.08, 3: 0.07, 4: 0.08, 5: 0.12, 6: 0.35,
    7: 0.08, 8: 0.10, 9: 0.09, 10: 0.12, 11: 0.40, 12: 0.32,
}
DAILY_GROWTH = 0.0007  # ~ +50% over the two simulated years


def generate(start: str, end: str, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range(start, end, freq="D")
    rows: list[dict] = []

    for store, store_mult in STORES.items():
        for category, (base_units, base_price) in CATEGORIES.items():
            # Each store/category series gets a stable level and growth personality.
            level = float(rng.normal(1.0, 0.06))
            growth = DAILY_GROWTH * float(rng.normal(1.0, 0.25))
            for i, day in enumerate(dates):
                month = int(day.month)
                dow = int(day.dayofweek)
                trend = 1.0 + growth * i
                seasonal = MONTH_SEASONAL[month] * WEEKDAY_FACTOR[dow]

                promo = bool(rng.random() < PROMO_PROB[month])
                promo_mult = 1.35 if promo else 1.0
                if promo:
                    discount = float(round(rng.uniform(0.06, 0.22), 3))
                else:
                    discount = float(round(rng.uniform(0.0, 0.05), 3))

                units = (
                    base_units * store_mult * level * trend * seasonal * promo_mult
                    * float(rng.lognormal(0.0, 0.13))
                )
                if rng.random() < 0.01:  # occasional flash-sale spike
                    units *= float(rng.uniform(1.6, 2.2))
                units = max(0, int(round(units)))

                price = base_price * (1 + 0.00012 * i) * float(rng.normal(1.0, 0.01))
                price = round(max(1.0, price), 2)
                revenue = round(units * price * (1 - discount), 2)

                rows.append({
                    "date": day.strftime("%Y-%m-%d"),
                    "store": store,
                    "category": category,
                    "units_sold": units,
                    "unit_price": price,
                    "discount": discount,
                    "revenue": revenue,
                    "promotion": int(promo),
                    "is_weekend": int(dow >= 5),
                })

    df = pd.DataFrame(rows)
    df = df.sort_values(["date", "store", "category"]).reset_index(drop=True)
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate data/sales.csv")
    parser.add_argument("--start", default="2024-01-01")
    parser.add_argument("--end", default="2025-12-31")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default=str(DATA_DIR / "sales.csv"))
    args = parser.parse_args()

    df = generate(args.start, args.end, args.seed)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False, encoding="utf-8-sig")

    print(f"wrote {out}")
    print(f"rows={len(df)} dates={df['date'].min()}..{df['date'].max()}")
    print(f"stores={df['store'].nunique()} categories={df['category'].nunique()}")
    print(f"total_revenue={df['revenue'].sum():,.2f}")


if __name__ == "__main__":
    main()
