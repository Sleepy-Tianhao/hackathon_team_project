# 模板使用说明（TEMPLATE.md）

一个卡片式预测页面：**填表单 → 出预测值 + 变化幅度 + AI 解释**。
页面上的每一个字、每一个下拉框都来自 `template.json`；预测由**模型插件**产生，插件自带两个本地实现，也可以**外接你自己的模型 API**。

```
┌─────────────────────────────────────────┐
│            SMART FOOD FORECAST          │  ← app.title / app.subtitle
├─────────────────────────────────────────┤
│  Menu:     [ Chicken Rice         ▼ ]   │  ← fields[]，下拉项来自 CSV
│  Day:      [ Friday               ▼ ]   │
│  Weather:  [ Rain                 ▼ ]   │
│  Event:    [ None                 ▼ ]   │
│                                         │
│           [ Predict Demand ]            │  ← output.submit_label
├─────────────────────────────────────────┤
│      Tomorrow's predicted demand        │  ← output.headline
│                132                      │  ← result.value
│              portions                   │  ← output.unit
│      📉 8% lower than normal            │  ← result.delta_text
│                                         │
│      🤖 AI Explanation                  │  ← output.explanation_title
│      Friday demand is historically      │  ← result.explanation
│      lower, and rain is expected.       │
└─────────────────────────────────────────┘
```

---

## 1. 快速开始

```bash
python -m backend.server --port 8000
# 浏览器打开 http://127.0.0.1:8000/
```

换成"校园食堂需求预测"示例（不动任何代码，只换配置文件）：

```powershell
copy templates\food-demand.json template.json
# 或者不覆盖文件，用环境变量临时指定：
$env:TEMPLATE_FILE = "templates/food-demand.json"; python -m backend.server
```

想接自己的模型 API：

```powershell
$env:MODEL_BACKEND   = "http"
$env:MODEL_API_URL   = "http://127.0.0.1:9000/predict"
$env:MODEL_API_KEY   = "your-token"     # 可选
python -m backend.server
```

---

## 2. 架构与模块职责

```
浏览器 frontend/
   │   GET  /api/config      → 拿模板 + 下拉项 + 数据摘要，渲染整个页面
   │   POST /api/predict     → 提交 {fields:{...}}，拿回预测结果
   ▼
入口层   backend/server.py   (零依赖标准库)   ← 只做路由、读 body、错误码
        backend/main.py     (FastAPI)
   ▼
编排层   backend/service.py  ← 校验字段、挑模型插件、把结果归一化成前端契约
   ├── backend/template_config.py  ← 读取/校验 template.json，解析下拉项与数据摘要
   ├── backend/model_api.py        ← 模型插件：本地统计 / 本地ML / 你的 HTTP 模型
   ├── backend/predictor.py        ← 本地 ML 预测引擎（ExtraTrees + 递归多步）
   ├── backend/ai.py               ← 规则洞察 + 异常检测 + 可选 LLM 叙事
   ├── backend/models.py           ← ORM：sales_records / prediction_runs
   └── backend/database.py         ← 引擎、会话、CSV 播种
```

| 文件 | 职责 | 你什么时候改它 |
|---|---|---|
| `template.json` | **唯一配置源**：标题、字段、下拉项来源、输出文案、用哪个插件 | 换题、加字段、改文案 —— 最常改的就是它 |
| `backend/template_config.py` | 加载 + 严格校验模板；把 CSV 列变成下拉项 | 需要新的字段类型/来源时 |
| `backend/model_api.py` | 模型插件接口 + 三个实现 | **接自己的模型时看这里** |
| `backend/service.py` | `get_config` / `get_field_options` / `run_prediction` | 改校验规则时 |
| `backend/server.py` | 标准库服务器（现场演示用，无需 pip 安装） | 加路由时 |
| `backend/main.py` | FastAPI 入口（正式部署，自带 /docs） | 加路由时 |
| `frontend/index.html · style.css · app.js` | 卡片 UI，**零硬编码字段名** | 改视觉时 |
| `backend/predictor.py · ai.py` | 本地 ML 插件与被归档的销售看板所用 | 一般不用改 |
| `tests/test_api.py` | 46 个端到端测试 | 加功能时补测试 |

