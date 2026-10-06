"""Generate a campus energy consumption dataset (data/energy_consumption.csv).

Usage:
    python data/generate_energy.py

Columns: date, building, day_type, weather, term_phase, kwh

The generator injects the effects the model is meant to recover, so the AI
explanation in the UI is backed by real signal:
  * building load      - a lab draws far more than a canteen
  * day_type           - weekends run at roughly 60% of a weekday
  * weather            - hot and cold days drive HVAC load up
  * term_phase         - exams lift load, vacations collapse it
Weather and term phase are drawn with month-dependent weights, so the seasonal
pattern is realistic without adding a column the model cannot see.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent

# building name -> base daily consumption in kWh
BUILDINGS: dict[str, float] = {
    "Teaching Block A": 850.0,
    "Laboratory B": 1200.0,
    "Library": 600.0,
    "Dormitory C": 700.0,
    "Canteen": 400.0,
}

DAY_TYPE_FACTOR = {"Weekday": 1.00, "Weekend": 0.62}
WEATHER_FACTOR = {"Sunny": 0.95, "Cloudy": 1.00, "Rain": 1.04, "Hot": 1.18, "Cold": 1.22}
TERM_FACTOR = {"Term": 1.00, "Exam Week": 1.12, "Vacation": 0.45}


def weather_weights(month: int) -> dict[str, float]:
    if month in (6, 7, 8):
        return {"Sunny": 0.30, "Cloudy": 0.20, "Rain": 0.20, "Hot": 0.28, "Cold": 0.02}
    if month in (12, 1, 2):
        return {"Sunny": 0.26, "Cloudy": 0.26, "Rain": 0.16, "Hot": 0.02, "Cold": 0.30}
    return {"Sunny": 0.30, "Cloudy": 0.30, "Rain": 0.25, "Hot": 0.08, "Cold": 0.07}


def term_weights(month: int) -> dict[str, float]:
    if month in (1, 2, 7, 8):
        return {"Term": 0.42, "Exam Week": 0.03, "Vacation": 0.55}
    if month in (6, 12):
        return {"Term": 0.72, "Exam Week": 0.22, "Vacation": 0.06}
    return {"Term": 0.88, "Exam Week": 0.08, "Vacation": 0.04}


def pick(rng: np.random.Generator, weights: dict[str, float]) -> str:
    keys = list(weights)
    probabilities = np.array([weights[key] for key in keys], dtype=float)
    return str(rng.choice(keys, p=probabilities / probabilities.sum()))


def generate(start: str, end: str, seed: int = 23) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range(start, end, freq="D")
    rows: list[dict] = []

    for day in dates:
        month = int(day.month)
        day_type = "Weekend" if day.dayofweek >= 5 else "Weekday"
        weather = pick(rng, weather_weights(month))
        term_phase = pick(rng, term_weights(month))

        for building, base in BUILDINGS.items():
            expected = (base * DAY_TYPE_FACTOR[day_type] * WEATHER_FACTOR[weather]
                        * TERM_FACTOR[term_phase])
            kwh = expected * float(rng.lognormal(0.0, 0.08))
            rows.append({
                "date": day.strftime("%Y-%m-%d"),
                "building": building,
                "day_type": day_type,
                "weather": weather,
                "term_phase": term_phase,
                "kwh": round(max(1.0, kwh), 1),
            })

    return pd.DataFrame(rows).sort_values(["date", "building"]).reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate data/energy_consumption.csv")
    parser.add_argument("--start", default="2024-01-01")
    parser.add_argument("--end", default="2025-12-31")
    parser.add_argument("--seed", type=int, default=23)
    parser.add_argument("--out", default=str(DATA_DIR / "energy_consumption.csv"))
    args = parser.parse_args()

    frame = generate(args.start, args.end, args.seed)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out, index=False, encoding="utf-8-sig")

    print(f"wrote {out}")
    print(f"rows={len(frame)} dates={frame['date'].min()}..{frame['date'].max()}")
    print(f"buildings={frame['building'].nunique()} weather={frame['weather'].nunique()} "
          f"phases={frame['term_phase'].nunique()}")
    print(f"avg_kwh={frame['kwh'].mean():.1f}  total_kwh={frame['kwh'].sum():,.0f}")
    print("mean kWh by day_type:")
    print(frame.groupby("day_type")["kwh"].mean().round(1).to_string())


if __name__ == "__main__":
    main()
