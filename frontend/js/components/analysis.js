export function Analysis(config) {
  return `
    <section class="section" id="analysis">
      <div class="container">

        <div class="section-head">
          <div>
            <h2>${config.analysis.title}</h2>
            <p>${config.analysis.subtitle}</p>
          </div>
        </div>

        <div class="analysis">

          <div class="card form-card">
            <form id="analysis-form">

              <div id="input-container">
                ${renderInputs(config.inputs)}
              </div>

              <button
                class="btn btn-primary analysis-button"
                type="submit">
                ${config.analysis.button}
              </button>

            </form>
          </div>

          <div class="card result-card">

            <div class="badge">AI RESULT</div>

            <div class="result-number" id="result-value">132</div>

            <div class="result-sub">
              ${config.analysis.resultUnit}
            </div>

            <div class="result-grid">

              <div class="mini">
                <span>Average</span>
                <strong id="result-average">143</strong>
              </div>

              <div class="mini">
                <span>Change</span>
                <strong id="result-change">-7.7%</strong>
              </div>

              <div class="mini">
                <span>Confidence</span>
                <strong id="result-confidence">87%</strong>
              </div>

            </div>

            <div class="insight">
              <strong>🤖 AI Insight</strong>
              <p id="result-explanation">
                This is demo output. Connect your backend API to replace it.
              </p>
            </div>

          </div>

        </div>
      </div>
    </section>
  `;
}

function renderInputs(inputs) {
  return inputs.map(input => {

    if (input.type === "select") {
      return `
        <label for="${input.id}">${input.label}</label>

        <select id="${input.id}" name="${input.id}">
          ${input.options.map(option =>
            `<option value="${option}">${option}</option>`
          ).join("")}
        </select>
      `;
    }

    return `
      <label for="${input.id}">${input.label}</label>

      <input
        id="${input.id}"
        name="${input.id}"
        type="${input.type}"
        placeholder="${input.placeholder || ""}"
      >
    `;
  }).join("");
}
