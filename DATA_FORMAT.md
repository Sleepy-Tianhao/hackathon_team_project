# 自定义数据输入 · 数据格式说明（DATA_FORMAT.md）

接你们自己的数据，只需要 **一个 CSV + template.json 里几行配置**。
**HTTP 接口一个都不改**：还是 `GET /api/config`、`POST /analyze`、`POST /api/predict`，路径、请求体、响应字段全部不变。

---

## 1. 最小可用格式

一个"长表"CSV，一行 = 一次观测：

```csv
date,drink,weekday,weather,term_phase,cups
2025-01-06,Latte,Monday,Sunny,Term,112
2025-01-06,Americano,Monday,Sunny,Term,78
2025-01-07,Latte,Tuesday,Rain,Term,96
...
```

就这么多。每一列承担一个角色：

| 角色 | 例子 | 必须？ | 说明 |
|---|---|---|---|
| **目标列** | `cups` | ✅ | 要预测的那个数值列，必须能转成数字 |
| **日期列** | `date` | 建议 | ISO 格式 `YYYY-MM-DD`。有它才能看时间范围、跑回测 |
| **维度列** | `drink` / `weekday` / `weather` / `term_phase` | ✅ 至少一个 | 每一列对应页面上的一个下拉框 |

> **核心规则：一行 = 一个维度取值的组合。**
> 不要把不同维度铺成很多列（`latte_cups, americano_cups, ...`），那样模型无法把它当成维度来学习。

---

## 2. CSV 列 ↔ template.json 的对照

| CSV | template.json |
|---|---|
| 目标列 `cups` | `"dataset": { "target": "cups" }` |
| 日期列 `date` | `"dataset": { "date_column": "date" }` |
| 维度列 `drink` | `fields[]` 里一项：`{ "name": "drink", "source": "dataset", "column": "drink" }` |
| 单位 | `"dataset": { "unit": "cups" }` |
| 文件路径 | `"dataset": { "path": "data/samples/coffee_shop_sales.csv" }` |

完整可跑的例子见 [data/samples/coffee_shop.template.json](data/samples/coffee_shop.template.json)。

---

## 3. 要求清单

**硬性（不满足会直接报错）**

- UTF-8 编码的 CSV（Excel 另存为"CSV UTF-8"，带不带 BOM 都行）
- 目标列存在，且**每一行都能转成数字**
- 每个 `source=dataset` 字段的 `column` 必须真实存在
- 每个取值至少有 `effect_min_rows` 行（默认 5），否则该因子的样本不足会被忽略
- `baseline_filter` 里引用的列和取值必须存在

**建议（决定准确率，不满足只会警告）**

| 项 | 建议 | 原因 |
|---|---|---|
| 总行数 | ≥ 300（越多越好） | 条件均值需要足够样本 |
| 每个取值 | ≥ 20 行 | 太少则因子噪声大 |
| 日期跨度 | ≥ 60 天 | 回测窗口默认最近 60 天 |
| 维度列 | **把真正影响结果的因素都做成列** | 见第 7 节，这是准确率的最大来源 |
| 目标 | 连续数值，有真实的季节/星期/条件效应 | 纯随机的目标谁都预测不了 |

---

## 4. 缺失值：一个必须知道的坑

- **空单元格** → 视为缺失，该行不参与统计（会在报告里告诉你去掉了几行）
- **字面量 `None` / `NA` / `nan`** → 会被当作**正常字符串**，不是缺失

这是刻意的：pandas 默认会把 `None` 当成缺失值，导致食堂模板里最常见的 `event=None` 从下拉框里凭空消失。

**所以"无特殊事件"不要留空，直接写一个明确取值**（`None`、`NoEvent`、`Normal` 都行）。

---

## 5. 三步接入

```powershell
# 1) 放数据（任意路径都行，相对路径基于项目根目录）
copy 你们的数据.csv data\my_data.csv

# 2) 改 template.json：dataset 指向它，fields 里加维度列
#    （懒人做法：用下面的 --write-template 自动生成一份）

# 3) 校验 + 预演 API，确认没问题再启动
python -m backend.check_data --csv data/my_data.csv --target yield ^
    --field crop --field soil --field region --check-api
```

