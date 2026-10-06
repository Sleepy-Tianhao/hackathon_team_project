# 系统架构（ARCHITECTURE.md）

**精确到文件**的架构图 + 每个文件的职责。想快速上手看 [README.md](README.md)；
改配置看 [TEMPLATE.md](TEMPLATE.md)；换数据看 [DATA_FORMAT.md](DATA_FORMAT.md)；
比赛当天改哪些看 [COMPETITION_CHECKLIST.md](COMPETITION_CHECKLIST.md)。

---

## 1. 分层架构图（文件级）

```text
┌────────────────────────────── 浏览器（纯静态 ES Module，无框架）──────────────────────────────┐
│  frontend/index.html                只有 #app / #toast 两个容器 + 一行 <script type="module">  │
│  frontend/css/style.css             全部样式（布局 / 卡片 / 响应式）                            │
│  frontend/.vscode/settings.json     Live Preview 配置（可选，与运行无关）                      │
│                                                                                              │
│  frontend/js/app.js            ★ 入口：GET /api/config → 组合组件 → 绑表单 → 调 API            │
│    ├── js/components/header.js       导航栏                                                   │
│    ├── js/components/hero.js         Hero（含占位柱状图）                                      │
│    ├── js/components/metrics.js      3 张 KPI 卡                                              │
│    ├── js/components/analysis.js   ★ 表单 + 结果卡（把字段渲染成 select/text）                  │
│    ├── js/components/impact.js       4 张 Impact 卡                                           │
│    └── js/components/footer.js       页脚                                                     │
│  frontend/js/config.js         ★ 外壳文案：项目名 / 标题 / 描述 / Hero / Metrics / Impact       │
│  frontend/js/services/api.js   ★ 与后端通信的唯一出口（fetch + 超时 + 地址候选 + Mock 回退）     │
└────────────────────────────────────────────┬─────────────────────────────────────────────────┘
                          HTTP/1.1 + JSON（原生 fetch）
     GET /api/config · GET /api/options · POST /analyze · POST /api/predict
┌────────────────────────────────────────────▼─────────────────────────────────────────────────┐
│ 入口层（二选一，暴露同一批路由与同一套 service 调用）                                            │
│   backend/server.py   零依赖：ThreadingHTTPServer + 路由 + 静态托管 + ES Module MIME + 防穿越   │
│   backend/main.py     FastAPI + uvicorn：路由声明 + CORSMiddleware + StaticFiles（自带 /docs）  │
│   两者都只做：路由分发、读 body、错误码、托管前端 —— 不含业务逻辑                                  │
└────────────────────────────────────────────┬─────────────────────────────────────────────────┘
┌────────────────────────────────────────────▼─────────────────────────────────────────────────┐
│ 编排层                                                                                        │
│   backend/service.py                                                                          │
│     字段校验（validate_fields）→ 选插件（resolve_model）→ 归一化结果 → 三种返回形状               │
│     模板接口：get_config / get_field_options / analyze / run_prediction                        │
│     归档分析：get_summary / timeseries / breakdown / momentum / sales / anomalies /            │
│               forecast / insights / predictions / warm_up                                     │
├────────────────── 配置与数据 ──────────────────┬──────────────── 模型 ─────────────────────────┤
│ backend/template_config.py                      │ backend/model_api.py  ★ 模型插件层            │
│   load_template（严格校验 template.json）        │   PredictionResult（统一结果信封）             │
│   dataset_path（含 DATASET_FILE 覆盖 / 锁定）    │   ModelPlugin（插件基类）                      │
│   dataset_frame（读 CSV · 解析 · 清洗 · mtime缓存）│   ├── group-baseline  条件均值因子（默认）      │
│   field_options（去重值 → 下拉项）                │   ├── sales-forecast  本地 ML               │
│   dataset_meta（行数 / 日期范围 / 均值）          │   └── http            外接你们的模型 API      │
│   backtest_group_baseline（留一天法回测）          │   resolve_model / fallback_plugin / warm_up  │
│                                                 │ backend/predictor.py                          │
│ backend/database.py                             │   ExtraTrees 递归多步预测 + 95% 区间          │
│   引擎 / 会话 / CSV→SQLite 播种 / ensure_seeded   │   load_frame/get_frame/get_engine             │
│ backend/models.py                               │   log_prediction_run（预测审计）              │
│   ORM：sales_records · prediction_runs           │ backend/ai.py                                 │
│                                                 │   规则洞察 / 异常检测 / 可选 LLM 叙事          │
└─────────────────────────────────────────────────┴──────────────────────────────────────────────┘
                              │
                    HTTP/1.1 + JSON（requests，可选）
                              ▼
              examples/llm_explainer_service.py      路线 1 参考服务
                本地统计模型算 value/baseline → 大模型写一句解释 → 按契约返回
                              │
                    HTTP/1.1 + JSON（requests）
                              ▼
                   第三方大模型网关（OpenAI 兼容） / 你们的模型 API
```

