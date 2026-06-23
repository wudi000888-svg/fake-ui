import { esc } from "../../components/layout.js?v=3.1.0";
import { empty, money } from "../../components/ui.js?v=3.1.0";


function paymentMethodOptions(methods) {
  return (methods || [])
    .filter((method) => method.enabled !== false)
    .map((method) => {
      const label = `${method.asset || ""} / ${method.chain || ""}`;
      return `<option value="${esc(method.id || "")}">${esc(label)}</option>`;
    })
    .join("");
}


function planCard(plan, currentPlanId, methods) {
  const current = plan.id === currentPlanId;
  const options = paymentMethodOptions(methods);
  return `
    <article class="mobile-card plan-mobile-card ${current ? "current" : ""}">
      <div>
        <strong>${esc(plan.name || plan.id)}</strong>
        <span>${esc(plan.days)} 天 · ${esc(plan.traffic_gb)} GB · ${esc((plan.node_groups || []).join(",") || "default")}</span>
      </div>
      <div class="plan-price">${money(plan.price)}</div>
      <button class="primary" data-action="checkout-open" data-plan="${esc(plan.id)}" type="button" ${plan.enabled === false ? "disabled" : ""}>
        ${current ? "续费当前套餐" : "购买套餐"}
      </button>
      <div class="checkout-panel" data-checkout-for="${esc(plan.id)}" hidden>
        <div>
          <strong>选择付款方式</strong>
          <span>订单会按当前账号自动判断新开或续费。</span>
        </div>
        ${options
          ? `
            <label>链上付款方式
              <select data-payment-method-for-plan="${esc(plan.id)}" aria-label="选择付款方式">${options}</select>
            </label>
            <div class="form-actions">
              <button class="primary" data-action="checkout-start" data-plan="${esc(plan.id)}" type="button">生成订单和二维码</button>
              <button class="secondary" data-action="checkout-close" data-plan="${esc(plan.id)}" type="button">取消</button>
            </div>
          `
          : `
            <p class="muted">管理员暂未启用收款方式，请稍后再试。</p>
            <button class="secondary" data-action="checkout-close" data-plan="${esc(plan.id)}" type="button">关闭</button>
          `}
      </div>
    </article>
  `;
}


export function renderUserPlans(data = {}) {
  const plans = (data.plans || []).filter((plan) => plan.enabled !== false);
  const profile = data.profile || {};
  const methods = data.payment_methods || [];
  return `
    <section class="screen stack">
      <div class="screen-head">
        <div>
          <h1>套餐</h1>
          <p>美元计价，链上到账后自动开通或续费。</p>
        </div>
      </div>
      <article class="mobile-card">
        <div>
          <strong>当前套餐</strong>
          <span>${esc(profile.plan_name || "未开通")}</span>
        </div>
        <button class="secondary" data-action="refresh" type="button">刷新状态</button>
      </article>
      <div class="card-grid">
        ${plans.map((plan) => planCard(plan, profile.plan_id, methods)).join("") || empty("暂无可购买套餐", "refresh", "刷新")}
      </div>
    </section>
  `;
}
