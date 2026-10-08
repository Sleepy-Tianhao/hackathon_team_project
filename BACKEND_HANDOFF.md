# 后端交接说明（BACKEND_HANDOFF.md）

> **由前端负责人写给后端同学。** 目标：让你不用问我任何问题，就能把后端做完，并且**永远不破坏前端**。
> 配套阅读：接口细节见 [TEMPLATE.md 第 5 节](TEMPLATE.md)，数据格式见 [DATA_FORMAT.md](DATA_FORMAT.md)，文件布局见 [ARCHITECTURE.md](ARCHITECTURE.md)。

---

## 0. 一句话

前端只依赖 **3 个接口 + 1 份配置**。你的活是：**把数据接进来、让这 3 个接口按契约返回、别改接口形状**。

---

## 1. 前端实际调用的接口（只有这三个）

| 方法 | 路径 | 谁调 | 作用 |
|---|---|---|---|
| GET | `/api/config` | `app.js` 启动时 | 拿模板 + 下拉项 + 单位 + 数据摘要 |
| GET | `/api/options` | 备用（刷新下拉项） | 同上，去掉模板 |
| **POST** | **`/analyze`** | 点"预测"按钮 | 拿预测结果 |

`POST /api/predict` 是同一段逻辑的"完整信封版"，**前端不用它**（留给其他客户端/调试用）。

---

## 2. 每个接口的精确形状（这部分我实测过）

### `GET /api/config`

```json
{
  "template": {
    "id": "energy-forecast",
    "fields": [
      { "name": "building", "label": "Building", "type": "select",
        "required": true, "default": "Teaching Block A", "placeholder": "" }
    ],
    "output": { "unit": "kWh" }
  },
  "options": { "building": ["Canteen", "Library", "Teaching Block A"] },
  "dataset": { "rows": 3655 },
  "model":    { "plugin": "group-baseline", "backtest": { "mape": 0.066, "accuracy": 0.934 } }
}
```

**前端只用这四个**：`template.fields[]`、`options[字段名]`、`template.output.unit`、`dataset.rows`。
多给字段没关系，**少给会直接崩**。

### `POST /analyze`

请求体是**扁平字段表**（就是 `Object.fromEntries(new FormData(form))` 的结果，**不是** `{fields:{...}}`）：

```json
{ "building": "Teaching Block A", "day_type": "Weekday",
  "weather": "Sunny", "term_phase": "Term", "notes": "" }
```

响应**必须**包含这 5 个 key（实测 `/analyze` 共 22 个 key = 完整信封 + 这 3 个别名）：

```json
{
  "prediction": 816.0,        // 主数字（前端的大字）
  "average": 693.0,           // "正常水平"（对比基准）
  "change_percent": 17.7,     // 相对变化，前端会加 "%"
  "confidence": 93,           // 0-100 整数；给不出时用 null（前端显示 "—"，不会崩）
  "explanation": "Teaching Block A averages 783 (13% above); ..."
}
```

### 错误格式（必须遵守）

非 2xx 时，body **必须是 JSON 且带 `detail`**：

```json
{ "detail": "缺少必填字段 'weather' (Weather)" }
```

前端逻辑是 `if (!response.ok) throw new Error(body.detail)`，然后把 `detail` 原样弹在页面右下角。
所以：**`detail` 写得越具体，现场排查越快。** 状态码用 400 / 404 / 405 / 422 / 500 / 502。

---

## 3. 你不能改的东西（改了前端当场崩）

| 不能改 | 原因 |
|---|---|
| 三个接口的**路径与 HTTP 方法** | `api.js` 里写死了 |
| `/analyze` 的请求体是**扁平字段表** | `app.js` 直接提交 `FormData` |
| 响应里那 **5 个 key 的名字** | `updateResult()` 按名字取 |
| 错误必须是 **JSON + detail** | 否则前端只能显示 "HTTP 500" |
| 静态文件的 **JS MIME** | ES Module 的 MIME 不对浏览器会拒绝执行（`server.py` 已处理好，别绕开它自己写静态服务） |

**有一条测试专门守着这件事**：

```text
tests/test_api.py::test_http_surface_is_unchanged    # 端点集合一变就红
```

这是保护你我的护栏，不是障碍。真要改接口形状，**先找我谈**，因为会连带改 `api.js`、Mock 和测试。

---

## 4. 你**不用**管的东西（前端自动适配）

| 你想做的事 | 你要改的 | 前端要不要改 |
|---|---|---|
| 加一个下拉框 / 改字段名 / 调顺序 | `template.json` 的 `fields[]` | **不用**，表单自动渲染 |
| 数据里多了一个取值（新楼栋/新品类） | 只更新 CSV | **不用**，下拉项自动出现 |
| 换预测目标、换单位 | `dataset.target` / `output.unit` | **不用**，单位自动显示 |
| 后端没启动时怎么演示 | — | **不用**，`api.js` 自动回退 Mock |
| 页面标题 / 文案 / KPI 数字 | — | 那是我的文件 `frontend/js/config.js` |

---

## 5. 你的活，按依赖顺序做

### Step 1 · 把数据放进来