---

## 3. `template.json` 完整参考

```json
{
  "id": "food-demand",                                  // 模板标识，会原样发给外接模型
  "app":     { "brand": "CAMPUS",                       // 标题上方小标签（可空）
               "title": "SMART FOOD FORECAST",          // 大标题（必填）
               "subtitle": "AI-powered Campus Food Forecast",  // 副标题（必填）
               "footer": "页脚小字（可空）" },
  "dataset": { "path": "data/menu_demand.csv",           // 相对项目根目录
               "date_column": "date",                    // 可选，用于页面的日期范围提示
               "target": "portions",                     // 预测目标列（必填）
               "unit": "portions",                       // 单位，显示在数字下方
               "target_label": "需求份数" },              // 中文名，用于本地插件的解释
  "model":   { "plugin": "group-baseline",               // 用哪个插件（必填）
               "options": { } },                         // 插件自己的参数
  "fields":  [ ... ],                                    // 表单字段，见下
  "output":  { "headline": "Tomorrow's predicted demand",
               "subheadline": "可选说明",
               "unit": "portions", "decimals": 0,
               "delta_label": "vs. normal",
               "explanation_title": "AI Explanation",
               "submit_label": "Predict Demand",
               "locale": "en" }                          // zh | en，决定内置文案语言
}
```

### 3.1 字段（`fields[]`）每个键的含义

| 键 | 必填 | 说明 |
|---|---|---|
| `name` | ✅ | 字段名，会作为 `fields` 的 key 发给模型 |
| `label` | ✅ | 显示在左侧的标签 |
| `type` | | `select` / `number` / `text`，默认 `select` |
| `source` | | `dataset` = 下拉项取 CSV 某列的去重值；`static` = 用本字段的 `options` |
| `column` | source=dataset 时 ✅ | 对应 CSV 的列名 |
| `options` | source=static 时 ✅ | 静态候选值数组，如 `[7,14,30,60,90]` |
| `required` | | 默认 `true`；`false` 时下拉会多一个空选项，空值会被传给模型 |
| `default` | | 页面初始选中值（不填则取第一个候选） |
| `min` / `max` | | 仅 `type=number`，后端会校验范围 |
| `suffix` | | 输入框的 placeholder |
| `help` | | 悬停提示（title） |

**控件映射**：字段有候选值（dataset 或 static）→ 渲染成下拉框；没有候选值且 `type=number` → 数字输入框；否则文本框。
所以"预测天数"这种写法会渲染成下拉框：

```json
{ "name": "horizon", "label": "Horizon", "type": "number",
  "source": "static", "options": [7, 14, 30, 60, 90], "default": 30, "suffix": "days" }
```

---

## 4. 加一个字段：改 3 处（都不用动代码）

以食堂模板加"温度"为例。先在 CSV 里加一列 `temperature`，然后在 `template.json` 的 `fields` 追加：

```json
{ "name": "temperature", "label": "Temp", "type": "select",
  "source": "dataset", "column": "temperature", "required": true, "default": "Mild" }
```

完成。下拉框会自动出现 CSV 里的所有取值，本地统计插件也会自动把它作为一个因子参与预测与解释。
**前端不需要改任何一行**——它按 `/api/config` 返回的字段列表渲染。

---

## 5. HTTP 接口契约

### `GET /api/config` — 页面初始化（一次调用拿到全部信息）

```json
{
  "template": { ...上面 template.json 的完整内容... },
  "options":  { "menu": ["Chicken Rice", "..."], "day": ["Friday", "..."],
                "weather": ["Rain", "..."], "event": ["None", "..."],
                "horizon": [7, 14, 30, 60, 90] },
  "dataset":  { "rows": 3655, "target": "portions", "target_label": "需求份数",
                "unit": "portions", "target_mean": 77.26,
                "date_min": "2024-01-01", "date_max": "2025-12-31" }
}
```

