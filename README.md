# SDC Hackathon · 通用预测模板

组件式前端 + 模板驱动后端 + 可插拔模型。换一个 `template.json` 就换一个赛题，
换一个模型插件就换成你们的模型，**前端代码不用动**。

```
┌──────────────────────────────────────────────────────┐
│  CAMPUS FOOD FORECAST                    Dashboard  │
├──────────────────────────────────────────────────────┤
│  AI FOR SUSTAINABILITY                               │
│  Predict demand. Cut food waste.                     │
│                                                      │
│  ┌─ Core Analysis ─────────┐  ┌─ AI RESULT ───────┐  │
│  │ Menu:    [Chicken Rice] │  │        95          │  │
│  │ Day:     [Friday     ]  │  │      portions      │  │
│  │ Weather: [Rain       ]  │  │ Average 92         │  │
│  │ Notes:   [...........]  │  │ Change +3.7%       │  │
│  │      [ Predict Demand ] │  │ Confidence 93%     │  │
│  └─────────────────────────┘  │ 🤖 AI Insight ...  │  │
│                               └────────────────────┘  │
└──────────────────────────────────────────────────────┘
```

**📖 模板字段、接口契约、接入自己模型的完整说明 → [TEMPLATE.md](TEMPLATE.md)**

---

## 一分钟上手

```powershell
python -m backend.server --port 8000
# 浏览器打开 http://127.0.0.1:8000/  —— 后端直接把前端也托管起来
```

只依赖本机已有的 pandas / numpy / scikit-learn / SQLAlchemy，**不联网也能跑**。

换赛题（只改配置，不改代码）：

```powershell
copy templates\retail-sales.json template.json     # 零售销售 + ExtraTrees
```

接你们自己的模型：

```powershell
$env:MODEL_BACKEND = "http"
$env:MODEL_API_URL = "http://127.0.0.1:9000/predict"
python -m backend.server
```

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

| 方法 | 路径 | 说明 |
|---|---|---|
| **POST** | **`/analyze`** | **前端实际调用的接口**。扁平的字段表进，出 `prediction / average / change_percent / confidence / explanation` |
| POST | `/api/predict` | 同一段代码的完整信封版（多 `value / baseline / delta / direction / model / evidence / meta`） |
| GET | `/api/config` | 模板 + 下拉项 + 数据摘要 + 回测指标，前端凭它渲染表单 |
| GET | `/api/options` | 只刷新下拉项 |
| GET | `/api/health` | 存活状态、数据行数、日期范围 |
| GET | `/api/predictions` | 预测审计记录 |

