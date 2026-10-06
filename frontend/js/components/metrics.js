export function Metrics(config) {
  return `
    <section class="section">
      <div class="container">

        <div class="section-head">
          <div>
            <h2>Key Metrics</h2>
            <p>Show the most important numbers of your solution.</p>
          </div>
        </div>

        <div class="metrics">
          ${config.metrics.map(metric => `
            <div class="card">
              <div class="metric-value">${metric.value}</div>
              <div class="metric-label">${metric.label}</div>
            </div>
          `).join("")}
        </div>

      </div>
    </section>
  `;
}
