"""End-to-end tests for the sales analytics API.

Works with pytest when it is installed, and with the standard library alone:

    python -m unittest discover -s tests -v
    python tests/test_api.py

Two layers are covered:

* backend.service  - KPIs, aggregation, forecasting, insights (direct calls)
* backend.server   - the standard-library HTTP server, end to end (routing,
                     JSON encoding, error status codes, static dashboard files)
"""
from __future__ import annotations

import json
import os
import shutil
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# Configure the environment before importing the backend: database.py reads
# DATABASE_URL at import time, so tests must point it at a throwaway file.
# The directory lives inside the project so it works under sandboxed execution
# where the system temp directory is not writable.
TMP_DIR = Path(__file__).resolve().parent / "_tmp"
TMP_DIR.mkdir(parents=True, exist_ok=True)
os.environ["DATABASE_URL"] = "sqlite:///" + (TMP_DIR / "test.db").as_posix()
os.environ["SKIP_DB_SEED"] = "1"        # seed explicitly in setUpModule
os.environ["FORECAST_FAST"] = "1"       # Ridge only: keeps the suite quick
os.environ.pop("OPENAI_API_KEY", None)  # never call an LLM from tests

from backend import check_data, database, predictor, server, service, template_config  # noqa: E402
from backend.database import SessionLocal  # noqa: E402

SEEDED_ROWS = 0

# The default template is the campus energy-consumption one, which is what
# frontend/js/config.js is themed for. Food demand and retail sales are the
# alternates; food demand doubles as the regression case for the literal "None"
# value, and retail sales exercises the bundled scikit-learn plugin.
FOOD_TEMPLATE = "templates/food-demand.json"
RETAIL_TEMPLATE = "templates/retail-sales.json"
ENERGY_FORM = {"building": "Teaching Block A", "day_type": "Weekday",
               "weather": "Sunny", "term_phase": "Term", "notes": ""}
FOOD_FORM = {"menu": "Chicken Rice", "day": "Friday", "weather": "Rain",
             "event": "None", "notes": ""}
RETAIL_FORM = {"store": "上海旗舰店", "category": "智能手机", "horizon": "30"}