校验通过后：

```powershell
python -m backend.server
# 前端会自动出现 crop / soil / region 三个下拉框，预测走你们的列
```

---

## 6. 校验工具

`python -m backend.check_data` 是专门为"接自己的数据"准备的，它**用和线上 API 完全相同的代码路径**读 CSV，
所以它报绿就代表服务跑起来看到的是同一份数据。

```text
python -m backend.check_data                                  # 校验当前 template.json
python -m backend.check_data --template data/samples/coffee_shop.template.json --check-api
python -m backend.check_data --csv my.csv --target yield --field crop --field soil
python -m backend.check_data --csv my.csv --target yield --field crop --write-template my.json
python -m backend.check_data --sample data/samples/coffee_shop_sales.csv
```

它会检查：文件能否读取、目标列是否全为数字、行数够不够、日期能否解析、
每个维度列的取值与样本量、`baseline_filter` 是否有效、**哪些列没被用上**，
然后跑一次留一天回测告诉你预期准确率，最后可选地预演 `/api/config` 与 `/analyze`。
**退出码 0 = 可以上线，1 = 有错误。**

真实输出（咖啡店示例）：

```text
  数据校验  id=coffee-shop  plugin=group-baseline
  [OK   ] 目标列 'cups' 全部可转成数字（1,000 行）
  [OK   ] 行数充足（1,000）
  [INFO ] 日期范围       2025-01-06 ~ 2025-07-24（200 天 / 200 个日期）
  [INFO ] 字段 drink        列=drink        取值=5    最少样本=200  最多样本=200
  [INFO ] 字段 weekday      列=weekday      取值=7    最少样本=140  最多样本=145
  [INFO ] 字段 weather      列=weather      取值=4    最少样本=115  最多样本=345
  [INFO ] 字段 term_phase   列=term_phase   取值=3    最少样本=90   最多样本=770
  [INFO ] 基准口径       a normal term week：过滤后 910 行作为 正常水平
  [INFO ] 回测           60 天 / 300 个样本
  [INFO ]   MAPE 9.13%   准确率 90.9%   平均绝对误差 4.59
  [INFO ]   参照系 21.24（always prep a typical weekday）
  [OK   ]   相对参照系误差降低 84.9%
  [OK   ] GET  /api/config   OK   id=coffee-shop  rows=1000  fields=['drink','weekday','weather','term_phase','notes']
  [OK   ] POST /analyze      OK   {"drink": "Latte", "weekday": "Monday", "weather": "Sunny", "term_phase": "Term", "notes": ""}
  [INFO ]                    -> prediction=112.0  average=56.0  change=98.9%  confidence=91%
  通过（0 个警告）—— 现有 API 无需任何改动
```

---

## 7. 准确率上不去，先看这一节

校验工具会直接点出来：**CSV 里有哪些列没有作为字段参与预测**。

这不是理论问题——上面那份咖啡数据，只把 `drink` 做成字段时：

| 用作字段的列 | 回测 MAPE | 准确率 |
|---|---|---|
| 只有 `drink` | 42.0% | — |
| `drink` + `weekday` + `weather` + `term_phase` | **9.13%** | 90.9% |

同样的数据、同样的代码，只因为把"星期几"这个真实影响需求的维度补成了字段。
**CSV 里有的信息，一定要在 `fields[]` 里暴露出来**，模型才能用它。

---

## 8. 换了数据，API 依然不变

用上面的 `--check-api` 实测（数据换成咖啡店，模板换成咖啡店）：

```text
GET  /api/config   ->  { "template": { "id": "coffee-shop", "fields": [...] },
                         "options": { "drink": ["Americano","Cocoa",...], "weekday": [...] },
                         "dataset": { "rows": 1000, ... } }
POST /analyze      ->  { "prediction": 112.0, "average": 56.0, "change_percent": 98.9,
                         "confidence": 91, "explanation": "Latte averages 108 (93% above); ..." }
```

结构与字段名和默认模板完全一致，前端的 `app.js` / `api.js` **不需要任何改动**——
这正是"字段唯一来源是 `template.json`、前端从 `/api/config` 渲染"的意义。

