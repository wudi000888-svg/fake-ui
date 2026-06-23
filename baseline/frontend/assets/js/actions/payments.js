import { post } from "../api.js?v=3.1.0";
import { cssEscape, copyText, showInlineForm } from "../dom.js?v=3.1.0";
import { state, setNotice } from "../state.js?v=3.1.0";
import { closeCheckout, openCheckout } from "./forms.js?v=3.1.0";


function firstEnabledPaymentMethod() {
  return (state.data.payment_methods || []).find((method) => method.enabled !== false);
}


export async function handlePaymentAction(button, app, { runAction }) {
  const actionName = button.dataset.action;
  if (actionName === "payment-method-sheet") {
    showInlineForm(app, ".payment-method-form");
    return true;
  }
  if (actionName === "copy-subscription" || actionName === "copy-node" || actionName === "copy") {
    await copyText(button.dataset.text || "");
    setNotice("已复制", "success");
    return true;
  }
  if (actionName === "checkout-open") {
    openCheckout(app, button.dataset.plan || "");
    return true;
  }
  if (actionName === "checkout-close") {
    closeCheckout(app, button.dataset.plan || "");
    return true;
  }
  if (actionName === "checkout-start") {
    const planId = button.dataset.plan || "";
    const selector = app.querySelector(`select[data-payment-method-for-plan="${cssEscape(planId)}"]`);
    const methodId = selector?.value || "";
    await runAction(async () => {
      if (!methodId) throw new Error("请选择付款方式");
      const out = await post("/api/orders/create", { plan_id: planId, note: "self-service checkout" });
      const paymentOut = await post("/api/payments/create", { order_id: out.order.id, method_id: methodId });
      state.route = "orders";
      history.pushState(null, "", "/orders");
      return `付款二维码已生成：${paymentOut.payment.asset} ${paymentOut.payment.crypto_amount}`;
    });
    return true;
  }
  if (actionName === "buy-plan") {
    const planId = button.dataset.plan || "";
    await runAction(async () => {
      const out = await post("/api/orders/create", { plan_id: planId, note: "self-service checkout" });
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
    return true;
  }
  if (actionName === "payment-start") {
    const orderId = button.dataset.order || "";
    const selector = app.querySelector(`select[data-payment-method-for="${cssEscape(orderId)}"]`);
    await runAction(async () => {
      const out = await post("/api/payments/create", { order_id: orderId, method_id: selector?.value || "" });
      return `付款码已生成：${out.payment.asset} ${out.payment.crypto_amount}`;
    });
    return true;
  }
  if (actionName === "payment-refresh") {
    await runAction(async () => {
      const out = await post("/api/payments/refresh", { id: button.dataset.payment || "" });
      return `付款状态：${out.payment.status}`;
    });
    return true;
  }
  if (actionName === "payment-submit-txid") {
    const card = button.closest("article");
    const txid = card?.querySelector('input[name="txid"]')?.value || "";
    await runAction(async () => {
      const path = txid.trim() ? "/api/payments/submit-tx" : "/api/payments/refresh";
      const out = await post(path, { id: button.dataset.payment || "", txid });
      return `付款状态：${out.payment.status}`;
    });
    return true;
  }
  if (actionName === "payment-method-edit") {
    const method = (state.data.payment_methods || []).find((item) => item.id === button.dataset.method);
    const form = app.querySelector('form[data-form="payment-method-save"]');
    if (method && form) {
      app.querySelector(".payment-method-form").hidden = false;
      form.elements.payment_type.value = `${String(method.asset || "").toUpperCase()}:${String(method.chain || "").toLowerCase()}`;
      form.elements.address.value = method.address || "";
      form.elements.enabled.value = method.enabled === false ? "false" : "true";
      form.elements.address.focus();
    }
    return true;
  }
  if (actionName === "payment-method-action") {
    const action = button.dataset.methodAction || "";
    if (action === "delete" && !confirm(`确认删除收款方式 ${button.dataset.method || ""}？`)) return true;
    await runAction(async () => {
      await post("/api/payment-methods/action", { id: button.dataset.method || "", action });
      return "收款方式已更新";
    });
    return true;
  }
  return false;
}


export async function handlePaymentForm(form, data, { runAction }) {
  if (form.dataset.form !== "payment-method-save") return false;
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
  return true;
}