@contextmanager
def temporary_env(**values):
    """Set/unset environment variables for one test, then restore them."""
    saved = {key: os.environ.get(key) for key in values}
    try:
        for key, value in values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class StubModelHandler(BaseHTTPRequestHandler):
    """A stand-in for a user's own model service."""

    payload: dict = {}
    status: int = 200
    last_request: dict = {}

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            type(self).last_request = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            type(self).last_request = {}
        body = json.dumps(type(self).payload).encode("utf-8")
        self.send_response(type(self).status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:
        pass


def setUpModule() -> None:
    global SEEDED_ROWS
    os.environ.pop("OPENAI_API_KEY", None)  # guards against a key loaded from .env
    database.init_db()
    SEEDED_ROWS = database.load_csv()


def tearDownModule() -> None:
    predictor.clear_cache()
    try:  # release the SQLite file handle before deleting the scratch directory
        database.engine.dispose()
    except Exception:
        pass
    shutil.rmtree(TMP_DIR, ignore_errors=True)


class SalesDataTestCase(unittest.TestCase):
    """Shared read-only session plus a few guards."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.db = SessionLocal()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.db.close()

    def setUp(self) -> None:
        self.assertGreater(SEEDED_ROWS, 0, "data/sales.csv must be seeded for the tests")


class TestServiceLayer(SalesDataTestCase):
    def test_health_reports_seeded_rows(self) -> None:
        health = service.get_health(self.db)
        self.assertEqual(health["status"], "ok")
        self.assertEqual(health["rows"], SEEDED_ROWS)
        self.assertEqual(health["date_min"], "2024-01-01")
        self.assertEqual(health["date_max"], "2025-12-31")
        self.assertFalse(health["llm_configured"])

    def test_filters_expose_dimension_values(self) -> None:
        filters = service.get_filters(self.db)
        self.assertEqual(len(filters["stores"]), 4)
        self.assertEqual(len(filters["categories"]), 5)
        self.assertEqual(len(filters["series"]), 20)
        self.assertIn("month", filters["granularities"])
        self.assertGreaterEqual(filters["horizon_max"], 30)

    def test_summary_matches_raw_database_totals(self) -> None:
        summary = service.get_summary(self.db)
        expected = predictor.get_frame(self.db)["revenue"].sum()
        self.assertAlmostEqual(summary["kpis"]["revenue"], round(float(expected), 2), places=2)
        self.assertEqual(summary["range"]["start"], "2024-01-01")
        self.assertEqual(summary["range"]["end"], "2025-12-31")
        self.assertEqual(summary["range"]["days"], 731)
        self.assertEqual(len(summary["breakdown"]["store"]), 4)
        self.assertEqual(len(summary["breakdown"]["category"]), 5)

    def test_summary_scope_filter_is_applied(self) -> None:
        full = service.get_summary(self.db)
        scoped = service.get_summary(self.db, store="上海旗舰店")
        self.assertLess(scoped["kpis"]["revenue"], full["kpis"]["revenue"])
        self.assertEqual({item["name"] for item in service.get_summary(self.db, store="上海旗舰店")["breakdown"]["store"]},
                         {"上海旗舰店"})

    def test_summary_growth_uses_previous_period(self) -> None:
        # Compare two equal-length adjacent windows by hand.
        first = service.get_summary(self.db, start="2024-01-01", end="2024-01-31")
        second = service.get_summary(self.db, start="2024-02-01", end="2024-03-02")
        manual = round(second["kpis"]["revenue"] / first["kpis"]["revenue"] - 1, 4)
        self.assertAlmostEqual(second["growth"]["revenue"], manual, places=4)

    def test_summary_unknown_scope_raises_404(self) -> None:
        with self.assertRaises(service.ServiceError) as ctx:
            service.get_summary(self.db, store="不存在的门店")
        self.assertEqual(ctx.exception.status, 404)

    def test_timeseries_buckets_reconcile_with_total(self) -> None:
        total = service.get_summary(self.db)["kpis"]["revenue"]
        for granularity in ("day", "week", "month"):
            points = service.get_timeseries(self.db, granularity=granularity)["points"]
            self.assertTrue(points)
            self.assertAlmostEqual(sum(p["revenue"] for p in points), total, places=2)
        self.assertEqual(len(service.get_timeseries(self.db, granularity="month")["points"]), 24)
        self.assertEqual(len(service.get_timeseries(self.db, granularity="day")["points"]), 731)

    def test_timeseries_rejects_bad_granularity(self) -> None:
        with self.assertRaises(service.ServiceError):
            service.get_timeseries(self.db, granularity="hour")

    def test_breakdown_shares_sum_to_one(self) -> None:
        for dimension in ("category", "store"):
            items = service.get_breakdown(self.db, dimension=dimension)["items"]
            self.assertAlmostEqual(sum(item["share"] for item in items), 1.0, places=3)
            self.assertEqual(items, sorted(items, key=lambda item: item["revenue"], reverse=True))

    def test_sales_pagination(self) -> None:
        first = service.get_sales(self.db, page=1, page_size=10)
        second = service.get_sales(self.db, page=2, page_size=10)
        self.assertEqual(first["total"], SEEDED_ROWS)
        self.assertEqual(first["pages"], (SEEDED_ROWS + 9) // 10)
        self.assertEqual(len(first["items"]), 10)
        self.assertEqual(len(second["items"]), 10)
        dates = [item["date"] for item in first["items"]]
        self.assertEqual(dates, sorted(dates, reverse=True))
        # Newest first, so the last row of page 1 is never older than page 2's first.
        self.assertGreaterEqual(first["items"][-1]["date"], second["items"][0]["date"])
        self.assertTrue(all(item["revenue"] > 0 for item in first["items"]))

    def test_sales_validates_paging_bounds(self) -> None:
        with self.assertRaises(service.ServiceError):
            service.get_sales(self.db, page=0)
        with self.assertRaises(service.ServiceError):
            service.get_sales(self.db, page_size=5000)

    def test_momentum_window_validation(self) -> None:
        items = service.get_momentum(self.db, window=30)["items"]
        self.assertEqual(len(items), 5)
        self.assertTrue(all("change" in item for item in items))
        with self.assertRaises(service.ServiceError):
            service.get_momentum(self.db, window=3)

    def test_anomalies_are_reported_within_window(self) -> None:
        payload = service.get_anomalies(self.db, days=120)
        self.assertEqual(payload["window_days"], 120)
        for item in payload["anomalies"]:
            self.assertGreaterEqual(abs(item["zscore"]), 2.5)
            self.assertIn(item["direction"], ("spike", "drop"))

    def test_forecast_shape_interval_and_metrics(self) -> None:
        result = service.get_forecast(self.db, horizon=14)
        self.assertEqual(result["horizon"], 14)
        self.assertEqual(len(result["points"]), 14)
        self.assertEqual(result["series_count"], 20)

        dates = [point["date"] for point in result["points"]]
        self.assertEqual(dates, sorted(dates))
        self.assertEqual(dates[0], "2026-01-01")  # last data day is 2025-12-31

        for point in result["points"]:
            self.assertGreaterEqual(point["revenue"], 0)
            self.assertLessEqual(point["revenue_lower"], point["revenue"])
            self.assertGreaterEqual(point["revenue_upper"], point["revenue"])

        self.assertAlmostEqual(result["totals"]["revenue"], sum(p["revenue"] for p in result["points"]), places=2)

        metrics = result["model"]["revenue"]
        self.assertIn(metrics["model"], ("Ridge", "ExtraTrees"))
        self.assertGreater(metrics["mape"], 0)
        self.assertLess(metrics["mape"], 0.5)          # a sane error rate
        self.assertIsNotNone(metrics["baseline_mape"])
        self.assertGreater(metrics["train_rows"], 1000)
        self.assertTrue(result["by_series"])
        self.assertEqual(len(result["history"]), 60)

    def test_forecast_is_positive_and_plausible(self) -> None:
        result = service.get_forecast(self.db, horizon=30)
        daily = result["totals"]["avg_daily_revenue"]
        historical = service.get_summary(self.db)["kpis"]["avg_daily_revenue"]
        # The synthetic data grows over time, so the forecast should be in the
        # right order of magnitude rather than absurd.
        self.assertGreater(daily, historical * 0.5)
        self.assertLess(daily, historical * 2.5)
        self.assertEqual(result["peak"]["date"],
                         max(result["points"], key=lambda p: p["revenue"])["date"])

    def test_forecast_scope_restricts_series(self) -> None:
        result = service.get_forecast(self.db, store="上海旗舰店", category="智能手机", horizon=7)
        self.assertEqual(result["series_count"], 1)
        self.assertEqual({item["series"] for item in result["by_series"]}, {"上海旗舰店 / 智能手机"})

    def test_forecast_horizon_validation(self) -> None:
        for horizon in (0, -3, service.MAX_HORIZON + 1):
            with self.assertRaises(service.ServiceError):
                service.get_forecast(self.db, horizon=horizon)

    def test_forecast_is_audited(self) -> None:
        before = len(service.get_predictions(self.db, limit=50)["runs"])
        service.get_forecast(self.db, horizon=5)
        after = service.get_predictions(self.db, limit=50)["runs"]
        self.assertGreater(len(after), before)
        self.assertEqual(after[0]["horizon"], 5)
        self.assertIn("model_name", after[0])

    def test_insights_contain_rules_and_narrative(self) -> None:
        payload = service.get_insights(self.db, horizon=14)
        self.assertEqual(payload["narrative_source"], "rules")
        self.assertGreater(len(payload["narrative"]), 10)
        self.assertGreaterEqual(len(payload["insights"]), 4)
        kinds = {item["kind"] for item in payload["insights"]}
        self.assertTrue({"growth", "promotion", "concentration"} & kinds)
        for item in payload["insights"]:
            self.assertTrue(item["title"])
            self.assertTrue(item["detail"])
            self.assertIn(item["severity"], ("critical", "warning", "positive", "info"))
        severities = [item["severity"] for item in payload["insights"]]
        rank = {"critical": 0, "warning": 1, "positive": 2, "info": 3}
        self.assertEqual(severities, sorted(severities, key=lambda s: rank[s]))

    def test_insights_include_forecast_context(self) -> None:
        payload = service.get_insights(self.db, horizon=21)
        self.assertTrue(any(item["kind"] == "forecast" for item in payload["insights"]))

    def test_anomaly_insight_when_present(self) -> None:
        from backend import ai
        self.assertEqual(ai.anomalies_to_insights([]), [])
        insight = ai.anomalies_to_insights([
            {"date": "2025-11-11", "revenue": 999.0, "expected": 100.0, "zscore": 4.2, "direction": "spike"}
        ])[0]
        self.assertEqual(insight["kind"], "anomaly")
        self.assertIn("2025-11-11", insight["detail"])


class TestHttpServer(unittest.TestCase):
    """Drive the standard-library server exactly like the browser does."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.httpd = server.build_server("127.0.0.1", 0)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=5)

    def request(self, path: str, **params):
        url = f"http://127.0.0.1:{self.port}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                return response.status, response.headers.get("Content-Type", ""), response.read()
        except urllib.error.HTTPError as error:
            return error.code, error.headers.get("Content-Type", ""), error.read()

    def get_json(self, path: str, **params):
        status, content_type, body = self.request(path, **params)
        self.assertIn("application/json", content_type)
        return status, json.loads(body.decode("utf-8"))

    def test_health_endpoint(self) -> None:
        status, payload = self.get_json("/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(payload["rows"], SEEDED_ROWS)

    def test_analytics_endpoints(self) -> None:
        status, summary = self.get_json("/api/summary", store="北京中关村店")
        self.assertEqual(status, 200)
        self.assertEqual(summary["scope"]["store"], "北京中关村店")

        status, series = self.get_json("/api/timeseries", granularity="week")
        self.assertEqual(status, 200)
        self.assertTrue(series["points"])

        status, breakdown = self.get_json("/api/breakdown", dimension="store")
        self.assertEqual(status, 200)
        self.assertEqual(len(breakdown["items"]), 4)

        status, table = self.get_json("/api/sales", page=1, page_size=5)
        self.assertEqual(status, 200)
        self.assertEqual(len(table["items"]), 5)

    def test_forecast_and_insights_endpoints(self) -> None:
        status, forecast = self.get_json("/api/forecast", horizon=7)
        self.assertEqual(status, 200)
        self.assertEqual(len(forecast["points"]), 7)

        status, insights = self.get_json("/api/insights", horizon=7)
        self.assertEqual(status, 200)
        self.assertTrue(insights["insights"])

    def test_invalid_parameters_return_400(self) -> None:
        cases = [
            ("/api/forecast", {"horizon": 0}),
            ("/api/forecast", {"horizon": 999}),
            ("/api/timeseries", {"granularity": "hour"}),
            ("/api/sales", {"page_size": 9999}),
            ("/api/sales", {"page": 0}),
            ("/api/summary", {"start": "not-a-date"}),
        ]
        for path, params in cases:
            with self.subTest(path=path, params=params):
                status, payload = self.get_json(path, **params)
                self.assertEqual(status, 400)
                self.assertIn("detail", payload)

    def test_unknown_endpoint_returns_404(self) -> None:
        status, payload = self.get_json("/api/nope")
        self.assertEqual(status, 404)
        self.assertIn("available", payload)

    def test_template_shell_is_served(self) -> None:
        status, content_type, body = self.request("/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", content_type)
        # index.html stays a bare shell: every section is rendered by app.js.
        self.assertIn('id="app"', body.decode("utf-8"))

        status, content_type, _ = self.request("/index.html")
        self.assertEqual(status, 200)
        self.assertIn("text/html", content_type)

    def test_es_modules_and_assets_are_served(self) -> None:
        assets = {
            "/css/style.css": "text/css",
            "/js/app.js": "javascript",
            "/js/config.js": "javascript",
            "/js/components/header.js": "javascript",
            "/js/components/hero.js": "javascript",
            "/js/components/analysis.js": "javascript",
            "/js/services/api.js": "javascript",
        }
        for path, expected in assets.items():
            with self.subTest(asset=path):
                status, content_type, body = self.request(path)
                self.assertEqual(status, 200)
                # Browsers refuse to execute an ES module unless the MIME type is
                # a JavaScript one. This is the regression the test guards.
                self.assertIn(expected, content_type)
                self.assertGreater(len(body), 80)

    # -- helpers ----------------------------------------------------------- #
    def post_json(self, path: str, payload, **params):
        url = f"http://127.0.0.1:{self.port}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(url, data=data, method="POST",
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            raw = error.read()
            try:
                return error.code, json.loads(raw.decode("utf-8"))
            except Exception:
                return error.code, {}

    def start_stub_model(self, payload: dict, status: int = 200):
        handler = type("Stub", (StubModelHandler,),
                       {"payload": payload, "status": status, "last_request": {}})
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()

        def stop():
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=5)

        self.addCleanup(stop)
        return httpd.server_address[1], handler

    def test_path_traversal_is_refused(self) -> None:
        status, _, _ = self.request("/../backend/main.py")
        self.assertIn(status, (400, 404))

    def test_post_is_rejected(self) -> None:
        url = f"http://127.0.0.1:{self.port}/api/health"
        request = urllib.request.Request(url, data=b"{}", method="POST")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                status = response.status
        except urllib.error.HTTPError as error:
            status = error.code
        self.assertEqual(status, 405)


    # -- template contract -------------------------------------------------- #
    def test_config_endpoint_describes_the_ui(self) -> None:
        status, payload = self.get_json("/api/config")
        self.assertEqual(status, 200)
        template = payload["template"]
        self.assertTrue(template["id"])
        self.assertTrue(template["app"]["title"])
        self.assertTrue(template["fields"])
        for field in template["fields"]:
            self.assertIn(field["type"], ("select", "number", "text"))
            self.assertTrue(field["label"])
        self.assertGreater(payload["dataset"]["rows"], 0)
        self.assertTrue(template["output"]["headline"])
        self.assertIn("options", payload)

    def test_options_endpoint_matches_config(self) -> None:
        status, payload = self.get_json("/api/options")
        self.assertEqual(status, 200)
        config = self.get_json("/api/config")[1]
        self.assertEqual(payload["options"], config["options"])

    def test_predict_endpoint_uses_the_configured_model(self) -> None:
        with temporary_env(TEMPLATE_FILE=RETAIL_TEMPLATE):
            status, body = self.post_json("/api/predict", {"fields": dict(RETAIL_FORM)})
        self.assertEqual(status, 200)
        self.assertGreater(body["value"], 0)
        expected = "up" if body["delta"] > 0.005 else ("down" if body["delta"] < -0.005 else "flat")
        self.assertEqual(body["direction"], expected)
        self.assertTrue(body["explanation"])
        self.assertEqual(body["explanation_source"], "ml-forecast")
        self.assertTrue(body["headline"])
        self.assertIn("elapsed_ms", body["meta"])

    def test_predict_endpoint_default_template(self) -> None:
        config = self.get_json("/api/config")[1]
        self.assertEqual(config["template"]["id"], "energy-forecast")
        self.assertIn("Teaching Block A", config["options"]["building"])

        status, body = self.post_json("/api/predict", {"fields": dict(ENERGY_FORM)})

        self.assertEqual(status, 200)
        self.assertGreater(body["value"], 0)
        self.assertEqual(body["unit"], "kWh")
        self.assertEqual(body["model"], "group-baseline")
        self.assertEqual(body["explanation_source"], "local-baseline")
        self.assertTrue(body["evidence"])
        # The explanation must name the very conditions the model used.
        self.assertIn("Teaching Block A", body["explanation"])
        self.assertIn("Sunny", body["explanation"])

    def test_literal_none_stays_a_value(self) -> None:
        """pandas would otherwise read the literal "None" as NaN and silently
        delete the most common value of a column (it broke the food template)."""
        with temporary_env(TEMPLATE_FILE=FOOD_TEMPLATE):
            config = self.get_json("/api/config")[1]
            self.assertEqual(config["template"]["id"], "food-demand")
            self.assertIn("None", config["options"]["event"])

            status, body = self.post_json("/api/predict", {"fields": dict(FOOD_FORM)})
        self.assertEqual(status, 200)
        self.assertIn("None", body["explanation"])

    def test_predict_validation_errors(self) -> None:
        good = dict(ENERGY_FORM)
        cases = [
            ({key: value for key, value in good.items() if key != "weather"}, "缺少必填字段"),
            ({**good, "building": "Penthouse"}, "不在可选范围"),
            ({**good, "day_type": "Caturday"}, "不在可选范围"),
            ({**good, "surprise": 1}, "未知字段"),
        ]
        for fields, expected in cases:
            with self.subTest(fields=fields):
                status, body = self.post_json("/api/predict", {"fields": fields})
                self.assertEqual(status, 422)
                self.assertIn(expected, body["detail"])

    def test_predict_rejects_malformed_bodies(self) -> None:
        status, _ = self.post_json("/api/predict", b"{not json")
        self.assertEqual(status, 400)
        status, _ = self.post_json("/api/predict", {"fields": "not-an-object"})
        self.assertEqual(status, 422)

    def test_predict_methods(self) -> None:
        status, _, _ = self.request("/api/predict")
        self.assertEqual(status, 405)
        status, _ = self.post_json("/api/summary", {})
        self.assertEqual(status, 405)

    def test_external_model_api_is_called_with_the_documented_contract(self) -> None:
        port, handler = self.start_stub_model({
            "value": 640, "unit": "kWh", "baseline": 693,
            "explanation": "Cold weather and a term week keep the lab load above a normal weekday.",
            "model": "load-xgb-v3", "meta": {"version": "test"},
        })
        with temporary_env(MODEL_BACKEND="http", MODEL_API_KEY="secret",
                           MODEL_API_URL=f"http://127.0.0.1:{port}/predict"):
            status, body = self.post_json("/api/predict", {"fields": dict(ENERGY_FORM)})

        self.assertEqual(status, 200)
        self.assertEqual(body["value"], 640)
        self.assertEqual(body["model"], "load-xgb-v3")
        self.assertEqual(body["explanation"], "Cold weather and a term week keep the lab load above a normal weekday.")
        self.assertEqual(body["explanation_source"], "external-api")
        self.assertEqual(body["direction"], "down")
        self.assertIn("lower than normal", body["delta_text"])
        # the external service can say who wrote the words (route 1)
        self.assertEqual(body["meta"]["external_model"], "load-xgb-v3")

        sent = handler.last_request
        self.assertEqual(sent["template_id"], "energy-forecast")
        self.assertEqual(sent["unit"], "kWh")
        self.assertEqual(sent["fields"]["building"], "Teaching Block A")
        self.assertIn("requested_at", sent["context"])

    def test_dead_model_api_falls_back_to_the_local_plugin(self) -> None:
        with temporary_env(MODEL_BACKEND="http", MODEL_API_URL="http://127.0.0.1:1/model",
                           MODEL_API_TIMEOUT="3", MODEL_API_FALLBACK=None):
            status, body = self.post_json("/api/predict", {"fields": dict(ENERGY_FORM)})
        self.assertEqual(status, 200)
        self.assertEqual(body["model"], "group-baseline")
        self.assertTrue(body["meta"]["fallback"])
        self.assertEqual(body["meta"]["requested_plugin"], "http")
        self.assertTrue(body["meta"]["fallback_reason"])

    def test_dead_model_api_can_fail_loudly(self) -> None:
        with temporary_env(MODEL_BACKEND="http", MODEL_API_URL="http://127.0.0.1:1/model",
                           MODEL_API_TIMEOUT="3", MODEL_API_FALLBACK="off"):
            status, body = self.post_json("/api/predict", {"fields": dict(ENERGY_FORM)})
        self.assertEqual(status, 502)
        self.assertIn("模型调用失败", body["detail"])

    def test_unknown_plugin_is_reported(self) -> None:
        with temporary_env(MODEL_BACKEND="does-not-exist"):
            status, body = self.post_json("/api/predict", {"fields": dict(ENERGY_FORM)})
        self.assertEqual(status, 500)
        self.assertIn("unknown model plugin", body["detail"])

    def test_encoded_traversal_is_refused(self) -> None:
        for path in ("/..%2fbackend%2fservice.py", "/js/../../backend/service.py"):
            with self.subTest(path=path):
                status, _, _ = self.request(path)
                self.assertEqual(status, 404)

    # -- /analyze: the contract frontend/js/services/api.js calls ------------ #
    def test_analyze_matches_the_frontend_contract(self) -> None:
        status, body = self.post_json("/analyze", dict(ENERGY_FORM))
        self.assertEqual(status, 200)
        for key in ("prediction", "average", "change_percent", "confidence", "explanation"):
            self.assertIn(key, body)
        self.assertEqual(body["prediction"], body["value"])
        self.assertEqual(body["average"], body["baseline"])
        self.assertAlmostEqual(body["change_percent"], round(body["delta"] * 100, 1), places=1)
        self.assertGreater(body["value"], 0)
        self.assertTrue(body["explanation"])
        self.assertEqual(body["fields"]["building"], "Teaching Block A")

    def test_analyze_requires_post(self) -> None:
        status, _, _ = self.request("/analyze")
        self.assertEqual(status, 405)

    def test_analyze_rejects_unknown_option_values(self) -> None:
        status, body = self.post_json("/analyze", {**ENERGY_FORM, "building": "Penthouse"})
        self.assertEqual(status, 422)
        self.assertIn("不在可选范围", body["detail"])

    def test_free_text_field_is_validated_and_passed_through(self) -> None:
        status, body = self.post_json("/analyze", {**ENERGY_FORM, "notes": "extra context"})
        self.assertEqual(status, 200)
        self.assertEqual(body["fields"]["notes"], "extra context")

        without_notes = {key: value for key, value in ENERGY_FORM.items() if key != "notes"}
        status, body = self.post_json("/analyze", without_notes)
        self.assertEqual(status, 200)
        self.assertEqual(body["fields"]["notes"], "")

    def test_confidence_is_measured_not_invented(self) -> None:
        status, body = self.post_json("/analyze", dict(ENERGY_FORM))
        self.assertEqual(status, 200)
        self.assertIsNotNone(body["confidence"])
        self.assertTrue(0 <= body["confidence"] <= 100)
        self.assertEqual(body["confidence_source"], "backtest-mape")
        backtest = body["meta"]["backtest"]
        self.assertGreater(backtest["samples"], 50)
        self.assertAlmostEqual(body["confidence"], round((1 - backtest["mape"]) * 100), delta=1)
        # the naive reference point ("always assume a normal weekday") is worse
        self.assertGreater(backtest["naive_mae"], backtest["mae"])

    def test_config_exposes_model_summary(self) -> None:
        status, payload = self.get_json("/api/config")
        self.assertEqual(status, 200)
        self.assertEqual(payload["model"]["plugin"], "group-baseline")
        self.assertIn("mape", payload["model"]["backtest"])


class TestCustomData(unittest.TestCase):
    """Bring-your-own-data: the validator, the DATASET_FILE override, and the
    promise that none of it changes the HTTP surface."""

    SAMPLE_CSV = "data/samples/coffee_shop_sales.csv"
    SAMPLE_TEMPLATE = "data/samples/coffee_shop.template.json"

    def tearDown(self) -> None:
        template_config.clear_cache()

    def test_bundled_sample_validates(self) -> None:
        exit_code = check_data.main(["--template", self.SAMPLE_TEMPLATE, "--quiet"])
        self.assertEqual(exit_code, 0)

    def test_bundled_sample_previews_the_unchanged_api(self) -> None:
        exit_code = check_data.main(["--template", self.SAMPLE_TEMPLATE, "--check-api", "--quiet"])
        self.assertEqual(exit_code, 0)

    def test_ad_hoc_mode_needs_no_template(self) -> None:
        exit_code = check_data.main([
            "--csv", self.SAMPLE_CSV, "--target", "cups",
            "--field", "drink", "--field", "weekday", "--quiet",
            "--backtest-days", "30",
        ])
        self.assertEqual(exit_code, 0)

    def test_broken_data_is_rejected(self) -> None:
        path = TMP_DIR / "broken-custom.csv"
        path.write_text(
            "date,drink,cups\n"
            "2025-01-01,Latte,120\n"
            "2025-01-02,Latte,oops\n"
            "01/03/2025,Latte,\n",
            encoding="utf-8",
        )
        exit_code = check_data.main([
            "--csv", str(path), "--target", "cups", "--field", "drink",
            "--backtest-days", "0", "--quiet",
        ])
        self.assertEqual(exit_code, 1)

    def test_sample_writer_produces_data_the_checker_accepts(self) -> None:
        path = TMP_DIR / "generated-sample.csv"
        rows = check_data.write_sample(path, days=45)
        self.assertEqual(rows, 45 * len(check_data.SAMPLE_DRINKS))
        exit_code = check_data.main([
            "--csv", str(path), "--target", "cups", "--field", "drink",
            "--field", "weekday", "--backtest-days", "20", "--quiet",
        ])
        self.assertEqual(exit_code, 0)

    def test_dataset_file_overrides_the_configured_path(self) -> None:
        template = template_config.load_template()
        self.assertGreater(template_config.dataset_meta(template)["rows"], 1000)

        tiny = TMP_DIR / "tiny-load.csv"
        lines = ["date,building,day_type,weather,term_phase,kwh"]
        for index in range(12):
            lines.append(f"2025-01-{index % 9 + 1:02d},Teaching Block A,Weekday,Sunny,Term,{700 + index}")
        tiny.write_text("\n".join(lines) + "\n", encoding="utf-8")

        with temporary_env(DATASET_FILE=str(tiny)):
            template_config.clear_cache()
            self.assertEqual(template_config.dataset_meta(template)["rows"], 12)

        template_config.clear_cache()
        self.assertGreater(template_config.dataset_meta(template)["rows"], 1000)

    def test_dataset_file_can_be_locked(self) -> None:
        template = template_config.load_template()
        with temporary_env(DATASET_FILE="data/samples/coffee_shop_sales.csv", DATASET_FILE_LOCK="1"):
            template_config.clear_cache()
            # locked -> the override is ignored and the configured dataset is used
            self.assertEqual(template_config.dataset_meta(template)["rows"], 3655)
        template_config.clear_cache()

    def test_http_surface_is_unchanged(self) -> None:
        """Custom data must not add, remove or rename a single endpoint."""
        self.assertEqual(set(server.ROUTES), {
            "/api/config", "/api/options", "/api/health", "/api/filters",
            "/api/summary", "/api/timeseries", "/api/breakdown", "/api/momentum",
            "/api/sales", "/api/anomalies", "/api/forecast", "/api/predictions",
            "/api/insights",
        })
        self.assertEqual(set(server.POST_ROUTES), {"/api/predict", "/analyze"})


# --------------------------------------------------------------------------- #
# route 1: local model decides the number, an LLM writes the words
# --------------------------------------------------------------------------- #
COFFEE_TEMPLATE = "data/samples/coffee_shop.template.json"
COFFEE_FIELDS = {"drink": "Latte", "weekday": "Monday", "weather": "Sunny",
                 "term_phase": "Term", "notes": ""}


def post_json_url(url: str, payload, timeout: int = 180):
    data = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST",
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raw = error.read()
        try:
            return error.code, json.loads(raw.decode("utf-8"))
        except Exception:
            return error.code, {}


def start_stub_server(test, payload: dict, status: int = 200):
    """Start a throwaway HTTP endpoint (stands in for an LLM gateway)."""
    handler = type("Stub", (StubModelHandler,),
                   {"payload": payload, "status": status, "last_request": {}})
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    def stop():
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)

    test.addCleanup(stop)
    return httpd.server_address[1], handler


