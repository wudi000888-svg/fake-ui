import { state } from "../state.js";
import { navigate } from "../router.js";


export function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}


function navButton(item) {
  const active = state.route === item.id ? " active" : "";
  return `
    <button class="nav-item${active}" data-nav="${esc(item.id)}" type="button">
      <span class="nav-dot" aria-hidden="true"></span>
      <span>${esc(item.label)}</span>
    </button>
  `;
}


function notice() {
  if (!state.notice) return "";
  return `<div class="notice ${esc(state.notice.type)}">${esc(state.notice.message)}</div>`;
}


export function layout(content) {
  const primaryItems = state.shell?.nav || [];
  const secondaryItems = state.shell?.secondary_nav || [];
  const mobileItems = [...primaryItems, ...secondaryItems];
  const nav = primaryItems.map(navButton).join("");
  const secondary = secondaryItems.map(navButton).join("");
  const username = state.shell?.username || state.session?.username || "";
  const role = state.shell?.role === "admin" ? "管理员" : "用户";
  const version = state.shell?.version || "2.0.1";
  return `
    <div class="app-shell-v2">
      <aside class="side-nav" aria-label="主导航">
        <div class="brand-block">
          <div class="brand-title">
            <strong>fake-ui</strong>
            <span class="version-chip">v${esc(version)}</span>
          </div>
          <span>单机多出口代理编排系统</span>
        </div>
        <div class="side-nav-scroll">
          <div class="nav-stack">${nav}</div>
          ${secondary ? `<div class="nav-stack nav-stack-secondary">${secondary}</div>` : ""}
        </div>
        <div class="side-nav-footer">
          <div class="side-nav-meta">
            <span>${esc(username || role)}</span>
            <span>v${esc(version)}</span>
          </div>
        </div>
      </aside>
      <div class="workspace-v2">
        <header class="topbar">
          <div>
            <strong>fake-ui <span class="version-chip">v${esc(version)}</span></strong>
            <span>单机多出口代理编排系统</span>
          </div>
          <div class="identity-chip">${esc(username || role)}</div>
        </header>
        <main class="main-v2">${notice()}${content}</main>
      </div>
      <nav class="bottom-nav" aria-label="移动端导航">${mobileItems.map(navButton).join("")}</nav>
    </div>
  `;
}


export function bindLayoutEvents(root) {
  root.addEventListener("click", (event) => {
    const button = event.target.closest("[data-nav]");
    if (!button) return;
    navigate(button.dataset.nav);
  });
}
