"""Template configuration: load, validate and resolve a template.json.

One JSON file drives the entire UI and the prediction contract: page copy, input
fields, dropdown options, output labels, which model plugin to call, and which
CSV the local plugins read. Nothing in the HTML/JS hardcodes a field name.

Schema
------
{
  "id": "food-demand",
  "app":     { brand, title, subtitle, footer },
  "dataset": { path, date_column, target, unit, target_label },
  "model":   { plugin, options: {...} },
  "fields":  [ { name, label, type, source, column, options,
                 default, required, suffix, help, min, max } ],
  "output":  { headline, subheadline, unit, decimals, delta_label,
               explanation_title, submit_label }
}

Field types: "select" | "number" | "text".
Field sources:
  "dataset" -> options are the distinct values of "column"
  "static"  -> options come from the field itself
  "input"   -> free input: no options and no column. The value is passed straight
               to the model (useful for a text field your own model consumes).

Validation is deliberately loud: a typo in template.json should fail with a
precise message pointing at the offending field index, not a confusing 500.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pandas as pd

from .database import BASE_DIR

DEFAULT_TEMPLATE_FILE = BASE_DIR / "template.json"
FIELD_TYPES = ("select", "number", "text")
FIELD_SOURCES = ("dataset", "static", "input")

_TEMPLATE_CACHE: dict[tuple, dict] = {}
_DATASET_CACHE: dict[tuple, pd.DataFrame] = {}


class TemplateError(Exception):
    """template.json is missing, unreadable or malformed."""


# --------------------------------------------------------------------------- #
# loading + validation
# --------------------------------------------------------------------------- #
def template_path() -> Path:
    """TEMPLATE_FILE lets you run different templates without editing files."""
    override = os.getenv("TEMPLATE_FILE")
    path = Path(override) if override else DEFAULT_TEMPLATE_FILE
    if not path.is_absolute():
        path = BASE_DIR / path
    return path


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise TemplateError(message)


def _validate(raw: Any, source: Path) -> dict:
    where = f"template.json ({source.name})"
    _require(isinstance(raw, dict), f"{where}: top level must be a JSON object")

    _require(isinstance(raw.get("id"), str) and raw["id"], f"{where}: 'id' must be a non-empty string")

    app = raw.get("app")
    _require(isinstance(app, dict), f"{where}: 'app' object is required")
    for key in ("title", "subtitle"):
        _require(isinstance(app.get(key), str) and app[key], f"{where}: 'app.{key}' is required")

    dataset = raw.get("dataset")
    _require(isinstance(dataset, dict), f"{where}: 'dataset' object is required")
    for key in ("path", "target"):
        _require(isinstance(dataset.get(key), str) and dataset[key],
                 f"{where}: 'dataset.{key}' is required")
    dataset.setdefault("date_column", "date")
    dataset.setdefault("unit", "")
    dataset.setdefault("target_label", dataset["target"])

    model = raw.get("model")
    _require(isinstance(model, dict), f"{where}: 'model' object is required")
    _require(isinstance(model.get("plugin"), str) and model["plugin"],
             f"{where}: 'model.plugin' is required (e.g. \"group-baseline\")")
    model.setdefault("options", {})
    _require(isinstance(model["options"], dict), f"{where}: 'model.options' must be an object")

    fields = raw.get("fields")
    _require(isinstance(fields, list) and fields, f"{where}: 'fields' must be a non-empty array")
    seen: set[str] = set()
    for index, item in enumerate(fields):
        at = f"{where}: fields[{index}]"
        _require(isinstance(item, dict), f"{at} must be an object")
        name = item.get("name")
        _require(isinstance(name, str) and name, f"{at}.name is required")
        _require(name not in seen, f"{at}.name '{name}' is duplicated")
        seen.add(name)
        _require(isinstance(item.get("label"), str) and item["label"], f"{at}.label is required")

        field_type = item.get("type", "select")
        _require(field_type in FIELD_TYPES, f"{at}.type must be one of {', '.join(FIELD_TYPES)}")
        item["type"] = field_type

        source = item.get("source", "static" if item.get("options") else "dataset")
        _require(source in FIELD_SOURCES, f"{at}.source must be one of {', '.join(FIELD_SOURCES)}")
        item["source"] = source

        if source == "dataset":
            _require(isinstance(item.get("column"), str) and item["column"],
                     f"{at}.column is required when source is \"dataset\"")
        if source == "static":
            _require(isinstance(item.get("options"), list) and item["options"],
                     f"{at}.options must be a non-empty array when source is \"static\"")
        if source == "input":
            item.setdefault("options", [])

        item.setdefault("required", field_type != "text")
        item.setdefault("default", None)
        item.setdefault("help", "")
        # "placeholder" is the frontend-facing name, "suffix" the older alias.
        item.setdefault("placeholder", item.get("suffix") or "")
        item.setdefault("suffix", item.get("placeholder") or "")
        _require(isinstance(item["required"], bool), f"{at}.required must be true/false")

    output = raw.get("output")
    _require(isinstance(output, dict), f"{where}: 'output' object is required")
    for key in ("headline", "unit", "delta_label"):
        _require(isinstance(output.get(key), str), f"{where}: 'output.{key}' must be a string")
    output.setdefault("subheadline", "")
    output.setdefault("decimals", 0)
    output.setdefault("explanation_title", "AI Explanation")
    output.setdefault("submit_label", "Predict")
    output.setdefault("locale", app.get("locale", "zh"))

    return raw


def load_template() -> dict:
    """Read and validate the active template. Cached by path + mtime."""
    path = template_path()
    if not path.is_file():
        raise TemplateError(f"template file not found: {path}")
    key = (str(path), path.stat().st_mtime_ns)
    cached = _TEMPLATE_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise TemplateError(f"{path.name} is not valid JSON: {exc}") from exc
    template = _validate(raw, path)
    _TEMPLATE_CACHE.clear()
    _TEMPLATE_CACHE[key] = template
    return template


# --------------------------------------------------------------------------- #
# dataset access
# --------------------------------------------------------------------------- #
def dataset_path(template: dict) -> Path:
    path = Path(template["dataset"]["path"])
    return path if path.is_absolute() else BASE_DIR / path


def dataset_frame(template: dict) -> pd.DataFrame:
    """The CSV the local plugins read, cached by path + mtime."""
    path = dataset_path(template)
    if not path.is_file():
        raise TemplateError(f"dataset not found: {path} (check dataset.path in template.json)")
    key = (str(path), path.stat().st_mtime_ns)
    cached = _DATASET_CACHE.get(key)
    if cached is not None:
        return cached

    # keep_default_na=False is deliberate: pandas otherwise treats the literal
    # strings "None" / "NA" / "nan" as missing, which silently deleted the most
    # common value of the food template's "event" column. Only empty cells are NA.
    frame = pd.read_csv(path, encoding="utf-8-sig", keep_default_na=False, na_values=[""])
    if frame.empty:
        raise TemplateError(f"dataset is empty: {path}")

    target = template["dataset"]["target"]
    if target not in frame.columns:
        raise TemplateError(
            f"dataset.target '{target}' is not a column in {path.name}; "
            f"available: {', '.join(map(str, frame.columns))}"
        )
    frame[target] = pd.to_numeric(frame[target], errors="coerce")
    frame = frame.dropna(subset=[target]).reset_index(drop=True)

    _DATASET_CACHE.clear()
    _DATASET_CACHE[key] = frame
    return frame


def field_options(template: dict) -> dict[str, list]:
    """Resolve every field's dropdown values.

    dataset-sourced fields list the distinct values of their column (so a new
    menu item in the CSV shows up in the UI with no code change).
    """
    frame = None
    options: dict[str, list] = {}
    for field in template["fields"]:
        if field["source"] in ("static", "input"):
            options[field["name"]] = list(field.get("options") or [])
            continue
        if frame is None:
            frame = dataset_frame(template)
        column = field["column"]
        if column not in frame.columns:
            raise TemplateError(
                f"field '{field['name']}' points at dataset column '{column}', "
                f"but {dataset_path(template).name} has: {', '.join(map(str, frame.columns))}"
            )
        values = frame[column].dropna().unique().tolist()
        options[field["name"]] = sorted(values, key=lambda value: str(value))
    return options


def dataset_meta(template: dict) -> dict:
    """Small summary the UI shows under the form."""
    frame = dataset_frame(template)
    dataset = template["dataset"]
    target = dataset["target"]
    meta = {
        "rows": int(len(frame)),
        "target": target,
        "target_label": dataset.get("target_label", target),
        "unit": dataset.get("unit", ""),
        "target_mean": round(float(frame[target].mean()), 2),
    }
    date_column = dataset.get("date_column")
    if date_column and date_column in frame.columns:
        dates = pd.to_datetime(frame[date_column], errors="coerce").dropna()
        if not dates.empty:
            meta["date_min"] = dates.min().date().isoformat()
            meta["date_max"] = dates.max().date().isoformat()
    return meta


def get_config() -> dict:
    """Payload for GET /api/config: everything the frontend needs in one call."""
    template = load_template()
    return {
        "template": template,
        "options": field_options(template),
        "dataset": dataset_meta(template),
    }


def clear_cache() -> None:
    """Drop cached templates/datasets (tests and hot reloads)."""
    _TEMPLATE_CACHE.clear()
    _DATASET_CACHE.clear()