class TestLLMExplainerService(unittest.TestCase):
    """examples/llm_explainer_service.py - the reference service for route 1."""

    def start_explainer(self, use_llm: bool):
        from examples import llm_explainer_service

        httpd, context = llm_explainer_service.build_server("127.0.0.1", 0, use_llm=use_llm)
        port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()

        def stop():
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=5)

        self.addCleanup(stop)
        return port, context

    def test_contract_without_an_llm(self) -> None:
        with temporary_env(TEMPLATE_FILE=COFFEE_TEMPLATE, LLM_API_KEY=None, OPENAI_API_KEY=None):
            port, _ = self.start_explainer(use_llm=True)
            status, body = post_json_url(f"http://127.0.0.1:{port}/predict", {"fields": COFFEE_FIELDS})

        self.assertEqual(status, 200)
        for key in ("value", "baseline", "confidence", "explanation", "model", "meta"):
            self.assertIn(key, body)
        self.assertGreater(body["value"], 0)
        self.assertTrue(0 <= body["confidence"] <= 100)
        self.assertTrue(body["explanation"])
        # without a key it must fall back to the model's own wording, never 500
        self.assertEqual(body["meta"]["explanation_source"], "local-model")

    def test_health_endpoint(self) -> None:
        with temporary_env(TEMPLATE_FILE=COFFEE_TEMPLATE, LLM_API_KEY=None):
            port, _ = self.start_explainer(use_llm=True)
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=30) as response:
                health = json.loads(response.read().decode("utf-8"))
        self.assertEqual(health["status"], "ok")
        self.assertEqual(health["template"], "coffee-shop")
        self.assertFalse(health["llm_enabled"])

    def test_explainer_uses_the_llm_when_reachable(self) -> None:
        stub_port, handler = start_stub_server(
            self, {"choices": [{"message": {"content": "周一晴天建议备足 112 杯。"}}]})

        with temporary_env(TEMPLATE_FILE=COFFEE_TEMPLATE, LLM_API_KEY="test-key",
                           LLM_BASE_URL=f"http://127.0.0.1:{stub_port}/v1", LLM_MODEL="fake-chat"):
            port, _ = self.start_explainer(use_llm=True)
            status, body = post_json_url(f"http://127.0.0.1:{port}/predict", {"fields": COFFEE_FIELDS})

        self.assertEqual(status, 200)
        self.assertEqual(body["meta"]["explanation_source"], "llm")
        self.assertEqual(body["explanation"], "周一晴天建议备足 112 杯。")
        self.assertIn("fake-chat", body["model"])

        # the prompt we sent must carry the conditions and the numbers
        sent = handler.last_request
        prompt = sent["messages"][1]["content"]
        self.assertIn("drink=Latte", prompt)
        self.assertIn("预测值", prompt)
        self.assertEqual(sent["model"], "fake-chat")

    def test_main_app_calls_the_explainer_end_to_end(self) -> None:
        """browser -> /analyze -> http plugin -> our service -> local model."""
        with temporary_env(TEMPLATE_FILE=COFFEE_TEMPLATE, LLM_API_KEY=None, OPENAI_API_KEY=None):
            port, _ = self.start_explainer(use_llm=True)
            with temporary_env(MODEL_BACKEND="http",
                               MODEL_API_URL=f"http://127.0.0.1:{port}/predict"):
                result = service.analyze(COFFEE_FIELDS)

        self.assertEqual(result["explanation_source"], "external-api")
        self.assertEqual(result["meta"]["external_explanation_source"], "local-model")
        self.assertGreater(result["prediction"], 0)
        self.assertTrue(result["explanation"])
        # and the five keys the frontend reads are still present
        for key in ("prediction", "average", "change_percent", "confidence", "explanation"):
            self.assertIn(key, result)

    def test_check_model_api_preflight_succeeds_and_fails(self) -> None:
        with temporary_env(TEMPLATE_FILE=COFFEE_TEMPLATE, LLM_API_KEY=None):
            port, _ = self.start_explainer(use_llm=False)
            with temporary_env(MODEL_BACKEND="http",
                               MODEL_API_URL=f"http://127.0.0.1:{port}/predict"):
                self.assertEqual(check_data.main(["--check-model-api", "--quiet"]), 0)

            with temporary_env(MODEL_BACKEND="http", MODEL_API_URL="http://127.0.0.1:1/predict",
                               MODEL_API_TIMEOUT="3"):
                self.assertEqual(check_data.main(["--check-model-api", "--quiet"]), 1)


