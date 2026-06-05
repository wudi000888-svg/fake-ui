import { post } from "../api.js";
import { showInlineForm } from "../dom.js";


export async function handleOrderAction(button, app, { runAction, refresh, setNotice }) {
  const actionName = button.dataset.action;
  if (actionName === "order-create-sheet") {
    showInlineForm(app, ".order-create-form");
    return true;
  }
  if (actionName === "orders-refresh") {
    await refresh();
    setNotice("已刷新", "success");
    return true;
  }
  if (actionName === "order-cancel") {
    if (!confirm(`确认取消订单 ${button.dataset.order || ""}？`)) return true;
    await runAction(async () => {
      await post("/api/orders/action", { id: button.dataset.order || "", action: "cancel" });
      return "订单已取消";
    });
    return true;
  }
  if (actionName === "order-action") {
    const action = button.dataset.orderAction || "";
    if (action === "cancel" && !confirm(`确认取消订单 ${button.dataset.order || ""}？`)) return true;
    await runAction(async () => {
      await post("/api/orders/action", { id: button.dataset.order || "", action });
      return action === "confirm" ? "订单已确认" : "订单已取消";
    });
    return true;
  }
  return false;
}


export async function handleOrderForm(form, data, { runAction }) {
  if (form.dataset.form !== "order-create") return false;
  await runAction(async () => {
    const out = await post("/api/orders/create", data);
    history.pushState(null, "", "/orders");
    return `订单已创建：${out.order.id}`;
  }, "订单已创建");
  return true;
}
