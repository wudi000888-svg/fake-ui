import { esc } from "./layout.js?v=3.0.1";


export function gb(bytes) {
  const value = Number(bytes || 0) / 1024 / 1024 / 1024;
  return `${value.toFixed(value >= 10 ? 0 : 1)} GB`;
}


export function statusPill(status) {
  const label = {
    completed: "已完成",
    pending: "待处理",
    awaiting_payment: "待付款",
    cancelled: "已取消",
    detected: "已到账",
    confirmed: "已到账",
    ambiguous: "需补 TXID",
    failed: "校验失败",
    expired: "已过期",
  }[status] || status || "未知";
  return `<span class="pill status-${esc(status || "unknown")}">${esc(label)}</span>`;
}


export function stat(label, value, tone = "") {
  return `
    <div class="stat-tile ${esc(tone)}">
      <span>${esc(label)}</span>
      <strong>${esc(value)}</strong>
    </div>
  `;
}


export function empty(message, action = "", label = "") {
  return `
    <article class="mobile-card empty">
      <p>${esc(message)}</p>
      ${action ? `<button class="secondary" data-action="${esc(action)}" type="button">${esc(label || "操作")}</button>` : ""}
    </article>
  `;
}


export function renderAppError(message) {
  return `
    <section class="screen app-error-screen">
      <article class="admin-card">
        <div>
          <strong>数据加载失败</strong>
          <span>${esc(message || "面板数据暂时不可用")}</span>
        </div>
        <div class="toolbar-actions">
          <button class="primary" data-action="retry-boot" type="button">重试</button>
          <button class="secondary" data-action="logout" type="button">退出</button>
        </div>
      </article>
    </section>
  `;
}


export function money(value) {
  const number = Number(value || 0);
  return Number.isFinite(number) ? `$${number.toFixed(number % 1 ? 2 : 0)}` : `$${esc(value)}`;
}