class TestTemplateValidation(unittest.TestCase):
    """A broken template.json must fail with a precise message, not a vague 500."""

    def write_template(self, name: str, payload: dict) -> str:
        path = TMP_DIR / name
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        template_config.clear_cache()
        self.addCleanup(template_config.clear_cache)
        return str(path)

    def base_template(self, **overrides) -> dict:
        template = {
            "id": "test",
            "app": {"title": "T", "subtitle": "S"},
            "dataset": {"path": "data/menu_demand.csv", "target": "portions"},
            "model": {"plugin": "group-baseline"},
            "fields": [{"name": "menu", "label": "Menu", "type": "select",
                        "source": "dataset", "column": "menu", "required": True}],
            "output": {"headline": "H", "unit": "u", "delta_label": "d"},
        }
        template.update(overrides)
        return template

    def test_missing_model_block_is_reported(self) -> None:
        payload = self.base_template()
        del payload["model"]
        path = self.write_template("no-model.json", payload)
        with temporary_env(TEMPLATE_FILE=path):
            with self.assertRaises(template_config.TemplateError) as ctx:
                template_config.load_template()
        self.assertIn("model", str(ctx.exception))

    def test_duplicate_field_names_are_reported(self) -> None:
        payload = self.base_template()
        payload["fields"].append(dict(payload["fields"][0]))
        path = self.write_template("dup.json", payload)
        with temporary_env(TEMPLATE_FILE=path):
            with self.assertRaises(template_config.TemplateError) as ctx:
                template_config.load_template()
        self.assertIn("duplicated", str(ctx.exception))

    def test_invalid_json_is_reported(self) -> None:
        path = TMP_DIR / "broken.json"
        path.write_text("{ this is not json", encoding="utf-8")
        template_config.clear_cache()
        self.addCleanup(template_config.clear_cache)
        with temporary_env(TEMPLATE_FILE=str(path)):
            with self.assertRaises(template_config.TemplateError) as ctx:
                template_config.load_template()
        self.assertIn("not valid JSON", str(ctx.exception))

    def test_field_pointing_at_missing_column_is_reported(self) -> None:
        payload = self.base_template()
        payload["fields"][0]["column"] = "nope"
        path = self.write_template("bad-column.json", payload)
        with temporary_env(TEMPLATE_FILE=path):
            template = template_config.load_template()
            with self.assertRaises(template_config.TemplateError) as ctx:
                template_config.field_options(template)
        self.assertIn("nope", str(ctx.exception))

    def test_missing_dataset_is_reported(self) -> None:
        payload = self.base_template()
        payload["dataset"] = {"path": "data/nope.csv", "target": "portions"}
        path = self.write_template("bad-dataset.json", payload)
        with temporary_env(TEMPLATE_FILE=path):
            with self.assertRaises(template_config.TemplateError) as ctx:
                template_config.get_config()
        self.assertIn("dataset not found", str(ctx.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
