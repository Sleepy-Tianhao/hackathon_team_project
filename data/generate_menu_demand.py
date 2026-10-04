"""Generate a campus canteen demand dataset (data/menu_demand.csv).

Usage:
    python data/generate_menu_demand.py

Output columns: date, menu, weekday, weather, event, portions

The generator injects the effects the template's local baseline model is meant to
recover, so the AI explanation in the UI is backed by real signal:
  * weekday effect  - campus canteens are quiet on weekends
  * weather effect  - rain and heat reduce footfall
  * event effect    - exam week / sports day lift demand, holidays crush it
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent

MENUS: dict[str, float] = {
    "Chicken Rice": 120.0,
    "Noodle Soup": 95.0,
    "Fried Rice": 110.0,
    "Vegetarian Bowl": 60.0,
    "Curry Rice": 85.0,
}

WEEKDAY_FACTOR = {
    "Monday": 1.06, "Tuesday": 1.02, "Wednesday": 1.00,
    "Thursday": 0.99, "Friday": 0.88, "Saturday": 0.46, "Sunday": 0.42,
}
WEATHER_FACTOR = {"Sunny": 1.05, "Cloudy": 1.00, "Rain": 0.90, "Hot": 0.94}
EVENT_FACTOR = {"None": 1.00, "Exam Week": 1.15, "Sports Day": 1.21, "Holiday": 0.55}

WEATHER_WEIGHTS = {"Sunny": 0.34, "Cloudy": 0.31, "Rain": 0.24, "Hot": 0.11}
EVENT_WEIGHTS = {"None": 0.80, "Exam Week": 0.08, "Sports Day": 0.05, "Holiday": 0.07}


def generate(start: str, end: str, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range(start, end, freq="D")
    rows: list[dict] = []

    for day in dates:
        weekday = day.day_name()
        weather = str(rng.choice(list(WEATHER_WEIGHTS), p=list(WEATHER_WEIGHTS.values())))
        event = str(rng.choice(list(EVENT_WEIGHTS), p=list(EVENT_WEIGHTS.values())))
        # Summer runs hotter, which shifts the weather mix.
        if day.month in (6, 7, 8) and weather == "Cloudy" and rng.random() < 0.35:
            weather = "Hot"

        for menu, base in MENUS.items():
            expected = (base * WEEKDAY_FACTOR[weekday] * WEATHER_FACTOR[weather]
                        * EVENT_FACTOR[event])
            portions = int(round(max(0.0, expected * float(rng.lognormal(0.0, 0.09)))))
            rows.append({
                "date": day.strftime("%Y-%m-%d"),
                "menu": menu,
                "weekday": weekday,
                "weather": weather,
                "event": event,
                "portions": portions,
            })

    return pd.DataFrame(rows).sort_values(["date", "menu"]).reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate data/menu_demand.csv")
    parser.add_argument("--start", default="2024-01-01")
    parser.add_argument("--end", default="2025-12-31")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", default=str(DATA_DIR / "menu_demand.csv"))
    args = parser.parse_args()

    frame = generate(args.start, args.end, args.seed)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out, index=False, encoding="utf-8-sig")

    print(f"wrote {out}")
    print(f"rows={len(frame)} dates={frame['date'].min()}..{frame['date'].max()}")
    print(f"menus={frame['menu'].nunique()} weather={frame['weather'].nunique()} events={frame['event'].nunique()}")
    print(f"avg_portions={frame['portions'].mean():.1f}")
    print("mean portions by weekday:")
    print(frame.groupby("weekday")["portions"].mean().round(1).to_string())


if __name__ == "__main__":
    main()