另有销售分析专用的一组接口（`/api/summary · timeseries · breakdown · momentum · sales · anomalies · forecast · insights`），
供 `backend/predictor.py` 的 ML 插件与被归档的看板使用。完整契约见 [TEMPLATE.md](TEMPLATE.md#5-http-接口契约)。

---

## 目录结构

```text
Hackathon/
├── template.json              ★ 后端唯一配置源：字段 / 下拉项 / 模型插件 / 输出文案
├── templates/
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
│   ├── model_api.py           ★ 模型插件：本地统计 / 本地 ML / 外接 HTTP
│   ├── service.py             业务编排：校验字段、选插件、归一化结果
│   ├── server.py              零依赖入口（含静态托管 + ES Module MIME）
│   ├── main.py                FastAPI 入口
│   ├── predictor.py           本地 ML 引擎（ExtraTrees + 递归多步预测）
│   ├── ai.py                  规则洞察 + 异常检测 + 可选 LLM 叙事
│   ├── models.py / database.py  ORM + 引擎 + CSV 自动播种
├── data/                      menu_demand.csv / sales.csv + 两个可复现生成器
├── tests/test_api.py          53 个端到端测试（仅需标准库）
├── TEMPLATE.md                ★ 模板 / 接口 / 接入模型 完整文档
└── requirement.txt
```

---

## 模型插件

`backend/model_api.py` 是唯一的模型接入层：

| 插件 | 类型 | 说明 |
|---|---|---|
| `group-baseline` | 本地统计 | 通用条件均值因子模型，任何 CSV + 任何字段都能用。**解释文字就是它乘过的那些因子** |
| `sales-forecast` | 本地 ML | 把 `store/category/horizon` 映射到 ExtraTrees 递归预测（验证集 MAPE 13.05%，优于季节朴素基线 33.5%） |
| `http` | 外接 | **你们的模型 API**。只有 `value` 必填；失败可自动回退本地插件 |

外接契约（详见 [TEMPLATE.md 第 6 节](TEMPLATE.md#6-接入你自己的模型-api重点)）：

```json
// → 发给你们的
{ "template_id": "food-demand",
  "fields": { "menu": "Chicken Rice", "day": "Friday", "weather": "Rain",
              "event": "None", "notes": "" },
  "unit": "portions",
  "context": { "target": "portions", "requested_at": "2026-03-01T08:00:00+00:00" } }

// ← 你们返回的（只有 value 必填）
{ "value": 132, "unit": "portions", "baseline": 143, "confidence": 87,
  "explanation": "Friday demand is historically lower, and rain is expected.",
  "model": "canteen-xgb-v3" }
```

---

## 实测指标（默认模板，60 天留一天法回测）

| 指标 | 数值 |
|---|---|
| 回测 MAPE | **7.5%**（准确率 92.5% → 界面 confidence 93%） |
| 平均绝对误差 | 5.58 份 |
| 参照系（每天都按典型工作日备餐） | 32.02 份 / MAPE 68.7% |
| **相对参照系减少的误差** | **82.6%** |

这些数字由 `backtest_group_baseline()` 现算并随响应返回（`meta.backtest`），
也可以从 `GET /api/config` 的 `model.backtest` 取到，**不是写死的宣传数字**。

---

## 我改动了前端的哪几个文件

保持你们的结构与组件不变，只做了"接线"：

| 文件 | 改动 |
|---|---|
| `js/services/api.js` | 新增真实 `analyze()` / `fetchConfig()`（含超时、候选地址、错误信息），保留 `analyzeMock()` 作离线回退 |
| `js/app.js` | 启动时用 `/api/config` 覆盖 `CONFIG.inputs`；改用 `analyze()`；结果渲染对 `null` 做兜底 |
| `js/config.js` | 示例值换成食堂/减浪费场景；`inputs` 变为离线兜底；Metrics/Impact 换成回测实测值 |
| `index.html · css/style.css · components/*` | **未改动** |

字段的分工：外壳文案在 `config.js`，分析字段与输出单位在 `template.json`。

---

## 数据集

| 文件 | 规模 | 用途 | 重新生成 |
|---|---|---|---|
| `data/menu_demand.csv` | 3,655 行 / 730 天 / 5 菜单 | 默认模板 | `python data/generate_menu_demand.py` |
| `data/sales.csv` | 14,620 行 / 731 天 / 4 门店 × 5 品类 | 备用模板 + ML 插件 | `python data/generate_sales.py` |

两个生成器都用固定随机种子，完全可复现，并内置了模型该学的真实信号（周末效应、天气、假日等）。

---

## 测试

```bash
python -m unittest discover -s tests -v      # 53 个用例，仅用标准库
pytest -q                                    # 装了 pytest 也可以
```

覆盖：模板加载的全部报错分支、`/analyze` 与 `/api/predict` 契约、外接模型 API 的成功调用
（含请求契约断言）与两种失败模式、字段校验、ES Module MIME、静态资源、目录穿越防护、
confidence 与回测的数值一致性、以及原有的销售分析与 ML 预测。

---

## 已知限制

- `group-baseline` 假设各字段效应独立，强相关字段（如"周六"与"假日"）会重复计算，故有上下限截断。
- 本地 ML 插件在进程内训练，重启即重训（启动时后台预热，首个请求不等待）。
- 接口当前无鉴权、无多租户，请勿直接暴露到公网。
