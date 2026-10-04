# 通用预测模板框架 · Prediction Template Framework

一个**配置驱动的卡片式预测应用**：填表单 → 出预测值 + 变化幅度 + AI 解释。
页面上的每个字、每个下拉框都来自 `template.json`；预测由**模型插件**产生，自带两个本地插件，也可以**外接你自己的模型 API**。

```
┌─────────────────────────────────────────┐
│            SMART FOOD FORECAST          │
│       AI-powered Campus Food Forecast   │
├─────────────────────────────────────────┤
│  Menu:     [ Chicken Rice         ▼ ]   │
│  Day:      [ Friday               ▼ ]   │
│  Weather:  [ Rain                 ▼ ]   │
│  Event:    [ None                 ▼ ]   │
│                                         │
│           [ Predict Demand ]            │
├─────────────────────────────────────────┤
│      Tomorrow's predicted demand        │
│                 132  portions           │
│        📉 8% lower than normal          │
│                                         │
│        🤖 AI Explanation                │
│  Friday demand is historically lower,   │
│  and rain is expected tomorrow.         │
└─────────────────────────────────────────┘
```

**📖 完整的模块/字段/接口说明、接入自己模型的步骤、排错表 → [TEMPLATE.md](TEMPLATE.md)**

---

## 一分钟上手

```powershell
python -m backend.server --port 8000
# 打开 http://127.0.0.1:8000/
```

只依赖本机已有的 pandas / numpy / scikit-learn / SQLAlchemy / requests，**不联网也能跑**。

换题（不动代码，只换配置）：

```powershell
copy templates\food-demand.json template.json
```

接自己的模型：

```powershell
$env:MODEL_BACKEND = "http"
$env:MODEL_API_URL = "http://127.0.0.1:9000/predict"
python -m backend.server
```

---

## 两个运行入口（同一套业务逻辑）

| 入口 | 命令 | 依赖 | 适用场景 |
|---|---|---|---|
| 零依赖服务器 | `python -m backend.server` | pandas / numpy / scikit-learn / SQLAlchemy | 现场演示，离线可用 |
| FastAPI 应用 | `uvicorn backend.main:app --reload` | 额外需要 fastapi / uvicorn | 正式部署，自带 `/docs` |

两者都只是适配器：路由、错误码、JSON 由入口层处理，业务逻辑全在 `backend/service.py`，因此**行为不会漂移**，测试也直接打服务层。

---

## 页面只用到三个接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/config` | 模板 + 下拉项 + 数据摘要 —— 前端凭这一个响应渲染整个页面 |
| GET | `/api/options` | 只刷新下拉项 |
| POST | `/api/predict` | `{"fields": {...}}` → 预测值 / 倍率 / 解释 |

