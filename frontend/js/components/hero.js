export function Hero(config) {
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
            </button>

            <button
              class="btn btn-secondary"
              data-action="about">
              ${config.hero.secondaryButton}
            </button>
          </div>
        </div>

        <div class="hero-card">
          <strong>${config.hero.chartTitle}</strong>

          <div class="mock-chart">
            <div class="bar" style="height:42%"></div>
            <div class="bar" style="height:65%"></div>
            <div class="bar" style="height:52%"></div>
            <div class="bar" style="height:82%"></div>
            <div class="bar" style="height:72%"></div>
            <div class="bar" style="height:94%"></div>
            <div class="bar" style="height:78%"></div>
          </div>

          <p class="chart-note">
            Demo visualization — replace with real data.
          </p>
        </div>

      </div>
    </section>
  `;
}
