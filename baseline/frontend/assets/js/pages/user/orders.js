import { esc } from "../../components/layout.js";
import { empty, money, statusPill } from "../../components/ui.js";


function paymentMethodOptions(methods) {
  return (methods || [])
    .filter((method) => method.enabled !== false)
    .map((method) => `<option value="${esc(method.id || "")}">${esc(method.asset || "")} / ${esc(method.chain || "")}</option>`)
    .join("");
}


function paymentForOrder(order, payments) {
  return payments.find((payment) => payment.id && payment.id === order.payment_id)
    || payments.find((payment) => payment.order_id === order.id)
    || null;
}


function orderBuckets(orders, payments) {
  const buckets = { active: [], ambiguous: [], history: [] };
  orders.forEach((order) => {
    const payment = paymentForOrder(order, payments);
    const paymentStatus = payment?.status || order.payment_status || "";
    if (order.status === "pending" && paymentStatus === "ambiguous") {
      buckets.ambiguous.push(order);
    } else if (order.status === "pending" || paymentStatus === "awaiting_payment" || paymentStatus === "detected") {
      buckets.active.push(order);
    } else {
      buckets.history.push(order);
    }
  });
  return buckets;
}


function timeline(payment) {
  const status = payment?.status || "awaiting_payment";
  return `
    <div class="payment-timeline" aria-label="链上付款进度">
      <span class="${status === "awaiting_payment" ? "active" : ""}">待付款</span>
      <span class="${status === "detected" ? "active" : ""}">确认中</span>
      <span class="${status === "confirmed" ? "active" : ""}">已到账</span>
    </div>
  `;
}


function orderCard(order, payments, methods) {
  const payment = paymentForOrder(order, payments);
  const needsTxid = payment?.status === "ambiguous" || order.payment_status === "ambiguous";
  const finalOrder = ["completed", "cancelled"].includes(order.status);
  const methodOptions = paymentMethodOptions(methods);
  const paymentActions = payment
    ? `
        <div class="order-actions">
          <button class="primary" data-action="payment-refresh" data-payment="${esc(payment.id || "")}" type="button">检查到账</button>
          <button class="secondary" data-action="payment-submit-txid" data-payment="${esc(payment.id || "")}" type="button">提交 TXID</button>
        </div>
        <input name="txid" inputmode="text" placeholder="${needsTxid ? "需要补 TXID" : "有歧义时再填写 TXID"}">
      `
    : (methodOptions
      ? `
        <div class="payment-start">
          <select data-payment-method-for="${esc(order.id || "")}" aria-label="选择链上收款方式">${methodOptions}</select>
          <button class="primary" data-action="payment-start" data-order="${esc(order.id || "")}" type="button">生成付款码</button>
        </div>
      `
      : `<p class="muted">暂无可用链上收款方式，请联系管理员。</p>`);
  return `
    <article class="mobile-card order-mobile-card">
      <div class="order-card-head">
        <div>
          <strong>${esc(order.plan_name || order.plan_id || order.kind || "套餐订单")}</strong>
          <span>${esc(order.created_at || "")}</span>
        </div>
        ${statusPill(order.status)}
      </div>
      <p>${money(order.amount)} · ${esc(order.kind || "续费")}</p>
      ${payment ? timeline(payment) : `<div class="payment-timeline muted"><span>未创建付款单</span></div>`}
      ${finalOrder ? `<p class="muted">${order.status === "cancelled" ? "订单已取消" : "订单已完成"}</p>` : paymentActions}
      ${order.status === "pending" ? `<button class="secondary quiet-danger" data-action="order-cancel" data-order="${esc(order.id || "")}" type="button">取消订单</button>` : ""}
    </article>
  `;
}


function section(title, hint, orders, payments, methods, action) {
  return `
    <div class="section-row"><div><h2>${esc(title)}</h2><span>${esc(hint)}</span></div><button class="secondary" data-action="${esc(action)}" type="button">查看</button></div>
    <div class="card-list">${orders.map((order) => orderCard(order, payments, methods)).join("") || empty("暂无订单", "open-plans", "购买套餐")}</div>
  `;
}


export function renderUserOrders(data = {}) {
  const orders = data.orders || [];
  const payments = data.payments || [];
  const methods = data.payment_methods || [];
  const buckets = orderBuckets(orders, payments);
  return `
    <section class="screen stack">
      <div class="screen-head">
        <div>
          <h1>订单</h1>
          <p>自动查账；多笔匹配时再补 TXID。</p>
        </div>
        <button class="primary" data-action="open-plans" type="button">新订单</button>
      </div>
      ${section("待处理", "待付款、确认中和未完成订单", buckets.active, payments, methods, "orders-pending")}
      ${section("需要补 TXID", "链上记录有歧义时显示在这里", buckets.ambiguous, payments, methods, "orders-ambiguous")}
      ${section("历史订单", "已完成、已取消和过期订单", buckets.history, payments, methods, "orders-history")}
    </section>
  `;
}
