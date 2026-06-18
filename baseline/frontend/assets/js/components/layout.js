import { state } from "../state.js";
import { navigate } from "../router.js";

const SIDEBAR_COLLAPSED_KEY = "fake-ui-side-nav-collapsed";


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
      <span class="nav-dot" aria-hidden="true">${esc(item.icon || "")}</span>
      <span class="nav-label">${esc(item.label)}</span>
    </button>
  `;
}


function notice() {
  if (!state.notice) return "";
  return `<div class="notice ${esc(state.notice.type)}">${esc(state.notice.message)}</div>`;
}


function accountMenu(username, role) {
  return `
    <div class="account-menu-popover">
      <div class="account-menu-head">
        <strong>${esc(username || role)}</strong>
        <span>${esc(role)}</span>
      </div>
      <button data-nav="account" type="button">个人资料</button>
      <button data-nav="links" type="button">订阅管理</button>
      <button data-action="logout" class="danger-link" type="button">退出登录</button>
    </div>
  `;
}


function isSidebarCollapsed() {
  try {
    return window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "1";
  } catch {
    return false;
  }
}


function setSidebarCollapsed(root, collapsed) {
  root.classList.toggle("side-nav-collapsed", collapsed);
  const button = root.querySelector(".side-nav-collapse");
  if (button) {
    setSidebarButtonState(button, collapsed);
  }
  try {
    window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, collapsed ? "1" : "0");
  } catch {
    // Local storage can be disabled; the visual state still updates for this page.
  }
}


function setSidebarButtonState(button, collapsed) {
  button.setAttribute("aria-expanded", collapsed ? "false" : "true");
  button.setAttribute("aria-label", collapsed ? "展开导航" : "收起导航");
  button.querySelector(".collapse-icon").textContent = collapsed ? "»" : "«";
  button.querySelector(".collapse-label").textContent = collapsed ? "展开" : "收起";
}


function syncSidebarButtonForViewport(root) {
  const shell = root.querySelector(".app-shell-v2") || root;
  const button = shell.querySelector(".side-nav-collapse");
  if (!button) return;
  setSidebarButtonState(button, !isMobileNavMode() && shell.classList.contains("side-nav-collapsed"));
}


function toggleSidebarCollapsed(root) {
  setSidebarCollapsed(root, !root.classList.contains("side-nav-collapsed"));
}


function isMobileNavMode() {
  return window.matchMedia("(max-width: 1023px)").matches;
}


export function layout(content) {
  const primaryItems = state.shell?.nav || [];
  const secondaryItems = state.shell?.secondary_nav || [];
  const nav = primaryItems.map(navButton).join("");
  const secondary = secondaryItems.map(navButton).join("");
  const username = state.shell?.username || state.session?.username || "";
  const role = state.shell?.role === "admin" ? "管理员" : "用户";
  const version = state.shell?.version || "2.3.1";
  const sidebarCollapsed = isSidebarCollapsed();
  return `
    <div class="app-shell-v2 ${sidebarCollapsed ? "side-nav-collapsed" : ""}">
      <button class="mobile-nav-backdrop" data-action="close-mobile-nav" type="button" aria-label="关闭导航"></button>
      <aside class="side-nav" aria-label="主导航">
        <div class="brand-block">
          <div class="brand-title">
            <span class="sidebar-logo">F</span>
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
          <button class="side-nav-collapse" data-action="toggle-side-nav" type="button" aria-expanded="${sidebarCollapsed ? "false" : "true"}" aria-label="${sidebarCollapsed ? "展开导航" : "收起导航"}">
            <span class="collapse-icon" aria-hidden="true">${sidebarCollapsed ? "»" : "«"}</span>
            <span class="collapse-label">${sidebarCollapsed ? "展开" : "收起"}</span>
          </button>
        </div>
      </aside>
      <div class="workspace-v2">
        <header class="topbar">
          <button class="icon-button mobile-menu-button" data-action="toggle-mobile-nav" type="button" aria-label="打开导航">☰</button>
          <div class="topbar-title">
            <strong>${state.shell?.role === "admin" ? "管理控制台" : "用户中心"}</strong>
            <span>系统概览与统计数据</span>
          </div>
          <div class="topbar-actions">
            <span class="version-chip">v${esc(version)}</span>
            <div class="account-menu-wrap">
              <button class="identity-chip" data-action="toggle-account-menu" type="button">
                <b>${esc((username || role).slice(0, 2).toUpperCase())}</b><span>${esc(username || role)}</span>
              </button>
              ${accountMenu(username, role)}
            </div>
          </div>
          <button class="secondary" data-action="logout" type="button">退出</button>
        </header>
        <main class="main-v2">${notice()}${content}</main>
      </div>
    </div>
  `;
}


export function bindLayoutEvents(root) {
  root.addEventListener("click", (event) => {
    const action = event.target.closest("[data-action]")?.dataset.action || "";
    if (action === "toggle-mobile-nav") {
      root.classList.remove("account-menu-open");
      syncSidebarButtonForViewport(root);
      root.classList.toggle("mobile-nav-open");
      return;
    }
    if (action === "toggle-side-nav") {
      if (isMobileNavMode()) {
        root.classList.remove("account-menu-open");
        root.classList.remove("mobile-nav-open");
        syncSidebarButtonForViewport(root);
        return;
      }
      const shell = root.querySelector(".app-shell-v2") || root;
      root.classList.remove("account-menu-open");
      toggleSidebarCollapsed(shell);
      return;
    }
    if (action === "close-mobile-nav") {
      root.classList.remove("mobile-nav-open");
      return;
    }
    if (action === "toggle-account-menu") {
      root.classList.remove("mobile-nav-open");
      root.classList.toggle("account-menu-open");
      return;
    }
    if (!event.target.closest(".account-menu-wrap")) {
      root.classList.remove("account-menu-open");
    }
    const button = event.target.closest("[data-nav]");
    if (!button) return;
    root.classList.remove("mobile-nav-open");
    root.classList.remove("account-menu-open");
    navigate(button.dataset.nav);
  });
}
