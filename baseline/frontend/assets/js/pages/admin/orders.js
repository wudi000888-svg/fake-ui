import { esc } from "../../components/layout.js?v=3.0.2";
import { money, statusPill } from "../../components/ui.js?v=3.0.2";


function paymentForOrder(order, payments) {
  return payments.find((payment) => payment.id && payment.id === order.payment_id)
    || payments.find((payment) => payment.order_id === order.id)
    || null;
}


function matchesOrder(order, payment, query) {
  if (!query) return true;
  const haystack = [
    order.id,
    order.username,
    order.kind,
    order.status,
    order.plan_id,
    order.plan_name,
    order.created_at,
    payment?.id,
    payment?.asset,
    payment?.chain,
    payment?.status,
    payment?.txid,
  ].join(" ").toLowerCase();
  return haystack.includes(query.toLowerCase());
}


function paymentCard(payment) {
  return `
    <div class="payment-mini">
      <span class="mono">${esc(payment.asset || "")} ${esc(payment.crypto_amount || "")} · ${esc(payment.status || "")}</span>
      <span>管理员核账</span>
      <button class="secondary" data-action="payment-refresh" data-payment="${esc(payment.id || "")}" type="button">刷新到账</button>
      <button class="secondary" data-action="payment-submit-txid" data-payment="${esc(payment.id || "")}" type="button">补录 TXID</button>
    </div>
  `;
}


function orderCard(order, payments) {
  const payment = paymentForOrder(order, payments);
  const canOperate = order.status === "pending";
  return `
    <article class="admin-card">
      <div>
        <strong>${esc(order.username || "-")}</strong>
        ${statusPill(order.status)}
      </div>
      <p>${esc(order.plan_name || order.plan_id || order.kind || "订单")} · ${money(order.amount)} · ${esc(order.created_at || "")}</p>
      ${payment ? paymentCard(payment) : `<p>暂无链上付款单</p>`}
      <div class="admin-actions">
        ${canOperate ? `<button class="secondary" data-action="order-action" data-order="${esc(order.id || "")}" data-order-action="confirm" type="button">确认</button>` : ""}
        ${canOperate ? `<button class="secondary quiet-danger" data-action="order-action" data-order="${esc(order.id || "")}" data-order-action="cancel" type="button">取消</button>` : ""}
      </div>
    </article>
  `;
}


export function renderAdminOrders(data = {}) {
  const orders = data.orders || [];
  const payments = data.payments || [];
  const query = data.filters?.orders || "";
  const plans = (data.plans || []).filter((plan) => plan.enabled !== false);
  const planOptions = plans.map((plan) => `<option value="${esc(plan.id || "")}">${esc(plan.name || plan.id || "")} / ${money(plan.price)}</option>`).join("");
  const visibleOrders = orders.filter((order) => matchesOrder(order, paymentForOrder(order, payments), query));
  const active = visibleOrders.filter((order) => order.status === "pending");
  const cancelled = visibleOrders.filter((order) => order.status === "cancelled");
  const completed = visibleOrders.filter((order) => order.status === "completed");
  const history = visibleOrders.filter((order) => !["pending", "cancelled", "completed"].includes(order.status));
  return `
    <section class="screen stack">
      <div class="screen-head">
        <div><h1>订单运营</h1><p>未付款、取消和已完成分开处理。</p></div>
        <button class="primary" data-action="order-create-sheet" type="button">创建订单</button>
      </div>
      <article class="admin-card order-create-form" hidden>
        <div><strong>创建待支付订单</strong><span>用户新开或续费由系统根据账号状态判断。</span></div>
        <form class="form-grid" data-form="order-create">
          <label>用户名<input name="username" autocomplete="off" required></label>
          <label>套餐
            <select name="plan_id" required>
              ${planOptions || `<option value="">暂无可用套餐</option>`}
            </select>
          </label>
          <label>类型
            <select name="kind">
              <option value="renew">自动/续费</option>
              <option value="create">新开</option>
            </select>
          </label>
          <label>备注<input name="note" placeholder="可选"></label>
          <button class="primary" type="submit">创建订单</button>
        </form>
      </article>
      <div class="toolbar"><input data-filter="orders" value="${esc(query)}" placeholder="搜索用户、订单、套餐或付款状态"><button data-action="orders-filter" type="button">筛选</button></div>
      <div class="section-row"><h2>待处理</h2><span>${active.length}</span></div>
      <div class="card-list">${active.map((order) => orderCard(order, payments)).join("") || `<article class="admin-card empty"><p>暂无待处理订单</p><button data-action="orders-refresh" type="button">刷新</button></article>`}</div>
      <div class="section-row"><h2>已完成</h2><span>${completed.length}</span></div>
      <div class="card-list">${completed.slice(0, 30).map((order) => orderCard(order, payments)).join("") || `<article class="admin-card empty"><p>暂无已完成订单</p></article>`}</div>
      <div class="section-row"><h2>已取消</h2><span>${cancelled.length}</span></div>
      <div class="card-list">${cancelled.slice(0, 30).map((order) => orderCard(order, payments)).join("") || `<article class="admin-card empty"><p>暂无已取消订单</p></article>`}</div>
      <div class="section-row"><h2>其他历史</h2><span>${history.length}</span></div>
      <div class="card-list">${history.slice(0, 40).map((order) => orderCard(order, payments)).join("") || `<article class="admin-card empty"><p>暂无其他历史订单</p></article>`}</div>
      <div class="bottom-sheet" hidden></div>
    </section>
  `;
}
