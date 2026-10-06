export function Header(config) {
  return `
    <nav class="nav">
      <div class="container nav-inner">
        <a class="brand" href="#dashboard">
          <div class="logo">${config.logo}</div>
          <span>${config.projectName}</span>
        </a>

        <div class="nav-links">
          <a href="#dashboard">Dashboard</a>
          <a href="#analysis">Analysis</a>
          <a href="#impact">Impact</a>
        </div>
      </div>
    </nav>
  `;
}
