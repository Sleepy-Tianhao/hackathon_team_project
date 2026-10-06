import { CONFIG } from "./config.js";

import { Header } from "./components/header.js";
import { Hero } from "./components/hero.js";
import { Metrics } from "./components/metrics.js";
import { Analysis } from "./components/analysis.js";
import { Impact } from "./components/impact.js";
import { Footer } from "./components/footer.js";

import { analyze, fetchConfig, getLastSource } from "./services/api.js";


/*
========================================================
APP ENTRY
========================================================
负责：
1. 从后端模板拉取表单字段（拿不到就用 config.js 的）
2. 组合页面
3. 注册事件
4. 调用 API
========================================================
*/

function renderApp() {
  const app = document.getElementById("app");

  app.innerHTML = `
    ${Header(CONFIG)}
    <main>
      ${Hero(CONFIG)}
      ${Metrics(CONFIG)}
      ${Analysis(CONFIG)}
      ${Impact(CONFIG)}
    </main>
    ${Footer(CONFIG)}
  `;
}

/*
--------------------------------------------------------
模板驱动的表单
template.json 是字段的唯一来源；这样前端的输入框和后端的
校验规则不会各写一份、逐渐对不上。
后端不可用时保留 js/config.js 里的 inputs 作为离线兜底。
--------------------------------------------------------
*/
function applyRemoteConfig(config) {
  const template = config && config.template;

  if (!template || !Array.isArray(template.fields) || template.fields.length === 0) {
    return false;
  }

  const options = config.options || {};

  CONFIG.inputs = template.fields.map(field => toInput(field, options[field.name]));

  if (template.output && template.output.unit) {
    CONFIG.analysis.resultUnit = template.output.unit;
  }

  const rows = config.dataset && config.dataset.rows;
  console.log(
    "[app] template '" + template.id + "' loaded" + (rows ? " (" + rows + " historical rows)" : "")
  );

  return true;
}

/* 后端字段 -> 前端控件参数（与 components/analysis.js 的 renderInputs 对齐） */
function toInput(field, values) {
  const choices = (values || []).map(String);

  return {
    id: field.name,
    label: field.label,
    type: choices.length ? "select" : (field.type === "number" ? "number" : "text"),
    options: choices,
    placeholder: field.placeholder || field.suffix || ""
  };
}


function setupEvents() {

  // Hero -> Analysis
  document.addEventListener("click", event => {

    if (event.target.dataset.action === "scroll-analysis") {
      document
        .querySelector("#analysis")
        .scrollIntoView({ behavior: "smooth" });
    }

    if (event.target.dataset.action === "about") {
      showToast("This is your reusable SDC project template.");
    }
  });


  // Analysis form
  const form = document.getElementById("analysis-form");

  form.addEventListener("submit", async event => {

    event.preventDefault();

    const button = form.querySelector("button");
    button.disabled = true;
    button.textContent = "Analyzing...";

    const formData = new FormData(form);
    const data = Object.fromEntries(formData.entries());

    try {

      // 后端在线走真实模型，离线自动回退 Mock（见 services/api.js）
      const result = await analyze(data);

      updateResult(result);

      // 路线 1（本地模型出数 + 大模型写解释）时，在提示里说明这句话是谁写的
      const wrote = result.meta && result.meta.external_explanation_source;
      showToast(
        getLastSource() === "mock"
          ? "Analysis completed (offline demo data)"
          : wrote === "llm"
            ? "Analysis completed · explanation by " + (result.model || "LLM")
            : "Analysis completed"
      );

    } catch (error) {

      console.error(error);

      showToast(error && error.message ? error.message : "Something went wrong.");

    } finally {

      button.disabled = false;
      button.textContent = CONFIG.analysis.button;
    }
  });
}


function updateResult(result) {

  setText("result-value", formatNumber(result.prediction));
  setText("result-average", formatNumber(result.average));

  setText(
    "result-change",
    isMissing(result.change_percent) ? "—" : `${result.change_percent}%`
  );

  setText(
    "result-confidence",
    isMissing(result.confidence) ? "—" : `${result.confidence}%`
  );

  setText("result-explanation", result.explanation || "—");
}


function setText(id, value) {
  const element = document.getElementById(id);
  if (element) {
    element.textContent = value;
  }
}

function isMissing(value) {
  return value === null || value === undefined || value === "";
}

function formatNumber(value) {
  if (isMissing(value)) {
    return "—";
  }

  const number = Number(value);

  return Number.isFinite(number)
    ? number.toLocaleString("en-US", { maximumFractionDigits: 1 })
    : String(value);
}


function showToast(message) {

  const toast = document.getElementById("toast");

  toast.textContent = message;
  toast.classList.add("show");

  setTimeout(() => {
    toast.classList.remove("show");
  }, 2200);
}


/*
--------------------------------------------------------
启动
先问后端要模板，再渲染；后端不在也照常启动。
--------------------------------------------------------
*/
async function bootstrap() {

  const remote = await fetchConfig();

  if (!applyRemoteConfig(remote)) {
    console.log("[app] backend not reachable - using fallback inputs from js/config.js");
  }

  renderApp();
  setupEvents();
}

bootstrap();
