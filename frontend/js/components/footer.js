export function Footer(config) {
  return `
    <footer class="footer">
      <div class="container">
        <strong>${config.projectName}</strong>
        <span> · Built for SDC Hackathon</span>
      </div>
    </footer>
  `;
}
