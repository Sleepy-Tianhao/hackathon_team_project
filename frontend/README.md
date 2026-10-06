# SDC Frontend Template — Scheme A

技术栈：

- HTML5
- CSS3
- Vanilla JavaScript (ES Modules)
- Fetch API（预留）
- 不使用 React / Vue / Tailwind

## 目录

```text
sdc_frontend_v1/
│
├── index.html
│
├── css/
│   └── style.css
│
└── js/
    ├── app.js
    ├── config.js
    │
    ├── components/
    │   ├── header.js
    │   ├── hero.js
    │   ├── metrics.js
    │   ├── analysis.js
    │   ├── impact.js
    │   └── footer.js
    │
    └── services/
        └── api.js
```

## 文件职责

### index.html

只负责：

- HTML 基础结构
- 引入 CSS
- 引入 app.js

不要把大量网页内容写这里。

### style.css

只负责：

- 页面布局
- 颜色
- 字体
- 卡片
- 响应式设计

### config.js

这是比赛当天最常修改的文件。

修改：

- projectName
- logo
- category
- title
- description
- inputs
- metrics
- impact

### components/

每个文件负责一个 UI 区域：

- header.js → 导航栏
- hero.js → 首页 Hero
- metrics.js → 数据卡片
- analysis.js → 核心分析
- impact.js → Impact
- footer.js → 页脚

### services/api.js

负责 Frontend 与 Backend 的通信。

目前使用 Mock API。

比赛正式开发后改成：

```text
Frontend
   ↓
api.js
   ↓
FastAPI
   ↓
AI / ML / Database
```

## 如何运行

**方式一（推荐）：由后端托管**

```powershell
python -m backend.server --port 8000
# 打开 http://127.0.0.1:8000/
```

后端会按正确的 ES Module MIME 提供 `js/`、`css/`，并且表单字段来自
`template.json`，预测走真实模型。

**方式二：前端独立开发**

1. 安装 VS Code + Live Server 扩展
2. 右键 `index.html` → `Open with Live Server`
3. 同时用方式一启动后端（在 8000 端口）

`js/services/api.js` 会先试同源、再试 `http://127.0.0.1:8000`，
都连不上就自动回退 `analyzeMock()`，所以**没有后端时页面也能完整演示**。

不要直接双击 index.html，某些浏览器会限制 ES Module 的本地加载。

## 比赛当天

第一步：

修改：

```text
js/config.js
```

第二步：

根据 Problem Statement 修改：

```text
js/components/analysis.js
```

第三步：

连接：

```text
js/services/api.js
```

到 FastAPI。

## 推荐 API

POST:

```text
/analyze
```

Request:

```json
{
  "category": "Option A",
  "time": "Morning",
  "extra": "..."
}
```

Response:

```json
{
  "prediction": 132,
  "average": 143,
  "change_percent": -7.7,
  "confidence": 87,
  "explanation": "..."
}
```

> **这个契约已经实现，并且有测试覆盖。** 后端 `POST /analyze` 就是按这个形状返回的，
> `js/services/api.js` 里的 `analyze()` 已经接上它（连不上后端时自动回退 `analyzeMock()`）。

字段名由后端 `template.json` 的 `fields[]` 决定：页面启动时会用 `GET /api/config`
覆盖本目录 `config.js` 里的 `inputs`，所以**下拉框和后端校验永远不会对不上**——
加字段只需要改 `template.json`，这个目录一行都不用动。

分工小结：

| 文件 | 负责什么 |
|---|---|
| `js/config.js` | 外壳文案：项目名、标题、描述、Hero、Metrics、Impact |
| `template.json`（后端） | 分析字段、下拉项、输出单位、用哪个模型 |
| `js/components/*.js` | 每个区域的版式 |
| `js/services/api.js` | 与后端通信（已经写好，一般不用改） |

## 五人团队分工

A:
- Backend / API
- Architecture

B:
- AI / Data

C:
- Frontend
- components
- CSS

D:
- Integration
- Testing
- Deployment

E:
- Product
- UX
- Pitch
- Demo data

## 开发原则

不要先做复杂功能。

优先保证：

```text
Problem
  ↓
Input
  ↓
AI / Algorithm
  ↓
Result
  ↓
Impact
```
