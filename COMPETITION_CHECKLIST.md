# 比赛当天要改哪些文件（COMPETITION_CHECKLIST.md）

一句话版：**正常只改 2 个文件 + 1 份数据**；接了你们自己的模型再多一个 `.env`。
其余都是框架代码，不要动。

```text
比赛当天要动的文件
├── ① template.json            ← 后端唯一配置源：数据 / 字段 / 模型 / 输出文案
├── ② frontend/js/config.js    ← 评委看到的第一屏：标题 / 文案 / KPI / Impact
├── ③ data/你们的.csv          ← 你们的数据
└── ④ .env                     ← 只在"接自己模型 / 临时换数据源"时改
```

---

## ① template.json — 必改，最重要的一个

这是后端唯一配置源。字段改了，前端表单自动跟着变，**不需要改任何前端代码**。

| 段落 | 要改的 key | 说明 |
|---|---|---|
| | `id` | 模板标识，会原样发给外接模型 |
| `app` | `brand` / `title` / `subtitle` / `footer` | 后端侧的标题（前端在线时以上 `config.js` 为准） |
| `dataset` | `path` | 你们的 CSV 路径（相对项目根目录） |
| | `target` | **要预测的数值列** |
| | `unit` / `target_label` / `date_column` | 单位 / 中文名 / 日期列 |
| `model` | `plugin` | `group-baseline`（自定义数据统计）或 `http`（你们的模型 API） |
| | `options.baseline_filter` / `baseline_label` | 什么叫"正常水平"（例如只算工作日） |
| | `options.effect_min_rows` | 最少样本数，默认 5 |
| `fields` | 每个字段：`name` / `label` / `type` / `source` / `column` / `default` / `required` / `placeholder` | **这就是表单**，见下表 |
| `output` | `headline` / `unit` / `decimals` / `delta_label` / `explanation_title` / `submit_label` / `locale` | 结果区的文字与单位 |

字段的三种 `source`：

| source | 写成什么样 | 用途 |
|---|---|---|
| `dataset` | `{ "name": "crop", "label": "Crop", "type": "select", "source": "dataset", "column": "crop" }` | 下拉框，选项自动取 CSV 该列的去重值 |
| `static` | `{ "name": "horizon", "type": "number", "source": "static", "options": [7,14,30] }` | 固定候选值 |
| `input` | `{ "name": "notes", "type": "text", "source": "input" }` | 自由输入，原样发给外接模型 |

---

## ② frontend/js/config.js — 必改（第一屏的观感）

| key | 改什么 |
|---|---|
| `projectName` / `logo` | 项目名、Logo 字母 |
| `category` | 左上角徽章（如 `AI FOR SUSTAINABILITY`） |
| `title` / `description` | Hero 大标题（可用 `<br>` 换行）与描述 |
| `hero` | 两个按钮文字、右侧小图表标题 |
| `analysis` | 分析区标题、副标题、按钮文字、`resultUnit` |
| `metrics` | 3 个数字卡 |
| `impact` | 4 个图标卡（🌱🌍⚡📈） |
| `inputs` | **只做离线兜底**：后端在线时会被 `template.json` 的 `fields` 覆盖 |

> `inputs` 什么时候会用到？只有"后端没启动、只用 Live Server 打开页面"时。
> 所以比赛当天可以不管它，但建议顺手改成和 template.json 一致的字段，避免离线演示时对不上。

---

## ③ 数据：data/你们的.csv

格式要求见 **[DATA_FORMAT.md](DATA_FORMAT.md)**（一行 = 一次观测；一个数值目标列 + 一个日期列 + 若干维度列）。

---

## ④ .env — 按需

| 变量 | 什么时候用 |
|---|---|
| `MODEL_BACKEND=http` + `MODEL_API_URL` + `MODEL_API_KEY` | 用你们自己的模型服务替换本地模型 |
| `MODEL_API_FALLBACK=off` | 模型 API 挂了不要静默回退（想暴露问题时） |
| `TEMPLATE_FILE` | 同时维护多套模板时切换 |
| `DATASET_FILE` | 临时换成评委给的数据，不改文件 |
| `MODEL_BACKEND=http` + `MODEL_API_URL` | 把预测（和解释）交给你们自己的服务，见上一节 |
| `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` | 路线 1 的参考服务用它调第三方大模型 |
| `OPENAI_API_KEY` | 只有归档看板的 `/api/insights` 会用到（可选） |

---

## 接第三方大模型（路线 1，推荐）

**数字交给可回测的本地模型，文字交给大模型。** 参考服务已经写好，不用从零写。

