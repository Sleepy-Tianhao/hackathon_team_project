# SDC Hackathon · 通用预测模板

组件式前端 + 模板驱动后端 + 可插拔模型。换一个 `template.json` 就换一个赛题，
换一个模型插件就换成你们的模型，**前端代码不用动**。

```
┌──────────────────────────────────────────────────────┐
│  ENERGY CONSUMPTION FORECAST             Dashboard  │
├──────────────────────────────────────────────────────┤
│  AI FOR SUSTAINABILITY                               │
│  Predict demand. Cut energy waste.                   │
│                                                      │
│  ┌─ Core Analysis ──────────────┐  ┌─ AI RESULT ──┐  │
│  │ Building:   [Teaching Blk A] │  │      816     │  │
│  │ Day Type:   [Weekday      ]  │  │      kWh     │  │
│  │ Weather:    [Sunny        ]  │  │ Average 693  │  │
│  │ Term Phase: [Term         ]  │  │ Change +17.7%│  │
│  │ Notes:      [.............]  │  │ Confidence 93%│ │
│  │     [ Predict Consumption ]  │  │ 🤖 AI Insight│  │
│  └──────────────────────────────┘  └──────────────┘  │
└──────────────────────────────────────────────────────┘
```

**📖 文档地图**

| 我想做这件事 | 看这份 |
|---|---|
| 先跑起来看看 | 下面「一分钟上手」 |
| 换赛题 / 加减字段 / 接自己的模型 | [TEMPLATE.md](TEMPLATE.md) |
| 换成我们自己的数据 | [DATA_FORMAT.md](DATA_FORMAT.md) |
| 搞清楚每个文件是干嘛的 | [ARCHITECTURE.md](ARCHITECTURE.md) |
| 我只负责前端，怎么指挥后端 | [BACKEND_HANDOFF.md](BACKEND_HANDOFF.md) |
| 比赛当天改哪些文件、按角色分工 | [COMPETITION_CHECKLIST.md](COMPETITION_CHECKLIST.md) |

---

## 一分钟上手

### 1 · 启动

```powershell
python -m backend.server --port 8000
# 浏览器打开 http://127.0.0.1:8000/  —— 后端直接把前端也托管起来
```

只依赖本机已有的 pandas / numpy / scikit-learn / SQLAlchemy，**不联网也能跑**。
（想用 FastAPI：`uvicorn backend.main:app --reload`，额外需要 `pip install -r requirement.txt`）

页面上你能做的事：左边选几个条件 → 点 **Predict Consumption** → 右边出预测值、对比基准、
变化百分比、置信度和大模型/本地模型写的解释。

### 2 · 换成你们自己的数据

一条命令完成「校验 + 预演接口 + 生成模板」：

```powershell
python -m backend.check_data --csv data/my.csv --target <数值列> ^
    --field <维度列1> --field <维度列2> --check-api --write-template templates/my.json

$env:TEMPLATE_FILE = "templates/my.json"    # 不动默认模板，随时能切回来
python -m backend.server
```

它会打印行数、每个字段的取值与样本量、**留一天法回测的 MAPE**，并直接告诉你"哪些列没被用上"。
数据只需要一个数值目标列 + 若干维度列（每个下拉框一列），格式要求见 [DATA_FORMAT.md](DATA_FORMAT.md)。
`--baseline-filter` 可选，用来定义"什么是正常水平"（例如只拿工作日当基准），见 [TEMPLATE.md 第 8 节](TEMPLATE.md)。

### 3 · 换赛题（只改配置，不改代码）

```powershell
copy templates\retail-sales.json template.json     # 零售销售 + ExtraTrees
copy templates\food-demand.json template.json      # 校园食堂需求
```

或者不覆盖文件、用环境变量临时切：
```powershell
$env:TEMPLATE_FILE = "templates/retail-sales.json"; python -m backend.server
```

### 4 · 接你们自己的模型

```powershell
$env:MODEL_BACKEND = "http"
$env:MODEL_API_URL = "http://127.0.0.1:9000/predict"
$env:MODEL_API_KEY = "your-token"        # 可选，有值就带 Authorization: Bearer
python -m backend.server
```