### `GET /api/options` — 只刷新下拉项

返回 `{ "options": {...}, "dataset": {...} }`，用于数据更新后不重载模板。

### `POST /api/predict` — 预测

请求：

```json
{ "fields": { "menu": "Chicken Rice", "day": "Friday", "weather": "Rain", "event": "None" } }
```

响应：

```json
{
  "value": 58.2,                       // 数值（已按 output.decimals 取整）
  "formatted": "58",                   // 带千分位的字符串，直接显示
  "unit": "portions",
  "baseline": 92.0,                    // "正常水平"，用于对比
  "delta": -0.3683,                    // 相对幅度，-0.3683 = 低 37%
  "delta_text": "37% lower than normal",  // 已本地化的文案
  "delta_label": "vs. normal",
  "direction": "down",                 // up | down | flat，前端用来上色/箭头
  "headline": "Tomorrow's predicted demand",
  "subheadline": "基于历史条件的需求预测",
  "explanation": "Rain averages 72 (22% below); ... Against a typical weekday of 92, the combined forecast is 58 portions.",
  "explanation_title": "AI Explanation",
  "explanation_source": "local-baseline",  // local-baseline | ml-forecast | external-api
  "model": "group-baseline",           // 实际产出这个结果的模型
  "fields": { ...回显提交的字段... },
  "evidence": [ { "field": "day", "value": "Friday", "mean": 81.99, "effect": -0.1063, "rows": 520 } ],
  "meta": { "plugin": "group-baseline", "elapsed_ms": 12.4, ... }
}
```

### 错误码

| 状态 | 场景 | 返回 |
|---|---|---|
| 400 | body 不是合法 JSON | `{"detail": "请求体不是合法 JSON: ..."}` |
| 405 | GET 请求 `/api/predict`，或 POST 请求只支持 GET 的路由 | `{"detail": "... only supports GET"}` |
| 422 | 缺必填字段 / 值不在候选内 / 未知字段 / 类型不对 | `{"detail": "缺少必填字段 'weather' (Weather)"}` |
| 500 | 模板配错（文件缺失、JSON 非法、插件名不存在、CSV 列不存在） | `{"detail": "<精确原因>"}` |
| 502 | 外接模型 API 报错且关闭了本地回退 | `{"detail": "模型调用失败: ..."}` |

---

## 6. 接入你自己的模型 API（重点）

### 6.1 三步

1. 起一个能接收 POST JSON 的服务（任何语言/框架，本地或云端）。
2. 按第 6.3 的契约返回 JSON。
3. 让本项目走 HTTP 插件：设置 `MODEL_BACKEND=http` 和 `MODEL_API_URL`。

### 6.2 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `MODEL_BACKEND` | 模板里的 `model.plugin` | 设为 `http` 即强制走外接 API；也可设成 `group-baseline` / `sales-forecast` |
| `MODEL_API_URL` | 无 | 外接模型地址（必填）。也可写进模板 `model.options.url` |
| `MODEL_API_KEY` | 空 | 有值时加 `Authorization: Bearer <key>` |
| `MODEL_API_TIMEOUT` | `15` | 秒 |
| `MODEL_API_FALLBACK` | `local` | 外接失败时回退到本地插件（`meta.fallback=true`）；设为 `off` 则直接返回 502 |
| `TEMPLATE_FILE` | `template.json` | 指定用哪个模板文件 |

### 6.3 请求（本项目发给你的）

```http
POST $MODEL_API_URL
Content-Type: application/json
Authorization: Bearer $MODEL_API_KEY        # 仅当设置了 key

{
  "template_id": "food-demand",
  "fields": { "menu": "Chicken Rice", "day": "Friday", "weather": "Rain", "event": "None" },
  "unit": "portions",
  "context": { "target": "portions", "target_label": "需求份数",
               "requested_at": "2026-03-01T08:00:00+00:00" }
}
```

### 6.4 响应（你返回给本项目的）

