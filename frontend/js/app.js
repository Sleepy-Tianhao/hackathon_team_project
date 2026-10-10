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
1. 把 config.js 的配色写成 CSS 变量 + 恢复主题（深浅）
2. 从后端模板拉取表单字段（拿不到就用 config.js 的）
3. 组合页面
4. 注册事件
5. 调用 API
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
  /* 导航栏里的主题按钮由 JS 注入（结构见 components/header.js） */
  mountThemeToggle();
}

/*
--------------------------------------------------------
主题
配色只在 js/config.js 的 palette 里写一份，这里写成 CSS 变量，
所以换色只需要改 config.js，不用动 css/style.css。
style.css 里保留了一份相同的兜底值，JS 未执行时页面同样是绿色。
--------------------------------------------------------
*/
function applyPalette(theme) {
  const palette = CONFIG.palette || {};
  const root = document.documentElement;

  const dark = theme === "dark";

  setVar(root, "--primary", dark ? palette.primaryOnDark : palette.primary);
  setVar(root, "--primary-dark", dark ? palette.primaryDarkOnDark : palette.primaryDark);
  setVar(root, "--primary-soft", dark ? palette.primarySoftDark : palette.primarySoft);

  if (palette.accent) {
    setVar(root, "--accent", palette.accent);
  }
}

function setVar(element, name, value) {
  if (value) {
    element.style.setProperty(name, value);
  }
}

function resolvedTheme() {
  const config = (CONFIG.theme || {});
  const key = config.storageKey || "sdc-theme";

  let stored = null;
  try {
    stored = localStorage.getItem(key);
  } catch (error) {
    stored = null; // 隐私模式 / 禁用存储
  }

  if (stored === "light" || stored === "dark") {
    return stored;
  }

  if (config.respectSystem !== false) {
    try {
      return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    } catch (error) {
      return "light";
    }
  }

  return "light";
}

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  applyPalette(theme);
  syncThemeButton(theme);
}

/* 主题按钮：注入到导航栏右侧，与链接同排 */
function mountThemeToggle() {
  const navInner = document.querySelector(".nav-inner");

  if (!navInner || navInner.querySelector(".theme-toggle")) {
    return;
  }

  const actions = document.createElement("div");
  actions.className = "nav-actions";

  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.id = "theme-toggle";
  toggle.className = "theme-toggle";
  toggle.title = "切换深色 / 浅色主题";
  toggle.setAttribute("aria-label", "切换深色 / 浅色主题");

  actions.appendChild(toggle);

  /* 保留原导航链接，只是把它们挪进 .nav-actions 以便和按钮并排 */
  const links = navInner.querySelector(".nav-links");
  if (links) {
    actions.insertBefore(links, toggle);
  }

  navInner.appendChild(actions);

  toggle.addEventListener("click", () => {
    const current = document.documentElement.getAttribute("data-theme");
    const next = current === "dark" ? "light" : "dark";

    applyTheme(next);

    try {
      localStorage.setItem((CONFIG.theme || {}).storageKey || "sdc-theme", next);
    } catch (error) {
      /* 存不了就算了，不影响切换 */
    }
  });

  syncThemeButton(document.documentElement.getAttribute("data-theme"));
}

function syncThemeButton(theme) {
  const toggle = document.getElementById("theme-toggle");

  if (toggle) {
    toggle.textContent = theme === "dark" ? "☀️" : "🌙";
  }
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
    /* 后端声明 optional / required=false 时前端也不强制填写；
       notes 是模板里的"补充信息"，同样视为可选 */
    optional: field.optional === true || field.required === false || field.name === "notes",
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

  /* 用户一动某个字段，就清掉它的错误态 */
  document.addEventListener("input", event => clearFieldError(event.target));
  document.addEventListener("change", event => clearFieldError(event.target));

  form.addEventListener("submit", async event => {

    event.preventDefault();

    const button = document.getElementById("analyze-button") || form.querySelector("button");

    if (!validateForm(form)) {
      showToast("请先补齐标红的必填项。");
      return;
    }

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


/*
--------------------------------------------------------
必填校验：只有真正缺失的必填字段才拦提交。
每个字段被包在 .field 里（components/analysis.js 生成），
所以错误态只影响出错的那一个。
--------------------------------------------------------
*/
function validateForm(form) {
  let ok = true;

  form.querySelectorAll("input, select").forEach(field => {
    const owner = field.closest(".field") || form;
    const optional = field.dataset.optional === "true";
    const empty = !String(field.value || "").trim();

    if (empty && !optional) {
      ok = false;
      owner.classList.add("field-error");
      field.setAttribute("aria-invalid", "true");
    } else {
      clearFieldError(field);
    }
  });

  return ok;
}


function clearFieldError(target) {
  if (!target || !target.closest) {
    return;
  }

  const owner = target.closest(".field");

  if (owner) {
    owner.classList.remove("field-error");
    target.removeAttribute("aria-invalid");
  }
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
1. 先落主题与配色（同步，避免深色模式闪白）
2. 再问后端要模板
3. 渲染 + 绑事件
后端不在也照常启动。
--------------------------------------------------------
*/
async function bootstrap() {

  applyTheme(resolvedTheme());

  const remote = await fetchConfig();

  if (!applyRemoteConfig(remote)) {
    console.log("[app] backend not reachable - using fallback inputs from js/config.js");
  }

  renderApp();
  setupEvents();
}

bootstrap();
