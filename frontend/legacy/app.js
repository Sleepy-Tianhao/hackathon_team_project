/* SDC Hackathon dashboard: vanilla JS, hand-rolled SVG charts, no CDN. */
(function () {
  "use strict";

  var API = "/api";
  var COLOR = {
    accent: "#5b8cff", accent2: "#22d3ee",
    positive: "#34d399", warning: "#fbbf24", critical: "#f87171"
  };
  var state = {
    store: "", category: "", start: "", end: "",
    granularity: "day", horizon: 30,
    page: 1, pageSize: 10, pages: 1, pending: 0, toastTimer: null
  };

  /* ---------------------------------------------------------------- utils */
  function byId(id) { return document.getElementById(id); }

  function esc(value) {
    return String(value === undefined || value === null ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function num(value) { var n = Number(value); return isFinite(n) ? n : 0; }
  function isNil(value) { return value === null || value === undefined || value === ""; }

  function fmtMoney(value) {
    var n = num(value), abs = Math.abs(n);
    if (abs >= 1e8) return (n / 1e8).toFixed(2) + " 亿";
    if (abs >= 1e4) return (n / 1e4).toFixed(1) + " 万";
    return n.toFixed(0);
  }
  function fmtMoneyRaw(value) {
    return "¥" + num(value).toLocaleString("zh-CN", { maximumFractionDigits: 2 });
  }
  function fmtInt(value) {
    return num(value).toLocaleString("zh-CN", { maximumFractionDigits: 0 });
  }
  function fmtPct(value, digits) {
    if (isNil(value) || !isFinite(Number(value))) return "—";
    return (Number(value) * 100).toFixed(digits === undefined ? 1 : digits) + "%";
  }
  function fmtSignedPct(value) {
    if (isNil(value) || !isFinite(Number(value))) return "—";
    var n = Number(value) * 100;
    return (n >= 0 ? "+" : "") + n.toFixed(1) + "%";
  }
  function deltaClass(value) {
    if (isNil(value) || !isFinite(Number(value))) return "muted";
    return Number(value) >= 0 ? "up" : "down";
  }
  function shortDate(iso) { return String(iso).slice(5); }

  /* Growth needs a comparable previous period; the first period of the dataset
     has none, so render that honestly instead of a bare dash. */
  function growthSegment(value) {
    if (isNil(value) || !isFinite(Number(value))) return '<span class="muted">无对比期</span>';
    return '环比 <span class="' + deltaClass(value) + '">' + fmtSignedPct(value) + '</span>';
  }

  function niceMax(value) {
    if (!isFinite(value) || value <= 0) return 1;
    var exponent = Math.floor(Math.log10(value));
    var base = Math.pow(10, exponent);
    var norm = value / base;
    var factor = norm <= 1 ? 1 : norm <= 1.5 ? 1.5 : norm <= 2 ? 2 : norm <= 2.5 ? 2.5 : norm <= 5 ? 5 : 10;
    return factor * base;
  }

  /* ------------------------------------------------------------------ api */
  function api(path, params) {
    var url = new URL(API + path, window.location.origin);
    Object.keys(params || {}).forEach(function (key) {
      var value = params[key];
      if (value === undefined || value === null || value === "") return;
      url.searchParams.set(key, value);
    });
    return fetch(url.toString(), { cache: "no-store" }).then(function (response) {
      if (response.ok) return response.json();
      return response.json().catch(function () { return {}; }).then(function (body) {
        throw new Error(body.detail || ("请求失败 HTTP " + response.status));
      });
    });
  }

  function safe(promise) {
    return promise.catch(function (error) { toast(error.message); return null; });
  }

  function toast(message) {
    var el = byId("toast");
    el.textContent = message;
    el.hidden = false;
    if (state.toastTimer) clearTimeout(state.toastTimer);
    state.toastTimer = setTimeout(function () { el.hidden = true; }, 5200);
  }

  function beginLoad() {
    state.pending += 1;
    byId("loading").hidden = false;
  }
  function endLoad() {
    state.pending = Math.max(0, state.pending - 1);
    if (state.pending === 0) byId("loading").hidden = true;
  }

  /* --------------------------------------------------------------- charts */
  function emptyChart(message) {
    return '<svg viewBox="0 0 840 300"><text x="420" y="150" text-anchor="middle">' + esc(message) + '</text></svg>';
  }

  function trendChart(points) {
    if (!points || !points.length) return emptyChart("暂无数据");
    var W = 840, H = 300, padL = 70, padR = 20, padT = 18, padB = 38;
    var innerW = W - padL - padR, innerH = H - padT - padB;
    var values = points.map(function (p) { return num(p.revenue); });
    var yMax = niceMax(Math.max.apply(null, values) * 1.06);
    var n = points.length;
    var stepX = n > 1 ? innerW / (n - 1) : 0;
    var xOf = function (i) { return padL + i * stepX; };
    var yOf = function (v) { return padT + innerH * (1 - v / yMax); };

    var line = [], i;
    for (i = 0; i < n; i++) {
      line.push((i === 0 ? "M " : "L ") + xOf(i).toFixed(2) + " " + yOf(values[i]).toFixed(2));
    }
    var baseline = padT + innerH;
    var area = line.join(" ") + " L " + xOf(n - 1).toFixed(2) + " " + baseline + " L " + xOf(0).toFixed(2) + " " + baseline + " Z";

    var grid = "";
    for (i = 0; i <= 4; i++) {
      var tickValue = yMax * i / 4;
      var y = yOf(tickValue);
      grid += '<line class="grid-line" x1="' + padL + '" y1="' + y.toFixed(1) + '" x2="' + (W - padR) + '" y2="' + y.toFixed(1) + '"></line>';
      grid += '<text x="' + (padL - 10) + '" y="' + (y + 4).toFixed(1) + '" text-anchor="end">' + fmtMoney(tickValue) + '</text>';
    }

    var labels = "";
    var labelCount = Math.min(6, n);
    for (i = 0; i < labelCount; i++) {
      var index = Math.round(i * (n - 1) / Math.max(1, labelCount - 1));
      labels += '<text x="' + xOf(index).toFixed(1) + '" y="' + (H - 12) + '" text-anchor="middle">'
        + esc(shortDate(points[index].period)) + '</text>';
    }

    var dots = "";
    if (n <= 92) {
      for (i = 0; i < n; i++) {
        dots += '<circle class="dot" cx="' + xOf(i).toFixed(2) + '" cy="' + yOf(values[i]).toFixed(2) + '" r="3">'
          + '<title>' + esc(points[i].period) + " · " + fmtMoneyRaw(values[i]) + '</title></circle>';
      }
    }

    return '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="营收趋势">'
      + '<defs><linearGradient id="areaFill" x1="0" y1="0" x2="0" y2="1">'
      + '<stop offset="0%" stop-color="rgba(91,140,255,0.42)"></stop>'
      + '<stop offset="100%" stop-color="rgba(91,140,255,0.02)"></stop>'
      + '</linearGradient></defs>'
      + grid
      + '<path class="series-area" d="' + area + '"></path>'
      + '<path class="series-line" d="' + line.join(" ") + '"></path>'
      + dots
      + '<line class="axis" x1="' + padL + '" y1="' + baseline + '" x2="' + (W - padR) + '" y2="' + baseline + '"></line>'
      + labels
      + '</svg>';
  }

  function forecastChart(history, points) {
    if (!history || !history.length || !points || !points.length) return emptyChart("暂无预测数据");
    var W = 840, H = 300, padL = 70, padR = 20, padT = 18, padB = 38;
    var innerW = W - padL - padR, innerH = H - padT - padB;
    var nH = history.length, nF = points.length, n = nH + nF;
    var stepX = innerW / Math.max(1, n - 1);
    var xOf = function (i) { return padL + i * stepX; };

    var upperAll = 0, i;
    for (i = 0; i < nH; i++) upperAll = Math.max(upperAll, num(history[i].revenue));
    for (i = 0; i < nF; i++) upperAll = Math.max(upperAll, num(points[i].revenue_upper));
    var yMax = niceMax(upperAll * 1.05);
    var yOf = function (v) { return padT + innerH * (1 - v / yMax); };

    var historyPath = [];
    for (i = 0; i < nH; i++) {
      historyPath.push((i === 0 ? "M " : "L ") + xOf(i).toFixed(2) + " " + yOf(num(history[i].revenue)).toFixed(2));
    }

    var forecastPath = ["M " + xOf(nH - 1).toFixed(2) + " " + yOf(num(history[nH - 1].revenue)).toFixed(2)];
    var upperPath = [], lowerPath = [];
    for (i = 0; i < nF; i++) {
      var index = nH + i;
      forecastPath.push("L " + xOf(index).toFixed(2) + " " + yOf(num(points[i].revenue)).toFixed(2));
      upperPath.push("L " + xOf(index).toFixed(2) + " " + yOf(num(points[i].revenue_upper)).toFixed(2));
      lowerPath.push("L " + xOf(index).toFixed(2) + " " + yOf(num(points[i].revenue_lower)).toFixed(2));
    }
    var bandStart = "M " + xOf(nH - 1).toFixed(2) + " " + yOf(num(history[nH - 1].revenue)).toFixed(2);
    var band = bandStart + " " + upperPath.join(" ") + " " + lowerPath.reverse().join(" ")
      + " L " + xOf(nH - 1).toFixed(2) + " " + yOf(num(history[nH - 1].revenue)).toFixed(2) + " Z";

    var grid = "";
    for (i = 0; i <= 4; i++) {
      var tickValue = yMax * i / 4;
      var y = yOf(tickValue);
      grid += '<line class="grid-line" x1="' + padL + '" y1="' + y.toFixed(1) + '" x2="' + (W - padR) + '" y2="' + y.toFixed(1) + '"></line>';
      grid += '<text x="' + (padL - 10) + '" y="' + (y + 4).toFixed(1) + '" text-anchor="end">' + fmtMoney(tickValue) + '</text>';
    }

    var labels = "";
    var labelCount = 6;
    for (i = 0; i < labelCount; i++) {
      var idx = Math.round(i * (n - 1) / (labelCount - 1));
      var label = idx < nH ? history[idx].date : points[idx - nH].date;
      labels += '<text x="' + xOf(idx).toFixed(1) + '" y="' + (H - 12) + '" text-anchor="middle">' + esc(shortDate(label)) + '</text>';
    }

    var dots = "";
    for (i = 0; i < nF; i++) {
      var pointIndex = nH + i;
      dots += '<circle class="dot forecast" cx="' + xOf(pointIndex).toFixed(2) + '" cy="' + yOf(num(points[i].revenue)).toFixed(2) + '" r="3">'
        + '<title>' + esc(points[i].date) + " · " + fmtMoneyRaw(points[i].revenue)
        + " (区间 " + fmtMoney(points[i].revenue_lower) + " ~ " + fmtMoney(points[i].revenue_upper) + ')</title></circle>';
    }

    return '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="预测曲线">'
      + grid
      + '<path class="band" d="' + band + '"></path>'
      + '<line class="divider" x1="' + xOf(nH - 1).toFixed(2) + '" y1="' + padT + '" x2="' + xOf(nH - 1).toFixed(2) + '" y2="' + (padT + innerH) + '"></line>'
      + '<path class="series-line" d="' + historyPath.join(" ") + '"></path>'
      + '<path class="series-line forecast" d="' + forecastPath.join(" ") + '"></path>'
      + dots
      + '<line class="axis" x1="' + padL + '" y1="' + (padT + innerH) + '" x2="' + (W - padR) + '" y2="' + (padT + innerH) + '"></line>'
      + labels
      + '</svg>';
  }

  function renderBars(container, items, gradient) {
    if (!items || !items.length) { container.innerHTML = '<p class="muted">暂无数据</p>'; return; }
    var max = 0;
    items.forEach(function (item) { max = Math.max(max, num(item.revenue)); });
    if (max <= 0) max = 1;
    container.innerHTML = items.map(function (item) {
      var width = Math.max(2, num(item.revenue) / max * 100).toFixed(1);
      return '<div class="bar-row">'
        + '<div class="bar-label" title="' + esc(item.name) + '">' + esc(item.name) + '</div>'
        + '<div class="bar-track"><div class="bar-fill" style="width:' + width + '%;background:' + gradient + '"></div></div>'
        + '<div class="bar-value">' + fmtMoney(item.revenue) + ' <span class="muted">' + fmtPct(item.share) + '</span></div>'
        + '</div>';
    }).join("");
  }

  /* ------------------------------------------------------------ renderers */
  function renderKpis(summary) {
    var kpis = summary.kpis || {}, growth = summary.growth || {};
    byId("kpi-revenue").textContent = fmtMoney(kpis.revenue);
    byId("kpi-revenue-sub").innerHTML = growthSegment(growth.revenue)
      + ' · ' + esc(summary.range.start) + ' 起 ' + summary.range.days + ' 天';

    byId("kpi-units").textContent = fmtInt(kpis.units) + " 件";
    byId("kpi-units-sub").innerHTML = growthSegment(growth.units)
      + ' · 日均 ' + fmtInt(kpis.avg_daily_units) + ' 件';

    byId("kpi-daily").textContent = fmtMoney(kpis.avg_daily_revenue);
    byId("kpi-daily-sub").innerHTML = growthSegment(growth.avg_daily_revenue)
      + ' · 共 ' + fmtInt(kpis.active_days) + ' 天';

    byId("kpi-price").textContent = fmtMoneyRaw(kpis.avg_unit_price);
    byId("kpi-price-sub").textContent = "覆盖 " + fmtInt(kpis.sales_rows) + " 条门店×品类记录";

    byId("kpi-promo").textContent = fmtSignedPct(kpis.promo_uplift);
    byId("kpi-promo").className = "kpi-value " + deltaClass(kpis.promo_uplift);
    byId("kpi-promo-sub").textContent = "促销日占比 " + fmtPct(kpis.promo_day_share)
      + " · 贡献营收 " + fmtPct(kpis.promo_revenue_share);

    byId("kpi-weekend").textContent = fmtSignedPct(kpis.weekend_uplift);
    byId("kpi-weekend").className = "kpi-value " + deltaClass(kpis.weekend_uplift);
    byId("kpi-weekend-sub").textContent = "周末日均 " + fmtMoney(kpis.avg_daily_revenue_weekend)
      + " / 工作日 " + fmtMoney(kpis.avg_daily_revenue_weekday);
  }

  function renderForecast(data) {
    byId("forecast-chart").innerHTML = forecastChart(data.history, data.points);
    byId("forecast-caption").textContent = data.horizon + " 天 · " + data.series_count + " 条序列 · 含 95% 区间";

    var totals = data.totals || {}, peak = data.peak || {};
    var pills = [
      ["预测总营收", fmtMoney(totals.revenue)],
      ["预测日均营收", fmtMoney(totals.avg_daily_revenue)],
      ["预测总销量", fmtInt(totals.units_sold) + " 件"],
      ["峰值日", String(peak.date || "—").slice(5) + " · " + fmtMoney(peak.revenue)]
    ];
    byId("forecast-summary").innerHTML = pills.map(function (pair) {
      return '<div class="summary-pill"><span>' + esc(pair[0]) + '</span><strong>' + esc(pair[1]) + '</strong></div>';
    }).join("");
  }

  function renderModel(data) {
    var targets = [["revenue", "营收模型"], ["units_sold", "销量模型"]];
    byId("model-info").innerHTML = targets.map(function (pair) {
      var m = (data.model || {})[pair[0]] || {};
      var rows = [
        ["选用模型", esc(m.model || "—")],
        ["验证集 MAPE", fmtPct(m.mape, 2)],
        ["季节朴素基线", fmtPct(m.baseline_mape, 2)],
        ["相对基线提升", isNil(m.improvement_vs_baseline) ? "—" : fmtSignedPct(m.improvement_vs_baseline)],
        ["MAE / RMSE", fmtMoney(m.mae) + " / " + fmtMoney(m.rmse)],
        ["训练样本", fmtInt(m.train_rows) + " 行"]
      ];
      var candidates = (m.candidates || []).map(function (c) {
        return '<div class="model-row"><span>· ' + esc(c.model) + ' 候选</span><span>MAE ' + fmtMoney(c.mae)
          + ' · MAPE ' + fmtPct(c.mape, 2) + '</span></div>';
      }).join("");
      return '<div class="model-card"><h3>' + esc(pair[1])
        + '<span class="badge ' + (pair[0] === "revenue" ? "badge-ai" : "badge-muted") + '">' + esc(m.model || "—") + '</span></h3>'
        + '<div class="model-rows">' + rows.map(function (row) {
          return '<div class="model-row"><span>' + row[0] + '</span><span>' + row[1] + '</span></div>';
        }).join("") + candidates + '</div></div>';
    }).join("");
  }

  function renderInsights(data) {
    byId("narrative").textContent = data.narrative || "暂无简报";
    var badge = byId("narrative-source");
    badge.textContent = data.narrative_source === "llm" ? "LLM 生成" : "规则引擎";
    badge.className = "badge " + (data.narrative_source === "llm" ? "badge-ai" : "badge-ok");

    var insights = data.insights || [];
    byId("insights").innerHTML = insights.map(function (item) {
      return '<article class="insight ' + esc(item.severity || "info") + '">'
        + '<h3>' + esc(item.title) + '</h3>'
        + '<p>' + esc(item.detail) + '</p>'
        + (item.recommendation ? '<p class="rec">' + esc(item.recommendation) + '</p>' : '')
        + '</article>';
    }).join("") || '<p class="muted">未生成洞察</p>';
  }

  function renderAnomalies(items) {
    if (!items || !items.length) { byId("anomalies").innerHTML = '<p class="muted">未检测到显著异常日</p>'; return; }
    byId("anomalies").innerHTML = items.map(function (item) {
      return '<div class="chip ' + esc(item.direction) + '">'
        + '<strong>' + esc(item.date) + '</strong> ' + (item.direction === "spike" ? "▲ 高" : "▼ 低")
        + '<small>' + fmtMoney(item.revenue) + ' · ' + item.zscore + 'σ · 基线 ' + fmtMoney(item.expected) + '</small></div>';
    }).join("");
  }

  function renderRuns(runs) {
    if (!runs || !runs.length) { byId("prediction-runs").innerHTML = '<p class="muted">暂无预测记录</p>'; return; }
    byId("prediction-runs").innerHTML = runs.map(function (run) {
      return '<div class="chip"><strong>' + esc(run.model_name || "—") + '</strong> · ' + fmtInt(run.horizon) + ' 天'
        + '<small>' + esc(run.store || "全部门店") + ' / ' + esc(run.category || "全部品类")
        + ' · ' + fmtMoney(run.total_revenue) + ' · MAPE ' + fmtPct(run.mape, 2) + '</small></div>';
    }).join("");
  }

  function renderTable(data) {
    state.pages = data.pages || 1;
    byId("sales-body").innerHTML = (data.items || []).map(function (row) {
      var tags = (row.promotion ? '<span class="tag tag-promo">促销</span> ' : "")
        + (row.is_weekend ? '<span class="tag">周末</span>' : "");
      return '<tr>'
        + '<td>' + esc(row.date) + '</td>'
        + '<td>' + esc(row.store) + '</td>'
        + '<td>' + esc(row.category) + '</td>'
        + '<td class="num">' + fmtInt(row.units_sold) + '</td>'
        + '<td class="num">' + fmtMoneyRaw(row.unit_price) + '</td>'
        + '<td class="num">' + fmtPct(row.discount, 1) + '</td>'
        + '<td class="num">' + fmtMoneyRaw(row.revenue) + '</td>'
        + '<td>' + (tags || '<span class="muted">—</span>') + '</td>'
        + '</tr>';
    }).join("") || '<tr><td colspan="8" class="muted">暂无数据</td></tr>';

    byId("page-info").textContent = "共 " + fmtInt(data.total) + " 条 · 第 " + data.page + " / " + (data.pages || 1) + " 页";
    byId("page-label").textContent = "第 " + data.page + " 页";
    byId("prev-btn").disabled = data.page <= 1;
    byId("next-btn").disabled = data.page >= (data.pages || 1);
  }

  /* ---------------------------------------------------------------- loads */
  function query() {
    return {
      store: state.store, category: state.category,
      start: state.start, end: state.end
    };
  }

  function loadTable() {
    beginLoad();
    return safe(api("/sales", {
      store: state.store, category: state.category, start: state.start, end: state.end,
      page: state.page, page_size: state.pageSize
    })).then(function (data) {
      if (data) renderTable(data);
      endLoad();
    });
  }

  function loadAll() {
    var base = query();
    beginLoad();
    return Promise.all([
      safe(api("/summary", base)),
      safe(api("/timeseries", {
        store: state.store, category: state.category, start: state.start, end: state.end,
        granularity: state.granularity
      })),
      safe(api("/breakdown", { store: state.store, category: state.category, start: state.start, end: state.end, dimension: "category" })),
      safe(api("/breakdown", { store: state.store, category: state.category, start: state.start, end: state.end, dimension: "store" })),
      safe(api("/forecast", { store: state.store, category: state.category, horizon: state.horizon })),
      safe(api("/insights", { store: state.store, category: state.category, start: state.start, end: state.end, horizon: state.horizon })),
      safe(api("/anomalies", { store: state.store, category: state.category })),
      safe(api("/predictions", { limit: 4 })),
      safe(api("/sales", {
        store: state.store, category: state.category, start: state.start, end: state.end,
        page: state.page, page_size: state.pageSize
      }))
    ]).then(function (results) {
      var summary = results[0], timeseries = results[1], catBreak = results[2], storeBreak = results[3];
      var forecast = results[4], insights = results[5], anomalies = results[6], runs = results[7], table = results[8];

      if (summary) {
        renderKpis(summary);
        byId("trend-caption").textContent = summary.scope.label + " · " + summary.range.start + " ~ " + summary.range.end;
      }
      if (timeseries) byId("trend-chart").innerHTML = trendChart(timeseries.points);
      if (catBreak) renderBars(byId("category-bars"), catBreak.items, "linear-gradient(90deg,#5b8cff,#22d3ee)");
      if (storeBreak) renderBars(byId("store-bars"), storeBreak.items, "linear-gradient(90deg,#22d3ee,#34d399)");
      if (forecast) { renderForecast(forecast); renderModel(forecast); }
      if (insights) renderInsights(insights);
      if (anomalies) renderAnomalies(anomalies.anomalies);
      if (runs) renderRuns(runs.runs);
      if (table) renderTable(table);
      endLoad();
    });
  }

  function loadHealth() {
    return safe(api("/health")).then(function (data) {
      if (!data) return;
      var badge = byId("health-badge");
      badge.textContent = "已连接 · " + fmtInt(data.rows) + " 条数据";
      badge.className = "badge badge-ok";
      byId("footer-meta").textContent = data.date_min + " ~ " + data.date_max
        + " · " + (data.llm_configured ? "LLM 已配置" : "LLM 未配置（使用规则引擎）");
    });
  }

  function loadFilters() {
    return safe(api("/filters")).then(function (data) {
      if (!data) return;
      var storeSelect = byId("store-filter");
      var categorySelect = byId("category-filter");
      (data.stores || []).forEach(function (name) {
        storeSelect.appendChild(new Option(name, name));
      });
      (data.categories || []).forEach(function (name) {
        categorySelect.appendChild(new Option(name, name));
      });
      if (data.date_min) {
        byId("start-filter").value = data.date_min;
        byId("start-filter").min = data.date_min;
      }
      if (data.date_max) {
        byId("end-filter").value = data.date_max;
        byId("end-filter").max = data.date_max;
      }
      if (data.horizon_max) byId("horizon-filter").dataset.max = data.horizon_max;
    });
  }

  /* --------------------------------------------------------------- events */
  function readControls() {
    state.store = byId("store-filter").value;
    state.category = byId("category-filter").value;
    state.start = byId("start-filter").value;
    state.end = byId("end-filter").value;
    state.granularity = byId("granularity-filter").value;
    state.horizon = Number(byId("horizon-filter").value) || 30;
  }

  function init() {
    byId("apply-btn").addEventListener("click", function () {
      readControls();
      state.page = 1;
      loadAll();
    });
    byId("reset-btn").addEventListener("click", function () {
      byId("store-filter").value = "";
      byId("category-filter").value = "";
      byId("granularity-filter").value = "day";
      byId("horizon-filter").value = "30";
      state.page = 1;
      loadFilters().then(function () {
        readControls();
        loadAll();
      });
    });
    byId("granularity-filter").addEventListener("change", function () {
      readControls();
      loadAll();
    });
    byId("horizon-filter").addEventListener("change", function () {
      readControls();
      loadAll();
    });
    byId("refresh-btn").addEventListener("click", function () {
      loadHealth();
      loadAll();
    });
    byId("prev-btn").addEventListener("click", function () {
      if (state.page > 1) { state.page -= 1; loadTable(); }
    });
    byId("next-btn").addEventListener("click", function () {
      if (state.page < state.pages) { state.page += 1; loadTable(); }
    });

    loadFilters().then(function () {
      readControls();
      loadHealth();
      loadAll();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
