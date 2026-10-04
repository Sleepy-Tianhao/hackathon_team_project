"""Zero-dependency HTTP server for the dashboard and JSON API.

Why this exists: the intended runtime is FastAPI (backend.main), but a hackathon
demo must survive a show floor with no network and no ability to pip install
anything. This module serves the exact same /api contract using only the Python
standard library, so the project runs with what already ships:

    python -m backend.server --port 8000

Both entry points delegate to backend.service, so behaviour cannot drift.
"""
from __future__ import annotations

import argparse
import json
import os
import threading
import traceback
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

try:  # package import: python -m backend.server
    from . import service
    from .database import BASE_DIR, SessionLocal, ensure_seeded
except ImportError:  # direct execution: python backend/server.py
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from backend import service
    from backend.database import BASE_DIR, SessionLocal, ensure_seeded

FRONTEND_DIR = BASE_DIR / "frontend"
STATIC_WHITELIST = {
    "index.html": "text/html; charset=utf-8",
    "style.css": "text/css; charset=utf-8",
    "app.js": "application/javascript; charset=utf-8",
    # Archived analytics dashboard, kept for reference. Safe to delete along
    # with these three entries.
    "legacy/index.html": "text/html; charset=utf-8",
    "legacy/style.css": "text/css; charset=utf-8",
    "legacy/app.js": "application/javascript; charset=utf-8",
}
JSON_HEADERS = {"Cache-Control": "no-store", "Access-Control-Allow-Origin": "*"}


# --------------------------------------------------------------------------- #
# query parameter reading
# --------------------------------------------------------------------------- #
class Params:
    """Typed, validating access to the query string."""

    def __init__(self, raw: dict[str, list[str]]) -> None:
        self._raw = raw

    def string(self, name: str, default: str | None = None) -> str | None:
        values = self._raw.get(name)
        if not values or values[0] == "":
            return default
        return values[0]

    def integer(self, name: str, default: int) -> int:
        value = self.string(name)
        if value is None:
            return default
        try:
            return int(value)
        except ValueError as exc:
            raise service.ServiceError(f"{name} must be an integer") from exc

    def boolean(self, name: str, default: bool) -> bool:
        value = self.string(name)
        if value is None:
            return default
        return value.strip().lower() in ("1", "true", "yes", "on")

    def iso_date(self, name: str) -> date | None:
        value = self.string(name)
        if value is None:
            return None
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise service.ServiceError(f"{name} must be an ISO date (YYYY-MM-DD)") from exc


# --------------------------------------------------------------------------- #
# routes
# --------------------------------------------------------------------------- #
def _health(params: Params, db) -> dict:
    return service.get_health(db)


def _filters(params: Params, db) -> dict:
    return service.get_filters(db)


def _summary(params: Params, db) -> dict:
    return service.get_summary(db, store=params.string("store"), category=params.string("category"),
                               start=params.iso_date("start"), end=params.iso_date("end"))


def _timeseries(params: Params, db) -> dict:
    return service.get_timeseries(db, granularity=params.string("granularity", "day"),
                                  store=params.string("store"), category=params.string("category"),
                                  start=params.iso_date("start"), end=params.iso_date("end"))


def _breakdown(params: Params, db) -> dict:
    return service.get_breakdown(db, dimension=params.string("dimension", "category"),
                                 store=params.string("store"), category=params.string("category"),
                                 start=params.iso_date("start"), end=params.iso_date("end"))


def _momentum(params: Params, db) -> dict:
    return service.get_momentum(db, dimension=params.string("dimension", "category"),
                                window=params.integer("window", 30),
                                store=params.string("store"), category=params.string("category"))


def _sales(params: Params, db) -> dict:
    return service.get_sales(db, store=params.string("store"), category=params.string("category"),
                             start=params.iso_date("start"), end=params.iso_date("end"),
                             page=params.integer("page", 1),
                             page_size=params.integer("page_size", service.DEFAULT_PAGE_SIZE))


def _anomalies(params: Params, db) -> dict:
    return service.get_anomalies(db, store=params.string("store"), category=params.string("category"),
                                 days=params.integer("days", 90))


def _forecast(params: Params, db) -> dict:
    return service.get_forecast(db, store=params.string("store"), category=params.string("category"),
                                horizon=params.integer("horizon", 30))


def _predictions(params: Params, db) -> dict:
    return service.get_predictions(db, limit=params.integer("limit", 10))


def _insights(params: Params, db) -> dict:
    return service.get_insights(db, store=params.string("store"), category=params.string("category"),
                                start=params.iso_date("start"), end=params.iso_date("end"),
                                horizon=params.integer("horizon", 30),
                                use_llm=params.boolean("use_llm", True))


def _predict(params: Params, db, body) -> dict:
    return service.run_prediction(body, db=db)