---

## 2. 配置与数据文件

```text
template.json                  ★ 默认模板（energy-forecast）：数据集 / 字段 / 插件 / 输出文案
templates/food-demand.json     备用模板：校园食堂需求
templates/retail-sales.json    备用模板：零售销售（走本地 ML 插件）

data/energy_consumption.csv    默认数据集  3,655 行 / 731 天 / 5 栋楼   ← 后端只读
data/menu_demand.csv           食堂数据集  3,655 行 / 730 天 / 5 菜单
data/sales.csv                 零售数据集  14,620 行 / 731 天         ← 同时是 sales.db 的播种源
data/samples/coffee_shop_sales.csv        自定义数据示例（1,000 行）
data/samples/coffee_shop.template.json    与它配套的示例模板
data/generate_energy.py        可复现生成器（固定随机种子）
data/generate_menu_demand.py   可复现生成器
data/generate_sales.py         可复现生成器
data/sales.db                  SQLite（启动自动从 sales.csv 播种，已 gitignore，可随时重建）

backend/check_data.py          命令行工具：校验数据 / 生成示例 / 写模板 / 预演 API / 预检外接模型
tests/test_api.py              67 个端到端测试（仅用标准库 unittest）
```

---

## 3. 每个文件的职责

### 3.1 根目录

| 文件 | 职责 | 谁读它 |
|---|---|---|
| `template.json` | **后端唯一配置源**：`id / app / dataset / model / fields[] / output` | `backend/template_config.py` |
| `.env` / `.env.example` | 本地配置：`HOST / PORT / DATABASE_URL / SKIP_DB_SEED / MODEL_* / LLM_* / OPENAI_*` | `database.py`（dotenv）、`server.py`、`model_api.py`、`ai.py`、示例服务 |
| `.gitignore` | 忽略 `.env` / `*.db` / `__pycache__` / `tests/_tmp` / `.scratch/` 等 | git |
| `requirement.txt` | **FastAPI 部署方式**的依赖清单（默认的零依赖入口用不到） | 人 / pip |
| `README.md` | 项目总览与快速开始 | 人 |
| `TEMPLATE.md` | 模板字段全参考、三个接口契约、接入自己模型的完整说明 | 人 |
| `DATA_FORMAT.md` | 自定义数据的格式要求 + 校验工具用法 | 人 |
| `COMPETITION_CHECKLIST.md` | 比赛当天改哪些文件、按角色分工 | 人 |
| `ARCHITECTURE.md` | 本文件 | 人 |
| `app.py` | ⚠️ **队友的 Streamlit「学生成绩分析系统」原型，与本系统没有任何引用关系**，且 `streamlit` 不在 `requirement.txt` 里 | 无 |

### 3.2 frontend/（浏览器侧）

