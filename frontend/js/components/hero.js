/*
========================================================
HERO
========================================================
相较上游改动：
1. 右侧卡片由「柱状图」改为「折线图」：
   - 数据来自 config.hero.chart.points，不再写死高度
   - 坐标按 viewBox 300x150 自动换算，加数据点无需改布局
   - 绘制动画 / 面积淡入 / 数据点依次出现写在 css/style.css
2. "Try It Now" 的箭头由字符 "→" 改为内联 SVG 图标，
   带轻量动效（hover 右移 + 空闲呼吸），样式同样在 CSS 里
其余 DOM 结构与上游保持一致。
========================================================
*/

export function Hero(config) {
  const chartData = (config.hero && config.hero.chart) || {};
  const points = Array.isArray(chartData.points) ? chartData.points : [];
  const labels = Array.isArray(chartData.dayLabels) ? chartData.dayLabels : [];
  const peakLabel = chartData.peakLabel || "PEAK";
  const note = chartData.note || "Demo visualization — replace with real data.";

  const coords = toCoordinates(points);
  const polylinePoints = coords.map(point => `${point.x},${point.y}`).join(" ");
  const areaPath = buildAreaPath(coords);
  const peakIndex = findPeakIndex(points);

  return `
    <section class="hero" id="dashboard">
      <div class="container hero-grid">

        <div>
          <span class="badge">${config.category}</span>

          <h1>${config.title}</h1>

          <p>${config.description}</p>

          <div class="actions">
            <button
              class="btn btn-primary"
              data-action="scroll-analysis">
              ${config.hero.primaryButton}
              ${ArrowIcon()}
            </button>

            <button
              class="btn btn-secondary"
              data-action="about">
              ${config.hero.secondaryButton}
            </button>
          </div>
        </div>

        <div class="hero-card">
          <strong class="chart-title">${config.hero.chartTitle}</strong>

          <div class="mock-chart">
            ${LineChart({ coords, polylinePoints, areaPath, peakIndex, peakLabel, labels })}
          </div>

          <p class="chart-note">
            ${note}
          </p>
        </div>

      </div>
    </section>
  `;
}


/*
--------------------------------------------------------
箭头图标：内联 SVG，stroke 用 currentColor 跟随按钮文字，
所以深色 / 浅色主题和 hover 状态都不用额外配颜色
--------------------------------------------------------
*/
function ArrowIcon() {
  return `<svg class="btn-arrow" viewBox="0 0 24 24" aria-hidden="true" focusable="false">` +
    `<path d="M4 12h13"></path><path d="M12.5 6.5 18 12l-5.5 5.5"></path>` +
    `</svg>`;
}


/*
--------------------------------------------------------
折线图：viewBox 固定 300x150，配合 CSS 的
width:100% / height:100% 和 preserveAspectRatio="none"
自适应卡片宽度（原柱状图也是一样的自适应方式）
--------------------------------------------------------
*/
function LineChart({ coords, polylinePoints, areaPath, peakIndex, peakLabel, labels }) {
  if (coords.length < 2) {
    return "";
  }

  const peak = coords[peakIndex];
  const dots = coords.map((point, index) => {
    // 峰值点画大一点，方便一眼看到
    const radius = index === peakIndex ? 4.4 : 3.6;
    return `<circle class="chart-dot" cx="${round(point.x)}" cy="${round(point.y)}" ` +
      `r="${radius}" fill="var(--primary)"></circle>`;
  }).join("");

  const peakText = peakLabel && peak
    ? `<text x="${round(peak.x)}" y="${round(Math.max(10, peak.y - 10))}" text-anchor="middle" ` +
      `font-size="9" font-weight="700" fill="var(--primary)">${escapeText(peakLabel)}</text>`
    : "";

  const description = labels.length
    ? "Load by day type 折线图（演示数据）：" + labels.join(" / ")
    : "Load by day type 折线图（演示数据）";

  return `<svg viewBox="0 0 300 150" preserveAspectRatio="none" role="img" aria-label="${escapeText(description)}">` +
    `<defs>` +
    `<linearGradient id="chart-fill" x1="0" y1="0" x2="0" y2="1">` +
    `<stop offset="0%" stop-color="var(--primary)" stop-opacity="0.30"></stop>` +
    `<stop offset="100%" stop-color="var(--primary)" stop-opacity="0"></stop>` +
    `</linearGradient>` +
    `</defs>` +
    // 横向参考线
    `<line x1="10" y1="31" x2="290" y2="31" stroke="var(--border)" stroke-width="1" stroke-dasharray="3 5" opacity="0.9"></line>` +
    `<line x1="10" y1="73" x2="290" y2="73" stroke="var(--border)" stroke-width="1" stroke-dasharray="3 5" opacity="0.9"></line>` +
    `<line x1="10" y1="115" x2="290" y2="115" stroke="var(--border)" stroke-width="1" stroke-dasharray="3 5" opacity="0.9"></line>` +
    // 面积 + 折线
    `<path class="chart-area" d="${areaPath}" fill="url(#chart-fill)"></path>` +
    `<polyline class="chart-line" stroke="var(--primary)" points="${polylinePoints}"></polyline>` +
    // 数据点
    dots +
    peakText +
    `</svg>`;
}


/* 数值 -> SVG 坐标：先按数值区间归一化到 15%~85% 的高度，再映射到 viewBox */
function toCoordinates(points) {
  const values = points.map(Number).filter(Number.isFinite);

  if (values.length === 0) {
    return [];
  }

  const max = Math.max.apply(null, values);
  const min = Math.min.apply(null, values);
  const span = (max - min) || 1;

  const innerWidth = 280; // 左右各留 10
  const top = 30;
  const bottom = 120;

  const step = values.length > 1 ? innerWidth / (values.length - 1) : 0;

  return values.map((value, index) => ({
    x: 10 + step * index,
    y: bottom - ((value - min) / span) * (bottom - top)
  }));
}

/* 面积路径：折线首尾下探到基准线后闭合 */
function buildAreaPath(coords) {
  if (coords.length < 2) {
    return "";
  }

  const line = coords
    .map((point, index) => (index === 0 ? "M " : "L ") + round(point.x) + " " + round(point.y))
    .join(" ");

  const last = coords[coords.length - 1];
  const first = coords[0];

  return line + " L " + round(last.x) + " 115 L " + round(first.x) + " 115 Z";
}

function findPeakIndex(points) {
  let peak = -1;
  let peakValue = -Infinity;

  points.forEach((value, index) => {
    const number = Number(value);
    if (Number.isFinite(number) && number > peakValue) {
      peakValue = number;
      peak = index;
    }
  });

  return peak;
}

function round(value) {
  return Math.round(value * 10) / 10;
}

/* 配置里的文案是作者自己写的，这里只做最基本的转义，避免手滑写出坏标记 */
function escapeText(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
