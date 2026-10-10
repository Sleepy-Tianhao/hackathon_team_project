/*
========================================================
API SERVICE
========================================================
前端唯一与后端通信的出口。

工作方式（自动切换，不需要改代码）：
1. 后端在线  -> POST {base}/analyze，返回真实模型结果
2. 后端离线  -> 自动回退到 analyzeMock()，页面照常可以演示

后端地址按优先级依次尝试：
1. window.SDC_API_BASE（在 index.html 里写死，最高优先级）
2. ?api=http://127.0.0.1:8000（临时指定）
3. 同源（页面由 backend/server.py 或 uvicorn 直接托管时）
4. http://127.0.0.1:8000（用 VS Code Live Server 打开页面时的本地后端）

后端契约（详见 TEMPLATE.md 第 5 节）：
POST /analyze   { "menu": "Chicken Rice", "day": "Friday", ... }
返回            { prediction, average, change_percent, confidence, explanation, ... }
========================================================
*/

const REQUEST_TIMEOUT = 60000;

// 上一次预测实际来自哪里：给界面提示用，也方便比赛现场排查
let lastSource = "unknown";

export function getLastSource() {
  return lastSource;
}

function trimBase(base) {
  let text = String(base);
  while (text.endsWith("/")) {
    text = text.slice(0, -1);
  }
  return text;
}

function candidateBases() {
  if (typeof window === "undefined") {
    return [""];
  }

  const explicit = window.SDC_API_BASE;
  if (explicit !== undefined && explicit !== null) {
    return [trimBase(explicit)];
  }

  const fromQuery = new URLSearchParams(window.location.search).get("api");
  if (fromQuery) {
    return [trimBase(fromQuery)];
  }

  const bases = [""];
  if (window.location.port !== "8000") {
    bases.push("http://127.0.0.1:8000");
  }
  return bases;
}

async function request(url, options) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT);

  try {
    const response = await fetch(url, Object.assign({}, options, {
      signal: controller.signal
    }));

    if (!response.ok) {
      let detail = "HTTP " + response.status;
      try {
        const body = await response.json();
        if (body && body.detail) {
          detail = body.detail;
        }
      } catch (ignored) {
        // 后端没返回 JSON，保留 HTTP 状态码即可
      }
      throw new Error(detail);
    }

    return await response.json();
  } finally {
    clearTimeout(timer);
  }
}

/*
--------------------------------------------------------
GET /api/config
页面初始化用：模板 + 下拉项 + 数据摘要。
拿不到就返回 null，页面会退回 js/config.js 里的 inputs。
--------------------------------------------------------
*/
export async function fetchConfig() {
  for (const base of candidateBases()) {
    const root = trimBase(base);
    try {
      return await request(root + "/api/config", { method: "GET" });
    } catch (error) {
      console.warn("[api] config from " + (root || "same-origin") + " failed:", error.message);
    }
  }
  return null;
}

/*
--------------------------------------------------------
POST /analyze
真正调用模型。所有候选地址都失败时才回退 Mock，
保证"后端还没写好/没启动"时页面依然能演示。
--------------------------------------------------------
*/
export async function analyze(data) {
  for (const base of candidateBases()) {
    const root = trimBase(base);
    const url = root + "/analyze";

    try {
      const result = await request(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data)
      });

      lastSource = root === "" ? "backend (same origin)" : "backend (" + root + ")";
      return result;
    } catch (error) {
      console.warn("[api] " + url + " failed:", error.message);
    }
  }

  console.warn("[api] no backend reachable - using mock data");
  lastSource = "mock";
  return analyzeMock(data);
}

/*
--------------------------------------------------------
MOCK API
后端不可用时的离线演示数据。字段与返回结构与真实接口一致。
相比上游：由 Math.random() 换成"由输入决定的确定性算法"，
同样的输入永远得到同样的结果，方便现场演示与复现。
--------------------------------------------------------
*/

/* 楼栋基准负荷 kWh（与 data/energy_consumption.csv 的量级保持一致） */
const BUILDING_BASE = {
  "Canteen": 168,
  "Dormitory C": 132,
  "Laboratory B": 196,
  "Library": 118,
  "Teaching Block A": 126
};

const WEATHER_FACTOR = {
  "Cloudy": 1.00,
  "Cold": 1.12,
  "Hot": 1.18,
  "Rain": 1.06,
  "Sunny": 0.97
};

const HISTORY_AVERAGE = 143;

/* 简易字符串散列，用来做 ±3% 的确定性抖动：让数字像实测值而不是整数 */
function hash(text) {
  let value = 2166136261;

  for (let i = 0; i < text.length; i += 1) {
    value ^= text.charCodeAt(i);
    value = Math.imul(value, 16777619);
  }

  return value >>> 0;
}

export async function analyzeMock(data) {
  await new Promise(resolve => setTimeout(resolve, 700));

  const building = String((data && data.building) || "Canteen");
  const dayType = String((data && data.day_type) || "Weekday");
  const weather = String((data && data.weather) || "Cloudy");
  const termPhase = String((data && data.term_phase) || "Term");
  const notes = String((data && data.notes) || "").trim();

  const base = BUILDING_BASE[building] || 140;
  const weatherFactor = WEATHER_FACTOR[weather] || 1;

  const dayFactor = dayType === "Weekend" ? 0.62 : 1;
  const termFactor =
    termPhase === "Vacation" ? 0.55 :
      termPhase === "Exam Week" ? 1.08 : 1;

  const jitter = 1 + (((hash(building + "|" + weather) % 601) - 300) / 10000);

  const prediction = Math.round(base * weatherFactor * dayFactor * termFactor * jitter);
  const average = HISTORY_AVERAGE;
  const change = Number((((prediction - average) / average) * 100).toFixed(1));

  const reasons = [
    building + " 的基准负荷约 " + base + " kWh",
    weather + " 天气系数 " + weatherFactor.toFixed(2),
    dayType === "Weekend" ? "周末负荷约为工作日的 62%" : "工作日满负荷",
    "学期阶段：" + termPhase
  ];

  /* 置信度：离历史均值越远越保守 */
  const confidence = Math.max(72, Math.min(95, Math.round(93 - Math.abs(change) * 0.4)));

  return {
    prediction: prediction,
    average: average,
    change_percent: change,
    confidence: confidence,
    explanation:
      "预测 " + prediction + " kWh（历史均值 " + average + " kWh，偏差 " + change + "%）。" +
      "主要依据：" + reasons.join("；") + "。" +
      (notes ? " 你补充的信息：" + notes + "。" : "") +
      " 当前为离线演示数据（Mock），启动后端后会自动切换为真实模型结果。",
    meta: { source: "mock" }
  };
}