| 文件 | 职责 |
|---|---|
| `index.html` | 唯一的 HTML：`#app` / `#toast` 容器 + 引入 `app.js`（`type="module"`） |
| `css/style.css` | 全部样式：CSS 变量、导航、Hero、卡片、表单、结果区、Impact、Toast、响应式 |
| `js/app.js` | 入口：`fetchConfig()` → 用 `template.fields` 覆盖 `CONFIG.inputs` → `renderApp()` → 绑表单 → `analyze()` → `updateResult()` |
| `js/config.js` | **外壳文案**：`projectName / logo / category / title / description / hero / analysis / metrics / impact / inputs（离线兜底）` |
| `js/services/api.js` | 通信唯一出口：`candidateBases()` 地址解析 → `fetch` + `AbortController`(60s) → 错误取 `detail` → 全失败回退 `analyzeMock()` |
| `js/components/header.js` | 顶部导航（Dashboard / Analysis / Impact 锚点） |
| `js/components/hero.js` | Hero 区：徽章 + 大标题 + 描述 + 两个按钮 + 占位柱状图 |
| `js/components/metrics.js` | “Key Metrics” 3 张数字卡（读 `CONFIG.metrics`） |
| `js/components/analysis.js` | **核心区**：输入表单（按 `CONFIG.inputs` 生成 select/text）+ 结果卡（`#result-value/average/change/confidence/explanation`） |
| `js/components/impact.js` | “Impact” 4 张图标卡（读 `CONFIG.impact`） |
| `js/components/footer.js` | 页脚 |
| `README.md` | 前端自己的说明（结构、运行方式、契约） |

### 3.3 backend/（服务端）

| 文件 | 职责 | 关键入口 |
|---|---|---|
| `server.py` | **入口 A（零依赖）**：ThreadingHTTPServer、`ROUTES` / `POST_ROUTES` 路由表、JSON 响应头、`OPTIONS`(CORS)、读 body、静态文件与 ES Module MIME、目录穿越防护 | `main()` / `build_server()` |
| `main.py` | **入口 B**：FastAPI 路由声明（`/api/config`、`/api/options`、`POST /analyze`、`POST /api/predict` + 归档分析接口）、CORSMiddleware、StaticFiles | `app` |
| `service.py` | **编排层**：字段校验（422）、插件选择、错误码映射、`warm_up`；模板接口与归档分析接口的业务实现 | `get_config / analyze / run_prediction` |
| `template_config.py` | 读 + 严格校验 `template.json`；CSV 定位（`DATASET_FILE` 覆盖/锁定）、解析（保留字面量 `None`）、target 转数值、按 mtime 缓存；生成下拉项与数据摘要 | `load_template / dataset_frame / field_options / dataset_meta` |
| `model_api.py` | **模型插件层**：`PredictionResult`、`ModelPlugin`、三个插件（`group-baseline` / `sales-forecast` / `http`）、留一天法回测、注册表与回退 | `resolve_model / PLUGINS` |
| `predictor.py` | 本地 ML 引擎：特征工程、模型选型（Ridge vs ExtraTrees）、批量递归多步预测、95% 区间、SQLite 读取、预测审计写入 | `forecast / get_engine` |
| `ai.py` | 规则洞察、异常检测（z-score）、可选 LLM 叙事（OpenAI 兼容 `/chat/completions`）—— **只被归档的 `/api/insights` 使用** | `generate_insights` |
| `database.py` | SQLAlchemy 引擎/会话、`Base`、CSV→SQLite 播种（`load_csv`）、`ensure_seeded` | `get_db` |
| `models.py` | ORM 模型：`sales_records`（门店/品类/日销量事实表）、`prediction_runs`（预测审计） | — |
| `check_data.py` | CLI 工具：`--csv/--target/--field` 校验、`--sample` 生成示例、`--write-template`、`--check-api` 预演、`--check-model-api` 预检 | `main()` |
| `__init__.py` | 包标记 |

### 3.4 examples/

| 文件 | 职责 |
|---|---|
| `llm_explainer_service.py` | **路线 1 参考服务**（跑在 9000）：用本地统计插件算 value/baseline，再调 OpenAI 兼容网关写一句解释；没 key / 断网 / 超时自动退回模型自带话术。含 `GET /health`、`POST /predict`（GET 打 `/predict` 返回 405 + 用法示例） |

