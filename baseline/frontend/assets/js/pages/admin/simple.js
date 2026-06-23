import { esc } from "../../components/layout.js?v=3.0.2";
import { stat } from "../../components/ui.js?v=3.0.2";


export function renderAdminDashboard(data = {}) {
  const users = data.users || [];
  const orders = data.orders || [];
  const nodes = data.nodes || [];
  const payments = data.payments || [];
  return `
    <section class="screen">
      <div class="screen-head">
        <div>
          <h1>概览</h1>
          <p>运营数据与节点状态</p>
        </div>
        <button class="secondary" data-action="refresh" type="button">刷新</button>
      </div>
      <div class="stat-grid">
        ${stat("用户", users.length)}
        ${stat("订单", orders.length)}
        ${stat("节点", nodes.length)}
        ${stat("链上付款", payments.length)}
      </div>
    </section>
  `;
}


export function renderAdminSimplePage(title, items = []) {
  return `
    <section class="screen">
      <div class="screen-head"><h1>${esc(title)}</h1><span>${items.length} 条</span></div>
      <div class="card-list">
        ${items.slice(0, 40).map((item) => `
          <article class="list-card">
            <strong>${esc(item.display_name || item.name || item.username || item.id || item.action || "-")}</strong>
            <span>${esc(item.status || item.kind || item.created_at || "")}</span>
          </article>
        `).join("") || `<div class="empty">暂无记录</div>`}
      </div>
    </section>
  `;
}
