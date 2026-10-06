export function Impact(config) {
  return `
    <section class="section" id="impact">
      <div class="container">

        <div class="section-head">
          <div>
            <h2>Impact</h2>
            <p>Show the measurable value created by your solution.</p>
          </div>
        </div>

        <div class="impact">
          ${config.impact.map(item => `
            <div class="card impact-card">
              <div class="icon">${item.icon}</div>
              <div class="metric-value">${item.value}</div>
              <div class="metric-label">${item.label}</div>
            </div>
          `).join("")}
        </div>

      </div>
    </section>
  `;
}
