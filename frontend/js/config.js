/*
========================================================
SDC FRONTEND CONFIGURATION
========================================================
比赛当天：优先修改这个文件。

分工（很重要）：
- 本文件负责"外壳"内容：项目名、Logo、标题、描述、Hero 文案、Metrics、Impact。
- 分析表单的字段由后端 template.json 决定：页面启动时会用
  GET /api/config 覆盖下面的 inputs，保证前后端字段永远一致。
- 后端没启动时（例如只用 Live Server 打开页面），下面的 inputs 就是离线兜底。
========================================================
*/

export const CONFIG = {
  projectName: "ENERGY CONSUMPTION FORECAST",
  logo: "E",

  category: "AI FOR SUSTAINABILITY",

  title: "Predict demand.<br>Cut energy waste.",

  description:
    "Pick a building, a day type, the weather and the term phase; the model predicts how much electricity that building will draw. Same shell, any problem statement - swap this file and template.json.",

  /*
  --------------------------------------------------------
  主题配色（唯一来源）
  --------------------------------------------------------
  改这里的颜色就能换整套视觉，不用动 css/style.css：
  app.js 启动时把下面几个值写成 :root 上的 CSS 变量
  （--primary / --primary-dark / --primary-soft）。
  style.css 里另有一份相同的兜底值，保证 JS 尚未执行时也是绿色。
  --------------------------------------------------------
  */
  palette: {
    primary: "#059669",                          // 主色：按钮 / 折线 / 结果数字 / logo
    primaryDark: "#047857",                      // 悬停加深
    primaryOnDark: "#10b981",                    // 深色主题下的主色（深底上要提亮）
    primaryDarkOnDark: "#059669",
    primarySoft: "#e6f7ef",                      // 徽章底色（浅色主题）
    primarySoftDark: "rgba(16, 185, 129, 0.16)", // 徽章底色（深色主题）
    accent: "#10b981"
  },

  /* 主题：默认跟随系统；点过右上角按钮后记录在 localStorage */
  theme: {
    storageKey: "sdc-theme",
    respectSystem: true
  },

  hero: {
    // 箭头图标由 components/hero.js 生成，文案里不再写 "→"
    primaryButton: "Try It Now",
    secondaryButton: "About Project",
    chartTitle: "Load by day type",

    /*
    折线图数据（原先的柱状图是写死在 hero.js 里的）。
    只写数值，坐标由 hero.js 按 viewBox 自动换算，
    增删数据点不必改任何布局或 CSS。
    */
    chart: {
      points: [42, 65, 52, 82, 72, 94, 78],
      dayLabels: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
      peakLabel: "PEAK",
      note: "Demo visualization — replace with real data."
    }
  },

  analysis: {
    title: "Core Analysis",
    subtitle: "Input → AI / Algorithm → Result",
    button: "Predict Consumption",
    resultUnit: "kWh"
  },

  // 离线兜底字段。后端在线时会被 template.json 的 fields 覆盖。
  inputs: [
    {
      id: "building",
      label: "Building",
      type: "select",
      options: ["Canteen", "Dormitory C", "Laboratory B", "Library", "Teaching Block A"]
    },
    {
      id: "day_type",
      label: "Day Type",
      type: "select",
      options: ["Weekday", "Weekend"]
    },
    {
      id: "weather",
      label: "Weather",
      type: "select",
      options: ["Cloudy", "Cold", "Hot", "Rain", "Sunny"]
    },
    {
      id: "term_phase",
      label: "Term Phase",
      type: "select",
      options: ["Exam Week", "Term", "Vacation"]
    },
    {
      id: "notes",
      label: "Additional Information",
      type: "text",
      optional: true, // 可选项：留空也能预测（analysis.js / app.js 会遵守这个标记）
      placeholder: "Extra context for your model..."
    }
  ],

  // 实测值：后端 60 天留一法回测，可从 GET /api/config 的 model.backtest 复核
  metrics: [
    { value: "93%", label: "Backtest Accuracy" },
    { value: "6.6%", label: "Backtest MAPE" },
    { value: "60 days", label: "Backtest Window" }
  ],

  // 同样是回测实测值：naive 基线 = "每天都按典型工作日用电量估算"
  impact: [
    { icon: "🌱", value: "45 kWh", label: "Avg. Daily Error" },
    { icon: "🌍", value: "86%", label: "Less Error vs Baseline" },
    { icon: "⚡", value: "2.26 GWh", label: "Load Analysed" },
    { icon: "📈", value: "5", label: "Buildings Modelled" }
  ]
};
