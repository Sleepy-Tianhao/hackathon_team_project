"""Route 1 reference service: local model decides the number, an LLM writes the words.

This file IS "你的模型服务". It runs on its own port and is called by the project's
http plugin. It does exactly three things:

  1. compute value / baseline with this repo's local statistics model
     (backtestable: MAPE ~9% on the bundled sample, so the number survives
      a judge asking "why this number?")
  2. hand the conditions + numbers to any OpenAI-compatible LLM, which writes
     one sentence of explanation
  3. return the documented contract: {value, baseline, confidence, explanation, model}

Why the LLM does not produce the number: LLMs are unstable at numeric regression.
The number comes from a model you can backtest; the wording comes from the LLM.

Run it:

    python examples/llm_explainer_service.py --port 9000
    # optional, to actually call an LLM:
    $env:LLM_API_KEY = "sk-..."
    $env:LLM_BASE_URL = "https://api.deepseek.com/v1"
    $env:LLM_MODEL    = "deepseek-chat"

Then point the project at it:

    $env:MODEL_BACKEND  = "http"
    $env:MODEL_API_URL  = "http://127.0.0.1:9000/predict"
    python -m backend.server

No key / no network / LLM error -> it silently falls back to the model's own
sentence, so a live demo never breaks. LLM_DISABLE=1 pins that behaviour.

Only the standard library plus requests is used, so nothing needs installing.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

try:  # run from the repo root: python examples/llm_explainer_service.py
    from backend import model_api, template_config
except ImportError:  # pragma: no cover - direct execution from elsewhere
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from backend import model_api, template_config

SYSTEM_PROMPT = (
    "你是一名零售/食堂运营分析师。根据给定的条件与预测数字，写一句 40-70 字的中文备餐建议："
    "先给结论，再说一个最关键的原因，最后给一条可执行动作。"
    "只使用给定信息，不要编造数据里没有的内容，不要罗列数字清单。"
)

USER_PROMPT = """预测目标：{target_label}（{unit}）
条件：{conditions}
预测值：{value}
正常水平：{baseline}（{baseline_label}）
相对变化：{change}
模型看到的因子：{evidence}

