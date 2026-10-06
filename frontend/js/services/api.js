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
--------------------------------------------------------
*/
export async function analyzeMock(data) {
  await new Promise(resolve => setTimeout(resolve, 900));

  const prediction = Math.floor(110 + Math.random() * 50);
  const average = 143;
  const change = Number(
    (((prediction - average) / average) * 100).toFixed(1)
  );

  return {
    prediction,
    average,
    change_percent: change,
    confidence: 87,
    explanation:
      "Demo analysis completed. Connect your FastAPI backend to return the real model prediction and explanation."
  };
}