**只有 `value` 是必须的**，其余都可选；可选字段缺省时本项目会自动补算或留空。

```json
{
  "value": 132,                                  // 必填，数字。也接受 prediction/predicted/demand/result
  "unit": "portions",                            // 可选，缺省用模板里的 unit
  "baseline": 143,                               // 可选，"正常水平"，有了就能显示"低 x%"
  "delta": -0.077,                               // 可选，不给则用 value/baseline 计算
  "explanation": "Friday demand is historically lower, and rain is expected tomorrow.",
  "model": "canteen-xgb-v3",                     // 会显示在结果下方
  "evidence": [ { "label": "Friday", "effect": -0.11 } ],
  "meta": { "version": "2026-03-01" }            // 原样透传给前端
}
```

以上对象也可以整体嵌在 `{"data": {...}}` 里返回。

### 6.5 你的服务端最小实现（FastAPI 示例）

```python
from fastapi import FastAPI
app = FastAPI()

@app.post("/predict")
def predict(body: dict):
    fields = body["fields"]                    # 页面提交的字段
    # ... 这里调用你自己的模型 ...
    value = 132
    baseline = 143
    return {
        "value": value,
        "unit": body.get("unit", ""),
        "baseline": baseline,
        "explanation": "Friday demand is historically lower, and rain is expected tomorrow.",
        "model": "canteen-xgb-v3",
    }
```

### 6.6 失败行为

| 情况 | 默认（`MODEL_API_FALLBACK=local`） | 设 `off` 时 |
|---|---|---|
| 连不上 / 超时 / 非 2xx / 返回非 JSON / 没有数字 value | 静默回退到本地插件，响应里 `meta.fallback=true` + `fallback_reason` | 返回 502，`detail` 说明原因 |

页面在这种回退情况下会在结果下方显示红色提示"外部模型不可用，已本地回退"。

---

## 7. 自定义进程内插件（不走 HTTP）

如果你更想把模型跑在同一个进程里（例如加载本地 `.pkl`），在 `backend/model_api.py` 里加一个类：

```python
class MyModel(ModelPlugin):
    name = "my-model"                     # ← 模板里写这个字符串

    def predict(self, fields, frame, db=None) -> PredictionResult:
        # fields: {"menu": "Chicken Rice", ...}  已经过校验
        # frame:  dataset 的 pandas DataFrame（缓存过的）
        # db:     SQLAlchemy Session，需要查库时用
        value = ...                        # 你的模型输出
        return PredictionResult(
            value=value,
            unit=self.template["dataset"].get("unit", ""),
            baseline=...,                  # 可选
            explanation="为什么是这个数",
            explanation_source="my-model",
            model=self.name,
            evidence=[],                   # 可选，调试/前端展示
            meta={},                       # 可选
        )

PLUGINS[MyModel.name] = MyModel        # 注册
```

然后在 `template.json` 里把 `model.plugin` 改成 `"my-model"` 即可。

三个参数的含义：

| 参数 | 类型 | 说明 |
|---|---|---|
| `fields` | `dict` | 已按模板校验/转换后的字段值（数字字段是 float，空值是非必填字段的 `""`） |
| `frame` | `DataFrame \| None` | 模板 `dataset.path` 的 CSV，按 mtime 缓存 |
| `db` | `Session \| None` | 标准库服务器/FastAPI 都会传入；离线纯 CSV 插件可以忽略 |

---

## 8. 自带插件说明

### 8.1 `group-baseline`（通用本地统计基线，无训练）

公式：

```
baseline   = mean(target | baseline_filter)            # 默认全量均值
factor_i   = mean(target | 字段i = 取值) / baseline     # 至少 effect_min_rows 条历史才算
prediction = clamp(baseline × Π factor_i, 0.2×baseline, 5×baseline)
```

