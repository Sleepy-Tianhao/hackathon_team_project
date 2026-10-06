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
  projectName: "CAMPUS FOOD FORECAST",
  logo: "C",

  category: "AI FOR SUSTAINABILITY",

  title: "Predict demand.<br>Cut food waste.",

  description:
    "Pick a menu, a day and the weather; the model predicts how many portions the canteen should prepare. Same shell, any problem statement - swap this file and template.json.",

  hero: {
    primaryButton: "Try It Now →",
    secondaryButton: "About Project",
    chartTitle: "Demand by weekday"
  },

  analysis: {
    title: "Core Analysis",
    subtitle: "Input → AI / Algorithm → Result",
    button: "Predict Demand",
    resultUnit: "portions"
  },

  // 离线兜底字段。后端在线时会被 template.json 的 fields 覆盖。
  inputs: [
    {
      id: "menu",
      label: "Menu",
      type: "select",
      options: ["Chicken Rice", "Curry Rice", "Fried Rice", "Noodle Soup", "Vegetarian Bowl"]
    },
    {
      id: "day",
      label: "Day",
      type: "select",
      options: ["Friday", "Monday", "Saturday", "Sunday", "Thursday", "Tuesday", "Wednesday"]
    },
    {
      id: "weather",
      label: "Weather",
      type: "select",
      options: ["Cloudy", "Hot", "Rain", "Sunny"]
    },
    {
      id: "notes",
      label: "Additional Information",
      type: "text",
      placeholder: "Enter extra context..."
    }
  ],

  // 实测值：后端 60 天留一法回测，可从 GET /api/config 的 model.backtest 复核
  metrics: [
    { value: "93%", label: "Backtest Accuracy" },
    { value: "7.5%", label: "Backtest MAPE" },
    { value: "60 days", label: "Backtest Window" }
  ],

  // 同样是回测实测值：naive 基线 = "每天都按典型工作日备餐"
  impact: [
    { icon: "🌱", value: "5.6", label: "Portions Avg. Prep Error" },
    { icon: "🌍", value: "83%", label: "Less Over/Under Prep" },
    { icon: "⚡", value: "3,655", label: "Meals Analysed" },
    { icon: "📈", value: "160", label: "Conditions Tested" }
  ]
};