请求与响应的完整字段、错误码表见 [TEMPLATE.md](TEMPLATE.md#5-http-接口契约)。

---

## 目录结构

```
Hackathon/
├── template.json              # ★ 唯一配置源：标题/字段/文案/用哪个模型
├── templates/
│   └── food-demand.json       # 校园食堂示例模板（对应上面的示意图）
├── backend/
│   ├── template_config.py     # 读取 + 严格校验 template.json；CSV 列 → 下拉项
│   ├── model_api.py           # ★ 模型插件接口 + 本地统计 + 本地ML + 外接HTTP
│   ├── service.py             # 业务编排：校验字段、选插件、归一化结果
│   ├── server.py              # 零依赖标准库入口
│   ├── main.py                # FastAPI 入口
│   ├── predictor.py           # 本地 ML 引擎（ExtraTrees + 递归多步预测）
│   ├── ai.py                  # 规则洞察 + 异常检测 + 可选 LLM 叙事
│   ├── models.py              # ORM: sales_records / prediction_runs
│   └── database.py            # 引擎、会话、CSV 自动播种
├── frontend/
│   ├── index.html             # 卡片骨架（零字段硬编码）
│   ├── style.css              # 极简样式
│   ├── app.js                 # 按 /api/config 渲染表单 + 提交预测
│   └── legacy/                # 归档：早前的销售分析看板
├── data/
│   ├── menu_demand.csv        # 食堂需求数据（3,655 行）
│   ├── generate_menu_demand.py
│   ├── sales.csv              # 零售销售数据（14,620 行）
│   └── generate_sales.py
├── tests/test_api.py          # 46 个端到端测试
├── TEMPLATE.md                # ★ 模板/接口/接入模型 完整文档
└── requirement.txt
```

---

## 模型插件

`backend/model_api.py` 是唯一的模型接入层，三个实现：

| 插件 | 类型 | 说明 |
|---|---|---|
| `group-baseline` | 本地统计 | 通用条件均值因子模型：`baseline × Π(字段条件均值/基准)`。任何 CSV + 任何字段都能用；**解释文字就是它乘过的那些因子**，不是事后编的 |
| `sales-forecast` | 本地 ML | 把 `store/category/horizon` 映射到 ExtraTrees 递归预测，验证集营收 MAPE 13.05%，优于季节朴素基线 33.5% |
| `http` | 外接 | **你的模型 API**。POST 表单字段过去，取回 `value/baseline/explanation`；失败可自动回退本地插件 |

外接契约（只有 `value` 必填）：

```json
// → 发给你的
{ "template_id": "food-demand",
  "fields": { "menu": "Chicken Rice", "day": "Friday", "weather": "Rain", "event": "None" },
  "unit": "portions",
  "context": { "target": "portions", "requested_at": "2026-03-01T08:00:00+00:00" } }

// ← 你要返回的
{ "value": 132, "unit": "portions", "baseline": 143,
  "explanation": "Friday demand is historically lower, and rain is expected tomorrow.",
  "model": "canteen-xgb-v3" }
```

自己写进程内插件只需继承 `ModelPlugin`、实现 `predict()`、注册到 `PLUGINS`，然后让模板指向它。
两种接入方式的完整示例见 [TEMPLATE.md 第 6、7 节](TEMPLATE.md#6-接入你自己的模型-api重点)。

---

## 数据集

| 文件 | 规模 | 用途 | 重新生成 |
|---|---|---|---|
| `data/menu_demand.csv` | 3,655 行 / 730 天 / 5 菜单 | 食堂模板 | `python data/generate_menu_demand.py` |
| `data/sales.csv` | 14,620 行 / 731 天 / 4 门店 × 5 品类 | 零售模板 + ML 插件 | `python data/generate_sales.py` |

两个生成器都用固定随机种子，完全可复现，并内置了模型该学的真实信号（周末效应、天气、假日、促销等）。

---

## 归档：销售分析看板

早前的多图看板仍在 `/legacy/index.html`（配套的分析接口 `/api/summary`、`/api/timeseries`、`/api/breakdown`、`/api/momentum`、`/api/sales`、`/api/anomalies`、`/api/forecast`、`/api/insights`、`/api/predictions` 也一并保留且仍在测试覆盖内）。
不需要的话，删掉 `frontend/legacy/` 与 `backend/server.py` 里对应的 3 行白名单即可。

---

## 配置（`.env`）

所有值都有代码内默认值，`.env` 可以不建。见 `.env.example`；完整表格在 [TEMPLATE.md 第 6.2 节](TEMPLATE.md#62-环境变量)。
最常用的四个：`TEMPLATE_FILE`、`MODEL_BACKEND`、`MODEL_API_URL`、`OPENAI_API_KEY`（留空则只走规则引擎，不发任何网络请求）。

---

## 测试

```bash
python -m unittest discover -s tests -v      # 46 个用例，仅用标准库
pytest -q                                    # 装了 pytest 也可以
```

覆盖：模板加载的全部报错分支、三个模板接口、外接模型 API 的成功调用（含请求契约断言）与两种失败模式、字段校验、方法/错误码、两个模板各自的预测、以及归档的分析接口与 ML 预测。

---

## 已知限制

- `group-baseline` 假设各字段效应独立，强相关字段（如"周六"与"假日"）会重复计算，故有上下限截断；要更准请换训练模型或外接 API。
- 本地 ML 插件的训练在进程内完成，重启即重训（启动时会后台预热，首个请求不等待）。
- 接口当前无鉴权、无多租户，请勿直接暴露到公网。