ROUTES = {
    "/api/config": lambda params, db: service.get_config(),
    "/api/options": lambda params, db: service.get_field_options(),
    "/api/health": _health,
    "/api/filters": _filters,
    "/api/summary": _summary,
    "/api/timeseries": _timeseries,
    "/api/breakdown": _breakdown,
    "/api/momentum": _momentum,
    "/api/sales": _sales,
    "/api/anomalies": _anomalies,
    "/api/forecast": _forecast,
    "/api/predictions": _predictions,
    "/api/insights": _insights,
}

# Routes that accept a JSON body (POST).
POST_ROUTES = {
    "/api/predict": _predict,
}

MAX_BODY_BYTES = 1 << 20


# --------------------------------------------------------------------------- #
# request handler
# --------------------------------------------------------------------------- #
class ApiHandler(BaseHTTPRequestHandler):
    server_version = "SDC-Hackathon/1.0"
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802 - the name is mandated by the base class
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path == "/api" or path.startswith("/api/"):
            self._handle_api(path, parsed.query)
        else:
            self._handle_static(path)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        for key, value in JSON_HEADERS.items():
            self.send_header(key, value)
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path).rstrip("/")
        # Always drain the body first: an unconsumed body would corrupt the next
        # request on a keep-alive connection.
        try:
            body = self._read_json_body()
        except service.ServiceError as exc:
            self._json(exc.status, {"detail": exc.detail})
            return

        if path in POST_ROUTES:
            self._dispatch(POST_ROUTES, path, parsed.query, body=body)
        elif path in ROUTES:
            self._json(405, {"detail": f"{path} only supports GET"})
        else:
            self._json(404, {"detail": f"unknown endpoint {parsed.path}", "available": sorted(ROUTES)})

    # -- helpers ------------------------------------------------------------ #
    def _handle_api(self, path: str, query: str) -> None:
        route = path.rstrip("/")
        if route in ROUTES:
            self._dispatch(ROUTES, route, query)
        elif route in POST_ROUTES:
            self._json(405, {"detail": f"{route} only supports POST"})
        else:
            self._json(404, {"detail": f"unknown endpoint {path}", "available": sorted(ROUTES)})

    def _dispatch(self, routes: dict, route: str, query: str, body=None) -> None:
        handler = routes[route]
        params = Params(parse_qs(query))
        db = SessionLocal()
        try:
            payload = handler(params, db, body) if body is not None else handler(params, db)
            self._json(200, payload)
        except service.ServiceError as exc:
            self._json(exc.status, {"detail": exc.detail})
        except Exception:  # pragma: no cover - defensive
            traceback.print_exc()
            self._json(500, {"detail": "internal server error"})
        finally:
            db.close()

    def _read_json_body(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError as exc:
            raise service.ServiceError("invalid Content-Length", 400) from exc
        if length <= 0:
            return {}
        if length > MAX_BODY_BYTES:
            raise service.ServiceError("request body too large", 413)
        raw = self.rfile.read(length)
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise service.ServiceError(f"请求体不是合法 JSON: {exc}", 400) from exc

    def _handle_static(self, path: str) -> None:
        name = path.strip("/") or "index.html"
        content_type = STATIC_WHITELIST.get(name)
        if content_type is None:
            self._json(404, {"detail": f"{path} not found"})
            return
        target = FRONTEND_DIR / name
        if not target.is_file():
            self._json(404, {"detail": f"{name} not found"})
            return
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=_json_default).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for key, value in JSON_HEADERS.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:  # keep the console readable
        if os.getenv("API_VERBOSE") == "1":
            super().log_message(fmt, *args)


def _json_default(value):
    """Last-resort encoder for numpy scalars and dates."""
    if hasattr(value, "item"):
        return value.item()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


# --------------------------------------------------------------------------- #
# entry point
# --------------------------------------------------------------------------- #
def build_server(host: str = "127.0.0.1", port: int = 8000) -> ThreadingHTTPServer:
    """Create (but do not start) the HTTP server - handy for tests."""
    return ThreadingHTTPServer((host, port), ApiHandler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the sales analytics API with no external dependencies")
    parser.add_argument("--host", default=os.getenv("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    args = parser.parse_args()

    inserted = ensure_seeded()
    if inserted:
        print(f"[server] seeded {inserted} sales rows from data/sales.csv")

    # Fit the forecast models in the background: the dashboard is usable
    # immediately and the first forecast click is already warm.
    threading.Thread(target=service.warm_up, name="warm-up", daemon=True).start()

    httpd = build_server(args.host, args.port)
    host, port = httpd.server_address[0], httpd.server_address[1]
    print(f"[server] dashboard  http://{host}:{port}/")
    print(f"[server] api        http://{host}:{port}/api/health")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[server] shutting down")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
