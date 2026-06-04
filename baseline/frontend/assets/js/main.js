import { api, post } from "./api.js";
import { state, setNotice } from "./state.js";
import { bindPopstate } from "./router.js";
import { esc, layout, bindLayoutEvents } from "./components/layout.js";
import { statusPill, stat } from "./components/ui.js";
import { renderAdminNodes } from "./pages/admin/nodes.js";
import { renderAdminOrders } from "./pages/admin/orders.js";
import { renderAdminOverview } from "./pages/admin/overview.js";
import { renderAdminSettings } from "./pages/admin/settings.js";
import { renderAdminUsers } from "./pages/admin/users.js";
import { renderUserAccount } from "./pages/user/account.js";
import { renderUserDashboard } from "./pages/user/dashboard.js";
import { renderUserLinks } from "./pages/user/links.js";
import { renderUserOrders } from "./pages/user/orders.js";
import { renderUserPlans } from "./pages/user/plans.js";


const app = document.querySelector("#app");


function formData(form) {
  return Object.fromEntries(new FormData(form).entries());
}


function cssEscape(value) {
  if (window.CSS?.escape) return window.CSS.escape(String(value || ""));
  return String(value || "").replace(/["\\]/g, "\\$&");
}


function firstEnabledPaymentMethod() {
  return (state.data.payment_methods || []).find((method) => method.enabled !== false);
}


async function copyText(text) {
  const value = String(text || "");
  if (!value) throw new Error("没有可复制的内容");
  if (navigator.clipboard?.writeText && window.isSecureContext) {
    await navigator.clipboard.writeText(value);
    return;
  }
  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();
  document.execCommand("copy");
  textarea.remove();
}


async function runAction(work, success = "操作已完成") {
  try {
    state.busy = true;
    const message = await work();
    await refresh();
    setNotice(message || success, "success");
  } catch (error) {
    setNotice(error.message, "error");
  } finally {
    state.busy = false;
    await render();
  }
}


function showInlineForm(selector) {
  const el = app.querySelector(selector);
  if (!el) return false;
  el.hidden = !el.hidden;
  if (!el.hidden) el.querySelector("input, select, button")?.focus();
  return true;
}


function loginView() {
  return `
    <section class="login-screen">
      <form class="login-card" data-form="login">
        <div>
          <h1>fake-ui</h1>
          <p>单机多出口代理编排系统</p>
        </div>
        <label>账号<input name="username" autocomplete="username" required></label>
        <label>密码<input name="password" type="password" autocomplete="current-password" required></label>
        <button class="primary" type="submit">登录</button>
      </form>
    </section>
  `;
}


function adminDashboardPage() {
  const users = state.data.users || [];
  const orders = state.data.orders || [];
  const nodes = state.data.nodes || [];
  const payments = state.data.payments || [];
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


function adminSimplePage(title, itemsKey) {
  const items = state.data[itemsKey] || [];
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


function page() {
  if (state.shell?.role !== "admin") {
    if (state.route === "plans") return renderUserPlans(state.data);
    if (state.route === "links") return renderUserLinks(state.data);
    if (state.route === "orders") return renderUserOrders(state.data);
    if (state.route === "account") return renderUserAccount(state.data, state.shell);
    return renderUserDashboard(state.data);
  }
  if (state.route === "orders") return renderAdminOrders(state.data);
  if (state.route === "account" || state.route === "settings") return renderAdminSettings(state.data);
  if (state.route === "users") return renderAdminUsers(state.data);
  if (state.route === "nodes") return renderAdminNodes(state.data);
  if (state.route === "plans") return adminSimplePage("套餐", "plans");
  if (state.route === "links") return adminSimplePage("订阅", "links");
  if (state.route === "requests") return adminSimplePage("申请", "registrations");
  if (state.route === "audit") return adminSimplePage("审计", "audit");
  if (state.route === "backups") return adminSimplePage("备份", "backups");
  if (state.route === "hy2") return adminDashboardPage();
  return renderAdminOverview(state.data);
}


export async function refresh() {
  const result = await api("/api/dashboard");
  state.session = result.data.session;
  state.data = result.data || {};
}


export async function render() {
  if (!state.session) {
    app.innerHTML = loginView();
    return;
  }
  app.innerHTML = layout(page());
}


async function boot() {
  try {
    const sessionResult = await api("/api/session");
    state.session = sessionResult.session;
    if (state.session) {
      state.shell = await api("/api/app-shell");
      await refresh();
    }
  } catch (error) {
    setNotice(error.message, "error");
  }
  bindPopstate();
  bindLayoutEvents(app);
  window.addEventListener("fake-ui:navigate", render);
  await render();
}


app.addEventListener("submit", async (event) => {
  const form = event.target.closest("[data-form]");
  if (!form) return;
  event.preventDefault();
  const data = formData(form);
  try {
    if (form.dataset.form === "login") {
      const result = await post("/api/login", data);
      state.session = result.session;
      state.shell = await api("/api/app-shell");
      await refresh();
      setNotice("登录成功", "success");
    }
    if (form.dataset.form === "order-create") {
      await runAction(async () => {
        const out = await post("/api/orders/create", data);
        state.route = "orders";
        history.pushState(null, "", "/orders");
        return `订单已创建：${out.order.id}`;
      });
      return;
    }
    if (form.dataset.form === "payment-method-save") {
      await runAction(async () => {
        const [asset, chain] = String(data.payment_type || "").split(":");
        await post("/api/payment-methods/save", {
          asset,
          chain,
          address: data.address || "",
          enabled: data.enabled !== "false",
        });
        form.reset();
        return "收款方式已保存";
      });
      return;
    }
  } catch (error) {
    setNotice(error.message, "error");
  }
  await render();
});


app.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-action]");
  if (!button) return;
  if (state.busy && button.dataset.action !== "logout") return;
  try {
    if (button.dataset.action === "refresh") {
      await refresh();
      setNotice("已刷新", "success");
    }
    if (button.dataset.action === "open-plans") {
      state.route = "plans";
      history.pushState(null, "", "/plans");
    }
    if (button.dataset.action === "open-links") {
      state.route = "links";
      history.pushState(null, "", "/links");
    }
    if (button.dataset.action === "open-nodes") {
      state.route = "nodes";
      history.pushState(null, "", "/nodes");
    }
    if (button.dataset.action === "orders-refresh" || button.dataset.action === "users-filter" || button.dataset.action === "orders-filter" || button.dataset.action === "nodes-filter") {
      await refresh();
      setNotice("已刷新", "success");
    }
    if (button.dataset.action === "order-create-sheet") {
      showInlineForm(".order-create-form");
      return;
    }
    if (button.dataset.action === "payment-method-sheet") {
      showInlineForm(".payment-method-form");
      return;
    }
    if (button.dataset.action === "copy-subscription" || button.dataset.action === "copy-node" || button.dataset.action === "copy") {
      await copyText(button.dataset.text || "");
      setNotice("已复制", "success");
    }
    if (button.dataset.action === "buy-plan") {
      const planId = button.dataset.plan || "";
      await runAction(async () => {
        const out = await post("/api/orders/create", { plan_id: planId, kind: "renew", note: "self-service checkout" });
        const method = firstEnabledPaymentMethod();
        if (method) {
          await post("/api/payments/create", { order_id: out.order.id, method_id: method.id });
          state.route = "orders";
          history.pushState(null, "", "/orders");
          return "订单和付款码已生成";
        }
        state.route = "orders";
        history.pushState(null, "", "/orders");
        return "订单已生成，请等待管理员配置收款方式";
      });
      return;
    }
    if (button.dataset.action === "payment-start") {
      const orderId = button.dataset.order || "";
      const selector = app.querySelector(`select[data-payment-method-for="${cssEscape(orderId)}"]`);
      await runAction(async () => {
        const out = await post("/api/payments/create", { order_id: orderId, method_id: selector?.value || "" });
        return `付款码已生成：${out.payment.asset} ${out.payment.crypto_amount}`;
      });
      return;
    }
    if (button.dataset.action === "payment-refresh") {
      await runAction(async () => {
        const out = await post("/api/payments/refresh", { id: button.dataset.payment || "" });
        return `付款状态：${out.payment.status}`;
      });
      return;
    }
    if (button.dataset.action === "payment-submit-txid") {
      const card = button.closest("article");
      const txid = card?.querySelector('input[name="txid"]')?.value || "";
      await runAction(async () => {
        const path = txid.trim() ? "/api/payments/submit-tx" : "/api/payments/refresh";
        const out = await post(path, { id: button.dataset.payment || "", txid });
        return `付款状态：${out.payment.status}`;
      });
      return;
    }
    if (button.dataset.action === "order-cancel") {
      if (!confirm(`确认取消订单 ${button.dataset.order || ""}？`)) return;
      await runAction(async () => {
        await post("/api/orders/action", { id: button.dataset.order || "", action: "cancel" });
        return "订单已取消";
      });
      return;
    }
    if (button.dataset.action === "order-action") {
      const action = button.dataset.orderAction || "";
      if (action === "cancel" && !confirm(`确认取消订单 ${button.dataset.order || ""}？`)) return;
      await runAction(async () => {
        await post("/api/orders/action", { id: button.dataset.order || "", action });
        return action === "confirm" ? "订单已确认" : "订单已取消";
      });
      return;
    }
    if (button.dataset.action === "payment-method-edit") {
      const method = (state.data.payment_methods || []).find((item) => item.id === button.dataset.method);
      const form = app.querySelector('form[data-form="payment-method-save"]');
      if (method && form) {
        app.querySelector(".payment-method-form").hidden = false;
        form.elements.payment_type.value = `${String(method.asset || "").toUpperCase()}:${String(method.chain || "").toLowerCase()}`;
        form.elements.address.value = method.address || "";
        form.elements.enabled.value = method.enabled === false ? "false" : "true";
        form.elements.address.focus();
      }
      return;
    }
    if (button.dataset.action === "payment-method-action") {
      const action = button.dataset.methodAction || "";
      if (action === "delete" && !confirm(`确认删除收款方式 ${button.dataset.method || ""}？`)) return;
      await runAction(async () => {
        await post("/api/payment-methods/action", { id: button.dataset.method || "", action });
        return "收款方式已更新";
      });
      return;
    }
    if (button.dataset.action === "cache-clear") {
      await runAction(async () => {
        await post("/api/cache/clear", {});
        return "缓存已清理";
      });
      return;
    }
    if (button.dataset.action === "node-quality-check") {
      await runAction(async () => {
        await post("/api/nodes/action", { id: button.dataset.node || "", action: "refresh" });
        return "出口质量已刷新";
      });
      return;
    }
    if (button.dataset.action === "node-add") {
      await runAction(async () => {
        await post("/api/nodes/add-vless", {});
        return "节点已新增";
      });
      return;
    }
    if (button.dataset.action === "logout") {
      await post("/api/logout", {});
      state.session = null;
      state.shell = null;
      state.data = {};
      setNotice("已退出", "success");
    }
  } catch (error) {
    setNotice(error.message, "error");
  }
  await render();
});


boot();