```powershell
# 数据放 data/ 下，然后自证数据可用：
python -m backend.check_data --csv data/my.csv --target <数值列> ^
    --field <维度列1> --field <维度列2> --check-api
```

它会打印行数、每个字段的取值与样本量、**留一天法回测的 MAPE**，并告诉你**哪些列没被用上**。
看到 "通过" 和退出码 0 再往下走。（格式要求见 [DATA_FORMAT.md](DATA_FORMAT.md)）

### Step 2 · 生成 / 编写模板

```powershell
# 让工具直接生成一份可用的模板：
python -m backend.check_data --csv data/my.csv --target <数值列> ^
    --field <维度列1> --field <维度列2> --write-template templates/my.json
```

生成的字段 `label` 默认等于列名，**改成给人看的**（`department` → `Department`）。

### Step 3 · 跑起来

```powershell
$env:TEMPLATE_FILE = "templates/my.json"     # 不动默认模板，可随时切回演示
python -m backend.server --port 8000         # 零依赖，同时托管前端
# 或者
uvicorn backend.main:app --reload            # FastAPI 方式（需要 pip install -r requirement.txt）
```

### Step 4 ·（可选）接你们自己的模型

```powershell
$env:MODEL_BACKEND = "http"
$env:MODEL_API_URL = "http://127.0.0.1:9000/predict"
```

你的服务只需返回 `{"value": 132}`（其余可选）。契约和参考实现见 [TEMPLATE.md 第 6 节](TEMPLATE.md) 与 [examples/llm_explainer_service.py](examples/llm_explainer_service.py)。

---

## 6. 你的完成定义（DoD）—— 复制粘贴这几条

```powershell
# 1) 数据 + 字段 + 接口 + 外接模型 四条通路，退出码必须是 0
python -m backend.check_data --check-api --check-model-api

# 2) 接口清单没被破坏，68 个用例必须 OK
python -m unittest discover -s tests -v

# 3) 浏览器视角手工确认
python -m backend.server
#    http://127.0.0.1:8000/            页面能打开
#    http://127.0.0.1:8000/api/config  JSON 正常、fields 是你要的
#    POST /analyze                     返回上面那 5 个 key
```

三条全绿 = 前端可以直接联调，不需要我再补任何东西。

---

## 7. 出问题时先看哪

| 现象 | 八成原因 | 怎么查 |
|---|---|---|
| 页面右下角弹 `dataset not found` | `dataset.path` 指错 / 文件没放对数 | 报错里就有绝对路径 |
| 弹 `{字段名} 不在可选范围内` | 前端提交的值不在该列取值里（多半是数据换了、字段没换） | `check_data` 看该列取值 |
| 弹 `缺少必填字段` | 字段 `required:true` 但表单没渲染出来（多半是 `options` 为空） | `/api/config` 看 `options` |
| 下拉框是空的 | 该列全是空值，或 `column` 写错 | `check_data` 会直接说 |
| 页面白屏 / 控制台报 MIME 错误 | 静态文件的 Content-Type 不对 | 别自己写静态服务，用 `backend/server.py` |
| 预测数字看着离谱 | 缺少重要维度列 | `check_data` 会提示"哪些列没被用上" |
| 测试在你机器上红 | 缺数据（`data/*.csv`） | 先跑 `check_data` |

---

## 8. 我们两边的文件边界（避免互相踩）

| 目录 / 文件 | 归属 | 备注 |
|---|---|---|
| `frontend/**` | **前端（我）** | 你不用改；要改文案告我 |
| `template.json` · `templates/**` | **后端（你）** | 但你一改字段，我页面上的表单就变——不用告我，但换主题时同步一句 |
| `data/**` | **后端（你）** | 数据 + 生成器；`sales.db` 是自动产物 |
| `backend/**` | **后端（你）** | |
| `tests/**` | 谁改行为谁补 | 现有 68 条是回归护栏，别为了过测试而改测试 |
| `frontend/js/config.js` 的 Metrics / Impact | **产品 / Pitch（E）** | 数字必须来自 `check_data` 的回测输出 |

---

## 9. 什么时候需要我配合

| 你的需求 | 我需要做什么 |
|---|---|
| 结果区要展示**更多东西**（第二个数字、图表、置信区间上下限） | 告我字段名 + 语义，我加 UI |
| 要改页面文案 / 标题 / KPI | 告我文字，我改 `config.js` |
| 要改接口路径、请求体形状、响应 key | **先谈**，会连带改 `api.js` + Mock + 测试 |
| 要新增一个"上传自己的 CSV"之类的交互 | 先谈接口，再谈 UI |

---

## 10. 你可以完全放心的部分

- **零依赖运行**：`python -m backend.server` 不需要 `pip install` 任何东西（本机已有 pandas/numpy/scikit-learn/SQLAlchemy）
- **离线可演示**：后端挂了前端自动用 Mock，页面不会白屏
- **接口契约有测试兜底**：端点集合、5 个 key、错误格式、ES Module MIME 都有测试守着
- **不要求你懂前端**：你只要保证 3 个接口的形状不变，前端自动适配你加的任何字段