- 每个 factor 都会进 `evidence`，**解释文字就是这些 factor 拼出来的**，不是事后编的。
- `model.options.baseline_filter`：限定"正常水平"的口径。食堂模板把它限定为"周一至周五"，所以周五才会显示"比正常低"。
- `model.options.effect_min_rows`：样本太少就不采信该因子（默认 5）。
- **已知局限**：假设各字段效应相互独立，强相关的字段（例如"周六"和"假日"）会重复计算，因此加了上下限截断（触发时解释末尾会标注）。要更准就换成你自己的模型或 `sales-forecast` 那种训练模型。

### 8.2 `sales-forecast`（本地 ML，销售示例）

- 把字段 `store` / `category` / `horizon` 映射到 `backend/predictor.py` 的 ExtraTrees 递归预测。
- 预测值 = 未来 N 天的**日均营收**；baseline = 同范围的历史日均营收；解释包含验证集 MAPE 与相对季节朴素基线的提升。
- 每次预测都会写一行 `prediction_runs` 审计记录（可用 `GET /api/predictions` 查看）。

---

## 9. 换成你自己的数据

1. 把 CSV 放进 `data/`（UTF-8；建议带 BOM 以便 Excel 打开）。
2. `dataset.path` 指向它，`dataset.target` 写你要预测的数值列名。
3. `fields[]` 里每个 `source=dataset` 字段的 `column` 写 CSV 的真实列名。
4. 重启服务。下拉项 = 该列的去重值，自动按字母/大小排序。

> 注意：CSV 里的字面量 `None` / `NA` 会被当作正常字符串（不是缺失值），这是刻意的——否则食堂模板里最常见的 `event=None` 会凭空消失。

---

## 10. 前端如何工作

`frontend/app.js` 只做三件事：

1. `GET /api/config` → 写入标题/副标题/页脚/按钮文案，按 `fields[]` 生成表单；
2. 点按钮 → `POST /api/predict`，body 为 `{fields:{...}}`；
3. 把结果渲染进 `#result` 区块。

因此**没有任何字段名写死在 HTML/JS 里**。可二次开发的元素 id：

| id | 内容 |
|---|---|
| `#brand` / `#app-title` / `#app-subtitle` / `#footer` | 标题区 |
| `#fields` | 表单字段容器（动态生成 `.row`） |
| `#submit` | 主按钮 |
| `#form-error` | 错误提示条 |
| `#result` | 结果区（`hidden` 控制显隐） |
| `#result-headline` / `#result-value` / `#result-unit` / `#result-delta` | 数值区 |
| `#result-explanation` / `#explain-title` | AI 解释区 |
| `#result-meta` | 模型名 / 来源 / 耗时 / 回退提示 |

---

## 11. 排错

| 现象 | 原因与处理 |
|---|---|
| 页面显示"配置加载失败" + `template file not found` | `template.json` 不在项目根目录，或 `TEMPLATE_FILE` 指向了不存在的文件 |
| `... is not valid JSON: ...` | template.json 有语法错误（多余逗号最常见），提示里带行号列号 |
| `fields[2].column is required` / `'nope' is not a column` | 字段的 column 与 CSV 列名不一致；错误信息会列出 CSV 里可用的列 |
| `unknown model plugin 'x'` | `model.plugin` 或 `MODEL_BACKEND` 写错，可用值为 `group-baseline` / `sales-forecast` / `http` |
| 下拉框为空 | 该列全是空值，或 `dataset.path` 指错了文件 |
| 返回 422 | 字段校验没过，`detail` 里有具体是哪个字段、哪个值 |
| 返回 502 | 外接模型 API 不可用且 `MODEL_API_FALLBACK=off`；去掉 off 可自动本地回退 |
| 预测数字离谱 | 本地统计插件受因子截断影响；查看响应的 `evidence` 与 `meta.clamped` |

---

## 12. 测试

```bash
python -m unittest discover -s tests -v      # 46 个用例，仅用标准库
pytest -q                                    # 装了 pytest 也可以
```

覆盖：模板加载与全部报错分支、`/api/config` / `/api/options` / `POST /api/predict`、
外接模型 API 成功调用（含请求契约断言）与两种失败模式、字段校验、方法/错误码、
两个模板各自的预测、以及原有销售分析接口与 ML 预测。