---

## 9. 运行期临时换数据（不改文件）

```powershell
$env:DATASET_FILE = "D:\somewhere\judge_data.csv"
python -m backend.server
```

`DATASET_FILE` 会临时替换 `template.json` 里的 `dataset.path`，
适合现场演示"同一套系统跑评委给的数据"。字段配置仍然来自 template.json，所以列名要能对上；
先跑一遍 `check_data` 就知道了。想锁死配置（禁止被环境变量覆盖）就设 `DATASET_FILE_LOCK=1`。

---

## 10. 给外接模型的数据格式（JSON）

如果你们是把自己的模型做成 HTTP 服务、由本项目去调用，那么"数据格式"是这一份：

```json
// 本项目 → 你们的模型
POST $MODEL_API_URL
{
  "template_id": "coffee-shop",
  "fields": { "drink": "Latte", "weekday": "Monday", "weather": "Sunny",
              "term_phase": "Term", "notes": "" },
  "unit": "cups",
  "context": { "target": "cups", "target_label": "杯数",
               "requested_at": "2026-03-01T08:00:00+00:00" }
}

// 你们 → 本项目（只有 value 必填）
{
  "value": 112,
  "unit": "cups",
  "baseline": 56,
  "confidence": 91,
  "explanation": "Latte on a sunny Monday in term time.",
  "model": "cafe-xgb-v3"
}
```

`fields` 的 key 就是 `template.json` 里 `fields[].name`，
所以**在 template.json 加一个字段，你们的模型就会自动多收到一个参数**。
详细契约见 [TEMPLATE.md 第 6 节](TEMPLATE.md#6-接入你自己的模型-api重点)。

---

## 11. 常见报错对照

| 报告 | 原因 | 处理 |
|---|---|---|
| `dataset.target 'x' 不在 CSV 里` | 列名拼错 / 传错文件 | 报告里会列出真实列名 |
| `目标列有 N 行不是数字` | 混了 `oops` / 空值 / 千分位逗号 | 清洗，或用 `1,234` → `1234` |
| `只有 N 行` | 数据太少 | 至少 300 行，或降低 `effect_min_rows` |
| `日期列有 N 行无法解析` | `01/05/2025` 之类的格式 | 统一成 `YYYY-MM-DD` |
| `不是 UTF-8 编码` | GBK 的 CSV | Excel 另存为 "CSV UTF-8" |
| `字段 'x' 指向的列 'y' 不存在` | template.json 的 `column` 拼错 | 改 `column` |
| `N 个取值样本 < 5，这些因子会被忽略` | 某个取值出现次数太少 | 合并取值，或降低 `effect_min_rows` |
| `这些列没有作为字段参与预测` | 有维度没暴露 | 在 `fields[]` 里加一项（第 7 节） |
| `MAPE 偏高` | 还有重要维度没做成字段 / 目标噪声大 | 先补齐维度列 |
| `相对参照系只提升 x%` | 维度对结果几乎没有区分度 | 换维度，或确认这个题值不值得预测 |

---

## 12. 附：完整可跑示例

```powershell
# 生成示例数据（1000 行：date, drink, weekday, weather, term_phase, cups）
python -m backend.check_data --sample data/samples/coffee_shop_sales.csv

# 用配套模板校验并预演 API
python -m backend.check_data --template data/samples/coffee_shop.template.json --check-api

# 真的跑起来看
$env:TEMPLATE_FILE = "data/samples/coffee_shop.template.json"
python -m backend.server --port 8000
```

| 文件 | 作用 |
|---|---|
| [data/samples/coffee_shop_sales.csv](data/samples/coffee_shop_sales.csv) | 示例数据（自定义数据的标准形状） |
| [data/samples/coffee_shop.template.json](data/samples/coffee_shop.template.json) | 与它配套的模板，可直接当模版抄 |
| [backend/check_data.py](backend/check_data.py) | 校验 / 生成示例 / 预演 API 的工具 |
| [template.json](template.json) | 默认模板（食堂需求），字段与输出的写法参考 |