### 3.5 tests/

| 文件 | 职责 |
|---|---|
| `test_api.py` | 67 个端到端测试：模板校验分支、`/api/config` / `POST /analyze` / `POST /api/predict` 契约、外接模型成功与两种失败、ES Module MIME、静态资源、目录穿越、confidence 与回测一致性、`DATASET_FILE` 覆盖、`check_data`、LLM 解释服务、**HTTP 接口清单未变的回归断言** |

---

## 4. 四条主要请求路径（谁调用谁）

**① 页面加载**

```text
index.html → app.js → api.js:fetchConfig()
  → GET /api/config
    → server.py 或 main.py（路由）
      → service.get_config()
        → template_config.load_template()     读 template.json
        → template_config.dataset_frame()     读 data/*.csv（只读 + mtime 缓存）
        → template_config.field_options()     去重值 → 下拉项
        → template_config.dataset_meta()      行数 / 日期范围 / 均值
        → model_api.backtest_group_baseline() 留一天法回测 → confidence 来源
  ← { template, options, dataset, model }
app.js 用 template.fields 覆盖 CONFIG.inputs 并 renderApp()
```

**② 预测（默认模板：本地统计）**

```text
表单 submit → api.js:analyze(扁平字段表)
  → POST /analyze
    → service.analyze() → run_prediction()
      → validate_fields()                  必填 / 候选值 / 未知字段 → 422
      → model_api.resolve_model()          取 template.model.plugin
      → GroupBaselineModel.predict()       基准 × Π 各字段条件因子
      → PredictionResult.to_payload()
      → 追加别名 prediction / average / change_percent / confidence
  ← 前端 updateResult() 填 5 个元素
```

**③ 预测（接你们的模型 / 大模型，路线 1）**

```text
service.run_prediction()
  → ExternalModelClient.predict()          requests.post(MODEL_API_URL)
      → examples/llm_explainer_service.py
          → （本地）GroupBaselineModel.predict() 算出 value/baseline
          → （网络）requests.post(LLM_BASE_URL + /chat/completions) 写解释
      ← { value, baseline, confidence, explanation, model, meta }
  ← 成功：meta.external_explanation_source = "llm" / "local-model"
  ← 失败：回退本地插件，meta.fallback = true（或 MODEL_API_FALLBACK=off 时 502）
```

**④ 归档分析接口（零售看板 / ML）**

```text
GET /api/summary · timeseries · breakdown · momentum · sales · anomalies · forecast · insights
  → service.py 里对应的 get_*()
      → predictor.get_frame(db)              读 SQLite sales_records（由 sales.csv 播种）
      → predictor.get_engine(frame)          选型 Ridge vs ExtraTrees 并缓存
      → ai_layer.detect_anomalies / generate_insights（可选 LLM 叙事）
  ← JSON（销售分析看板用；当前默认前端不使用这组接口）
```

---

## 5. 部署时哪些必须带、哪些可重建

| 类别 | 文件 |
|---|---|
| **运行必需** | `backend/`、`frontend/`、`template.json`、模板引用的 `data/*.csv` |
| FastAPI 方式额外需要 | `requirement.txt` 里的包（`fastapi / uvicorn`…） |
| 可自动重建 | `data/sales.db`（启动从 `sales.csv` 播种）、`__pycache__/` |
| 可选（工具/示例） | `backend/check_data.py`、`examples/`、`data/generate_*.py`、`data/samples/` |
| 纯文档 | `*.md` |
| 与本系统无关 | `app.py`（Streamlit 原型） |
```

---

## 6. 一句话记住每个目录

```text
frontend/   界面 + 与后端唯一的通信出口（换字段不用动它）
backend/    服务端：入口 → 编排 → 配置/数据 → 模型 四层
templates/  备用题目（换题 = copy 一个到 template.json）
data/       数据集（后端只读）+ 可复现生成器；sales.db 是可重建的派生库
examples/   路线 1 参考服务（本地模型出数 + 大模型写解释）
tests/      67 个端到端测试，仅依赖标准库
```