请写一句备餐建议。"""


# --------------------------------------------------------------------------- #
# the local model: decides the number
# --------------------------------------------------------------------------- #
class Explainer:
    """Holds the loaded template/dataset/model and answers /predict."""

    def __init__(self, template: dict, frame, plugin, use_llm: bool, timeout: float) -> None:
        self.template = template
        self.frame = frame
        self.plugin = plugin
        self.use_llm = use_llm
        self.timeout = timeout
        self.llm_base = (os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL")
                         or "https://api.openai.com/v1").rstrip("/")
        self.llm_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
        self.llm_model = os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL") or "deepseek-chat"
        self.llm_calls = 0
        self.llm_failures = 0

    # -- the contract ------------------------------------------------------ #
    def predict(self, body: dict[str, Any]) -> dict[str, Any]:
        fields = body.get("fields") if isinstance(body, dict) else None
        if not isinstance(fields, dict):
            raise ValueError('body must be {"fields": {...}}')

        result = self.plugin.predict(fields, self.frame, db=None)

        explanation = ""
        source = "local-model"
        if self.use_llm:
            explanation, error = self.write_explanation(fields, result)
            if explanation:
                source = "llm"
            else:
                print(f"[explainer] LLM unavailable ({error}); using the model's own wording")

        payload = {
            "value": round(float(result.value), 2),
            "baseline": None if result.baseline is None else round(float(result.baseline), 2),
            "confidence": None if result.confidence is None else round(float(result.confidence) * 100),
            "explanation": explanation or result.explanation,
            "model": f"{result.model} + {self.llm_model}" if source == "llm" else result.model,
            "evidence": result.evidence,
            "meta": {
                "explanation_source": source,
                "template_id": self.template["id"],
                "unit": result.unit,
                "llm_model": self.llm_model if source == "llm" else None,
            },
        }
        return payload

    # -- the LLM: writes the words ----------------------------------------- #
    def write_explanation(self, fields: dict, result) -> tuple[str, str]:
        if not self.llm_key:
            return "", "LLM_API_KEY / OPENAI_API_KEY is not set"

        prompt = self.build_prompt(fields, result)
        import requests  # imported late so the service starts instantly

        self.llm_calls += 1
        try:
            response = requests.post(
                f"{self.llm_base}/chat/completions",
                headers={"Authorization": f"Bearer {self.llm_key}",
                         "Content-Type": "application/json"},
                json={
                    "model": self.llm_model,
                    "temperature": 0.4,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
            text = ((payload.get("choices") or [{}])[0].get("message") or {}).get("content")
            if isinstance(text, str) and text.strip():
                return text.strip(), ""
            return "", "empty response from the LLM"
        except Exception as exc:  # any transport/parse problem -> fall back
            self.llm_failures += 1
            return "", f"{type(exc).__name__}: {exc}"

    def build_prompt(self, fields: dict, result) -> str:
        dataset = self.template["dataset"]
        options = self.template["model"].get("options") or {}
        conditions = "、".join(
            f"{key}={value}" for key, value in fields.items() if value not in ("", None)
        ) or "无"

        if result.baseline:
            delta = float(result.value) / float(result.baseline) - 1.0
            change = f"{'高' if delta >= 0 else '低'} {abs(delta) * 100:.0f}%"
        else:
            change = "未知"

        evidence = "；".join(
            f"{item.get('value')} 的历史均值 {item.get('mean')}"
            for item in (result.evidence or [])
            if isinstance(item, dict) and item.get("used")
        ) or "无"

        return USER_PROMPT.format(
            target_label=dataset.get("target_label", dataset["target"]),
            unit=dataset.get("unit", ""),
            conditions=conditions,
            value=f"{float(result.value):,.0f}",
            baseline=f"{float(result.baseline):,.0f}" if result.baseline else "未知",
            baseline_label=options.get("baseline_label", "正常水平"),
            change=change,
            evidence=evidence,
        )

    def health(self) -> dict:
        return {
            "status": "ok",
            "template": self.template["id"],
            "rows": int(len(self.frame)),
            "model": self.plugin.name,
            "llm_enabled": bool(self.use_llm and self.llm_key),
            "llm_base": self.llm_base,
            "llm_model": self.llm_model,
            "llm_calls": self.llm_calls,
            "llm_failures": self.llm_failures,
        }


# --------------------------------------------------------------------------- #
# HTTP plumbing (standard library only)
# --------------------------------------------------------------------------- #
MAX_BODY = 1 << 20


class ExplainerHandler(BaseHTTPRequestHandler):
    server_version = "LLM-Explainer/1.0"
    protocol_version = "HTTP/1.1"
    context: Explainer = None  # type: ignore[assignment]

    # Paths that exist only as POST. Opening one in a browser sends GET, and a
    # bare "unknown endpoint" makes a healthy service look broken - so answer
    # 405 with the exact shape to send instead.
    POST_ONLY = ("/predict",)

    def do_GET(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path.rstrip("/") or "/"
        if path in ("/", "/health"):
            self._json(200, self.context.health())
        elif path in self.POST_ONLY:
            template_fields = self.context.template.get("fields") or []
            self._json(405, {
                "detail": f"{path} only accepts POST (a browser address bar sends GET)",
                "hint": 'send {"fields": {...}}, or open GET /health in the browser',
                "example": {
                    "method": "POST",
                    "url": f"http://127.0.0.1:{self.server.server_address[1]}{path}",
                    "body": {"fields": {
                        field["name"]: (field.get("default") if field.get("default") is not None else "")
                        for field in template_fields
                    }},
                },
            })
        else:
            self._json(404, {"detail": f"unknown endpoint {path}"})

    def do_POST(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path.rstrip("/")
        if path != "/predict":
            self._read_body()          # drain before answering
            self._json(404, {"detail": f"unknown endpoint {path}"})
            return

        body = self._read_body()
        if body is None:
            return

        try:
            payload = self.context.predict(body)
        except Exception as exc:
            traceback.print_exc()
            self._json(400, {"detail": f"{type(exc).__name__}: {exc}"})
            return
        self._json(200, payload)

    def _read_body(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._json(400, {"detail": "invalid Content-Length"})
            return None
        if length <= 0:
            return {}
        if length > MAX_BODY:
            self._json(413, {"detail": "request body too large"})
            return None
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self._json(400, {"detail": f"body is not valid JSON: {exc}"})
            return None

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:
        if os.getenv("EXPLAINER_VERBOSE") == "1":
            super().log_message(fmt, *args)


# --------------------------------------------------------------------------- #
# wiring
# --------------------------------------------------------------------------- #
def load_explainer(use_llm: bool = True, timeout: float = 20.0) -> Explainer:
    """Load the active template and build the local model ONCE, at startup.

    The local plugin is instantiated directly instead of going through
    resolve_model(): otherwise MODEL_BACKEND=http (which you need set for the main
    app) would make this service call itself in a loop.
    """
    template = template_config.load_template()
    frame = template_config.dataset_frame(template)
    plugin = model_api.GroupBaselineModel(template, template["model"].get("options") or {})
    return Explainer(template, frame, plugin, use_llm, timeout)


def build_server(host: str = "127.0.0.1", port: int = 9000, use_llm: bool = True,
                 timeout: float = 20.0) -> tuple[ThreadingHTTPServer, Explainer]:
    context = load_explainer(use_llm=use_llm, timeout=timeout)
    handler = type("BoundExplainerHandler", (ExplainerHandler,), {"context": context})
    return ThreadingHTTPServer((host, port), handler), context


def main() -> None:
    parser = argparse.ArgumentParser(description="Route 1: local model + LLM explanation service")
    parser.add_argument("--host", default=os.getenv("EXPLAINER_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("EXPLAINER_PORT", "9000")))
    parser.add_argument("--no-llm", action="store_true",
                        help="never call an LLM (offline demo / rehearsal)")
    parser.add_argument("--llm-timeout", type=float, default=float(os.getenv("LLM_TIMEOUT", "20")))
    args = parser.parse_args()

    use_llm = not args.no_llm and os.getenv("LLM_DISABLE", "").strip() not in ("1", "true", "yes")
    httpd, context = build_server(args.host, args.port, use_llm=use_llm, timeout=args.llm_timeout)
    host, port = httpd.server_address[0], httpd.server_address[1]

    health = context.health()
    print(f"[explainer] listening   http://{host}:{port}/predict")
    print(f"[explainer] template    {health['template']}  ({health['rows']:,} rows)")
    print(f"[explainer] local model {health['model']}  (decides the number)")
    if health["llm_enabled"]:
        print(f"[explainer] LLM         {health['llm_model']} @ {health['llm_base']}  (writes the words)")
    else:
        print("[explainer] LLM         disabled -> the model's own wording is returned")
        print("[explainer]             想启用：设 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL 后重启")
    print()
    print("让本项目走这个服务：")
    print(f"  $env:MODEL_BACKEND = 'http'")
    print(f"  $env:MODEL_API_URL = 'http://{host}:{port}/predict'")
    print("  python -m backend.server")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[explainer] shutting down")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