```powershell
# 终端 1：解释服务（内部调大模型）
$env:LLM_API_KEY  = "sk-..."                      # 任意 OpenAI 兼容网关
$env:LLM_BASE_URL = "https://api.deepseek.com/v1"
$env:LLM_MODEL    = "deepseek-chat"
python examples/llm_explainer_service.py --port 9000

# 终端 2：本项目走它
$env:MODEL_BACKEND = "http"
$env:MODEL_API_URL = "http://127.0.0.1:9000/predict"
python -m backend.server

# 上线前预检（真的发一次请求过去）
python -m backend.check_data --check-model-api
```

- 没网 / 没 key / 大模型超时 → **自动退回本地模型的话术**，页面照常出数，演示不会挂
- 想换成你们自己的模型服务 → 只改 `examples/llm_explainer_service.py` 里 `plugin.predict()` 那一步
- 供应商怎么选、base_url 怎么填 → 见 [TEMPLATE.md 第 6 节](TEMPLATE.md#6-接入你自己的模型-api重点)

---

## 不要动这些（改了容易坏）

| 文件 | 为什么 |
|---|---|
| `backend/service.py` / `server.py` / `main.py` | 业务编排与路由，接口契约在这层 |
| `backend/template_config.py` / `predictor.py` / `database.py` / `models.py` | 配置加载 / ML 引擎 / 存储 |
| `frontend/js/app.js` | 接线：它会把 template.json 的 fields 灌进表单（第 57 行）、把 unit 灌进结果区（第 60 行） |
| `frontend/js/services/api.js` | 已经写好，含离线回退；一般不用改 |
| `frontend/js/components/*.js` | 只在想改版式（加图表、加区块）时才动 |
| `tests/` | 除非加了功能想补测试 |

---

## 30 分钟最快流程

```powershell
# 1) 放数据
copy 你们的.csv data\my_data.csv

# 2) 让工具生成 fields 片段，顺便校验 + 预演接口
python -m backend.check_data --csv data/my_data.csv --target yield ^
    --field crop --field soil --field region --check-api

# 3) 把上一步打印的 dataset + fields 片段贴进 template.json，
#    再改 output 的 headline / unit / submit_label

# 4) 改 frontend/js/config.js 的文案与 KPI

# 5) 起服务，打开 http://127.0.0.1:8000/
python -m backend.server
```

想要一份完整模板而不是手贴，用它一键生成：

```powershell
python -m backend.check_data --csv data/my_data.csv --target yield ^
    --field crop --field soil --write-template templates/mine.json
$env:TEMPLATE_FILE = "templates/mine.json"
python -m backend.server
```

---

## 两个最容易踩的坑

**1. `config.js` 里的 `metrics` / `impact` 数字必须和当前 template.json 是同一份数据算出来的。**
现在填的是**校园用电量**的回测实测值（93% / 6.6% / 45 kWh / 86%），已经和默认模板对齐。
换题之后要重新跑一次回测并同步这几个数字，否则会出现"讲着农业的题、屏幕上写 kWh"。
你们的真实数字从这两个地方拿：

```powershell
python -m backend.check_data --csv data/my_data.csv --target yield --field crop   # 回测 MAPE / 准确率 / 相对参照系提升
# 或者运行时：
# GET /api/config  ->  model.backtest
```

**2. `fields[].name` 是前后端契约。**
改名字不需要改前端（表单是按 `/api/config` 渲染的），但：

- 你们外接的模型会收到新的 key（`fields` 里的名字变了）
- `baseline_filter` 里引用的列名与取值要跟着数据走，写错了 `check_data` 会直接报错

---

## 按角色的分工（对应 frontend/README 里的 A–E）

| 角色 | 主要动这些 |
|---|---|
| A · 后端 / 架构 | `.env`；只有在写"进程内插件"时才动 `backend/model_api.py` |
| B · AI / 数据 | 数据 CSV、`template.json` 的 `dataset` / `fields` / `model` |
| C · 前端 / UI | `frontend/js/config.js`、`components/*`、`css/style.css` |
| D · 集成 / 测试 | `python -m backend.check_data --check-api`、`python -m unittest discover -s tests` |
| E · 产品 / Pitch | `config.js` 的文案与 KPI 数字 |

---

## 相关文档

| 文档 | 内容 |
|---|---|
| [README.md](README.md) | 项目总览与快速开始 |
| [TEMPLATE.md](TEMPLATE.md) | 模板字段全参考、三个接口契约、接入自己的模型 |
| [DATA_FORMAT.md](DATA_FORMAT.md) | 自定义数据的格式要求与校验工具 |
| [frontend/README.md](frontend/README.md) | 前端结构与组件职责 |