你们的服务只要返回 `{"value": 132}`（其余字段都可选）。契约见 [TEMPLATE.md 第 6 节](TEMPLATE.md#6-接入你自己的模型-api重点)；
连不上时默认自动回退本地插件（`meta.fallback=true`），演示不会中断。

### 5 · 接第三方大模型写解释（路线 1：本地模型出数 + 大模型写话）

```powershell
# 终端 1：解释服务（参考实现已写好）
$env:LLM_API_KEY = "sk-..."      # 任意 OpenAI 兼容网关；不配 key 也能跑，会退回本地话术
python examples/llm_explainer_service.py --port 9000

# 终端 2：主应用切到外接模式
$env:MODEL_BACKEND = "http"
$env:MODEL_API_URL = "http://127.0.0.1:9000/predict"
python -m backend.server
```

怎么确认大模型真的被调用了：看响应里的 `meta.external_explanation_source` 是 `"llm"` 还是 `"local-model"`，
或连续两次访问 `http://127.0.0.1:9000/health` 看 `llm_calls` 有没有 +1。

---

## 两个运行入口

| 入口 | 命令 | 依赖 | 说明 |
|---|---|---|---|
| 零依赖服务器 | `python -m backend.server` | pandas / numpy / scikit-learn / SQLAlchemy | 同时托管前端，离线可用，演示首选 |
| FastAPI 应用 | `uvicorn backend.main:app --reload` | 额外需要 fastapi / uvicorn | 正式部署，自带 `/docs` |

两者共用 `backend/service.py` 的全部业务逻辑，只是路由适配器不同，行为不会漂移。

前端单独开发时，用 VS Code Live Server 打开 `frontend/index.html` 也可以：
`api.js` 会先试同源、再试 `http://127.0.0.1:8000`，都连不上才回退 Mock 数据。

---

## 接口一览

| 方法 | 路径 | 请求体 | 说明 |
|---|---|---|---|
| **POST** | **`/analyze`** | **扁平字段表** `{"building":"...","weather":"..."}` | **前端实际调用的接口**。响应在完整信封之上多 3 个别名：`prediction / average / change_percent`（外加 `confidence / explanation`） |
| POST | `/api/predict` | `{"fields":{...}}` | 同一段代码的完整信封版（多 `value / baseline / delta / direction / model / evidence / meta`） |
| GET | `/api/config` | — | 模板 + 下拉项 + 数据摘要 + 回测指标，前端凭它渲染整个页面 |
| GET | `/api/options` | — | 只刷新下拉项 |
| GET | `/api/health` | — | 存活状态、数据行数、日期范围 |
| GET | `/api/predictions` | — | 预测审计记录 |

> ⚠️ **两个 POST 的 body 形状不一样**，这是最容易踩的坑：`/analyze` 直接收 `FormData` 转出来的扁平对象，
> `/api/predict` 要包一层 `fields`。两者业务逻辑完全相同，只是适配器不同。

**错误约定**：非 2xx 一律返回 `{"detail": "人话原因"}`，状态码 400 / 404 / 405 / 413 / 422 / 500 / 502。
前端直接把 `detail` 弹在页面右下角 —— 所以报错写得越具体，现场排查越快。

**跨域**：已开 CORS（`Access-Control-Allow-Origin: *`，预检允许 `GET, POST, OPTIONS`），
所以用 VS Code Live Server 打开前端也能直连本机后端；用 `backend/server.py` 托管前端时是同源，根本不走 CORS。

另有销售分析专用的一组接口（`/api/summary · timeseries · breakdown · momentum · sales · anomalies · forecast · insights`），
供 `backend/predictor.py` 的 ML 插件与被归档的看板使用。完整契约见 [TEMPLATE.md](TEMPLATE.md#5-http-接口契约)。

---

## 目录结构

```text
Hackathon/
├── template.json              ★ 后端唯一配置源（默认：校园用电量预测）
├── templates/
│   ├── food-demand.json       备用模板：食堂需求预测
│   └── retail-sales.json      备用模板：零售销售 + 本地 ML 插件
├── frontend/                  组件式前端（ES Module，无框架、无构建）
│   ├── index.html             只有 #app / #toast 容器
│   ├── css/style.css          全部样式
│   ├── js/config.js           ★ 外壳文案：项目名 / 标题 / Metrics / Impact
│   ├── js/app.js              入口：拉模板 → 组合组件 → 绑定表单 → 调 API
│   ├── js/components/         header · hero · metrics · analysis · impact · footer
│   └── js/services/api.js     ★ 与后端通信的唯一出口（含离线 Mock 回退）
├── backend/
│   ├── template_config.py     读取 + 严格校验 template.json；CSV 列 → 下拉项
│   ├── check_data.py          数据校验 / 生成示例 / 预演 API（退出码 0/1）
│   ├── model_api.py           ★ 模型插件：本地统计 / 本地 ML / 外接 HTTP
│   ├── service.py             业务编排：校验字段、选插件、归一化结果
│   ├── server.py              零依赖入口（含静态托管 + ES Module MIME）
│   ├── main.py                FastAPI 入口
│   ├── predictor.py           本地 ML 引擎（ExtraTrees + 递归多步预测）
│   ├── ai.py                  规则洞察 + 异常检测 + 可选 LLM 叙事
│   ├── models.py / database.py  ORM + 引擎 + CSV 自动播种
├── data/                      energy_consumption.csv / menu_demand.csv / sales.csv
│                              + 三个可复现生成器
│   └── samples/               自定义数据示例：coffee_shop_sales.csv + 配套模板
├── examples/
│   └── llm_explainer_service.py  路线 1 参考服务：本地模型出数 + 大模型写解释
├── tests/test_api.py          69 个端到端测试（仅需标准库）
├── TEMPLATE.md                ★ 模板 / 接口 / 接入模型 完整文档
├── DATA_FORMAT.md             ★ 自定义数据：格式要求 + 校验工具用法
├── ARCHITECTURE.md            精确到文件的架构图与依赖关系
├── BACKEND_HANDOFF.md         前后端分工 + 接口契约（拿来对接队友）
├── COMPETITION_CHECKLIST.md   比赛当天改哪些文件、按角色分工
└── requirement.txt
```

---

## 模型插件

`backend/model_api.py` 是唯一的模型接入层：

| 插件 | 类型 | 说明 |
|---|---|---|
| `group-baseline` | 本地统计 | 通用条件均值因子模型，任何 CSV + 任何字段都能用。**解释文字就是它乘过的那些因子** |
| `sales-forecast` | 本地 ML | 把 `store/category/horizon` 映射到 ExtraTrees 递归预测（验证集 MAPE 13.05%，优于季节朴素基线 33.5%） |
| `http` | 外接 | **你们的模型 API**（也可以是包了大模型的解释服务）。只有 `value` 必填；失败自动回退本地插件 |

外接契约（详见 [TEMPLATE.md 第 6 节](TEMPLATE.md#6-接入你自己的模型-api重点)）：

```json
// → 发给你们的
{ "template_id": "energy-forecast",
  "fields": { "building": "Teaching Block A", "day_type": "Weekday",
              "weather": "Sunny", "term_phase": "Term", "notes": "" },
  "unit": "kWh",
  "context": { "target": "kwh", "requested_at": "2026-03-01T08:00:00+00:00" } }

// ← 你们返回的（只有 value 必填）
{ "value": 640, "unit": "kWh", "baseline": 693, "confidence": 91,
  "explanation": "Cold weather and a term week push the lab load above normal.",
  "model": "load-xgb-v3" }
```

---

## 实测指标（默认模板，60 天留一天法回测）

| 指标 | 数值 |
|---|---|
| 回测 MAPE | **6.6%**（准确率 93.4% → 界面 confidence 93%） |
| 平均绝对误差 | 45.26 kWh |
| 参照系（每天都按"典型工作日"估算） | 256.14 kWh / MAPE 46.8% |
| **相对参照系减少的误差** | MAE **82.3%** / MAPE **85.9%** |

这些数字由 `backtest_group_baseline()` 现算并随响应返回（`meta.backtest`），
也可以从 `GET /api/config` 的 `model.backtest` 取到，**不是写死的宣传数字**。

---

## 我改动了前端的哪几个文件

保持你们的结构与组件不变，只做了"接线"：

| 文件 | 改动 |
|---|---|
| `js/services/api.js` | 新增真实 `analyze()` / `fetchConfig()`（含超时、候选地址、错误信息），保留 `analyzeMock()` 作离线回退 |
| `js/app.js` | 启动时用 `/api/config` 覆盖 `CONFIG.inputs`；改用 `analyze()`；结果渲染对 `null` 做兜底 |
| `js/config.js` | 文案对齐到能耗场景（**你们自己改的 projectName / title 原样保留**）；`inputs` 变为离线兜底；Metrics/Impact 换成能耗回测实测值 |
| `index.html · css/style.css · components/*` | **未改动** |

字段的分工：外壳文案在 `config.js`，分析字段与输出单位在 `template.json`。

---

## 数据集

| 文件 | 规模 | 用途 | 重新生成 |
|---|---|---|---|
| `data/energy_consumption.csv` | 3,655 行 / 731 天 / 5 栋楼 | **默认模板** | `python data/generate_energy.py` |
| `data/menu_demand.csv` | 3,655 行 / 730 天 / 5 菜单 | `templates/food-demand.json` | `python data/generate_menu_demand.py` |
| `data/sales.csv` | 14,620 行 / 731 天 / 4 门店 × 5 品类 | `templates/retail-sales.json` + ML 插件 | `python data/generate_sales.py` |

三个生成器都用固定随机种子，完全可复现，并内置了模型该学的真实信号（工作日/周末、天气、假期、促销等）。

---

## 测试

```bash
python -m unittest discover -s tests -v      # 69 个用例，仅用标准库
pytest -q                                    # 装了 pytest 也可以
```

覆盖：模板加载的全部报错分支（含"数据集缺失时 /analyze 必须报出精确原因"）、
`/analyze` 与 `/api/predict` 契约、外接模型 API 的成功调用（含请求契约断言）与两种失败模式、
字段校验、**CORS 预检允许 POST**、ES Module MIME、静态资源、目录穿越防护、
confidence 与回测的数值一致性、自定义数据校验工具与 `DATASET_FILE` 覆盖、
LLM 解释服务（路线 1）、以及一条"HTTP 接口清单未变"的回归断言，最后是原有的销售分析与 ML 预测。

---

## 已知限制

- `group-baseline` 假设各字段效应独立，强相关字段（如"周六"与"假日"）会重复计算，故有上下限截断。
- 本地 ML 插件在进程内训练，重启即重训（启动时后台预热，首个请求不等待）。
- 接口当前无鉴权、无多租户，请勿直接暴露到公网。
