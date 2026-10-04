/* Minimal template UI: render everything from /api/config, predict via POST /api/predict.
   No field name is hardcoded here - add a field in template.json and it appears. */
(function () {
  "use strict";

  var state = { template: null, options: {}, busy: false };

  function byId(id) { return document.getElementById(id); }

  function esc(value) {
    return String(value === undefined || value === null ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function api(path, options) {
    return fetch(path, options || {}).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (body) {
        if (!response.ok) throw new Error(body.detail || ("HTTP " + response.status));
        return body;
      });
    });
  }

  /* ------------------------------------------------------------- rendering */
  function renderShell(config) {
    var app = config.template.app || {};
    var output = config.template.output || {};
    state.template = config.template;
    state.options = config.options || {};

    document.title = app.title || "Forecast";
    byId("brand").textContent = app.brand || "";
    byId("app-title").textContent = app.title || "";
    byId("app-subtitle").textContent = app.subtitle || "";
    byId("footer").textContent = app.footer || "";
    byId("explain-title").textContent = output.explanation_title || "AI Explanation";

    var fields = config.template.fields || [];
    byId("fields").innerHTML = fields.map(function (field) {
      return fieldRow(field, state.options[field.name] || []);
    }).join("");

    fields.forEach(function (field) {
      var element = document.querySelector('[name="' + field.name + '"]');
      if (element && field.default !== null && field.default !== undefined) {
        element.value = String(field.default);
      }
    });

    var submit = byId("submit");
    submit.textContent = output.submit_label || "Predict";
    submit.disabled = false;
  }

  function fieldRow(field, options) {
    return '<div class="row">'
      + '<label class="row-label" for="field-' + esc(field.name) + '" title="' + esc(field.help || "") + '">'
      + esc(field.label) + '</label>'
      + control(field, options)
      + '</div>';
  }

  function control(field, options) {
    var id = "field-" + field.name;
    var name = esc(field.name);

    if (options && options.length) {
      var items = options.map(function (value) {
        return '<option value="' + esc(value) + '">' + esc(value) + '</option>';
      }).join("");
      if (!field.required) items = '<option value="">—</option>' + items;
      return '<select id="' + id + '" name="' + name + '">' + items + '</select>';
    }

    var type = field.type === "number" ? "number" : "text";
    var extra = "";
    if (field.min !== undefined && field.min !== null) extra += ' min="' + esc(field.min) + '"';
    if (field.max !== undefined && field.max !== null) extra += ' max="' + esc(field.max) + '"';
    return '<input id="' + id + '" name="' + name + '" type="' + type + '"' + extra
      + ' placeholder="' + esc(field.suffix || "") + '" />';
  }

  function collect() {
    var values = {};
    (state.template.fields || []).forEach(function (field) {
      var element = document.querySelector('[name="' + field.name + '"]');
      if (element) values[field.name] = element.value;
    });
    return values;
  }

  /* ---------------------------------------------------------------- submit */
  function submit(event) {
    event.preventDefault();
    if (state.busy) return;
    setBusy(true);
    byId("form-error").hidden = true;

    api("/api/predict", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fields: collect() })
    })
      .then(renderResult)
      .catch(function (error) { showError(error.message); })
      .then(function () { setBusy(false); });
  }

  function setBusy(busy) {
    state.busy = busy;
    var submitButton = byId("submit");
    var label = (state.template && state.template.output && state.template.output.submit_label) || "Predict";
    submitButton.disabled = busy;
    submitButton.textContent = busy ? "计算中…" : label;
  }

  function showError(message) {
    var element = byId("form-error");
    element.textContent = message;
    element.hidden = false;
  }

  function renderResult(payload) {
    byId("result-headline").textContent = payload.headline || "";
    byId("result-value").textContent = payload.formatted || String(payload.value);
    byId("result-unit").textContent = payload.unit || "";

    var delta = byId("result-delta");
    var arrow = payload.direction === "up" ? "▲ " : (payload.direction === "down" ? "▼ " : "");
    delta.textContent = payload.delta_text ? arrow + payload.delta_text : "";
    delta.className = "result-delta " + (payload.direction || "flat");

    byId("result-explanation").textContent = payload.explanation || "—";

    var parts = [];
    if (payload.model) parts.push("model: " + payload.model);
    if (payload.explanation_source) parts.push("source: " + payload.explanation_source);
    if (payload.baseline !== null && payload.baseline !== undefined) {
      parts.push("baseline: " + payload.baseline + " " + (payload.unit || "")
        + (payload.delta_label ? " (" + payload.delta_label + ")" : ""));
    }
    var meta = payload.meta || {};
    if (meta.elapsed_ms !== undefined) parts.push(meta.elapsed_ms + " ms");

    byId("result-meta").innerHTML = esc(parts.join("  ·  "))
      + (meta.fallback ? '  <span class="warn">外部模型不可用，已本地回退</span>' : "");

    byId("result").hidden = false;
  }

  /* ------------------------------------------------------------------ boot */
  function boot() {
    api("/api/config")
      .then(renderShell)
      .then(function () { byId("form").addEventListener("submit", submit); })
      .catch(function (error) {
        byId("app-title").textContent = "配置加载失败";
        byId("app-subtitle").textContent = error.message;
        showError(error.message);
      });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
