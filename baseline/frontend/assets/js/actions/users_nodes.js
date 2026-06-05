import { post } from "../api.js";
import { openForm } from "../dom.js";
import { state } from "../state.js";
import { closeForms, fillNodeForm, fillUserForm } from "./forms.js";


export async function handleUserNodeAction(button, app, { runAction }) {
  const actionName = button.dataset.action;
  if (actionName === "user-create-sheet") {
    closeForms(app);
    openForm(app, ".user-create-form");
    return true;
  }
  if (actionName === "user-form-close" || actionName === "node-form-close" || actionName === "plan-form-close") {
    closeForms(app);
    return true;
  }
  if (actionName === "user-edit") {
    const user = (state.data.users || []).find((item) => item.username === button.dataset.user);
    closeForms(app);
    fillUserForm(app, user);
    return true;
  }
  if (actionName === "user-action") {
    const action = button.dataset.userAction || "";
    if (action === "delete" && !confirm(`确认删除用户 ${button.dataset.user || ""}？`)) return true;
    await runAction(async () => {
      await post("/api/users/action", { username: button.dataset.user || "", action, days: "30" });
      if (action === "delete") return "用户已删除";
      if (action === "reset_traffic") return "用户流量已清零";
      if (action === "extend") return "用户已续期";
      return "用户已更新";
    });
    return true;
  }
  if (actionName === "reset-sub") {
    await runAction(async () => {
      await post("/api/users/reset-subscription", { username: button.dataset.user || "" });
      return "订阅已重置";
    });
    return true;
  }
  if (actionName === "node-edit") {
    const node = (state.data.nodes || []).find((item) => item.id === button.dataset.node);
    closeForms(app);
    fillNodeForm(app, node);
    return true;
  }
  if (actionName === "node-quality-check") {
    await runAction(async () => {
      await post("/api/nodes/action", { id: button.dataset.node || "", action: "refresh" });
      return "出口质量已刷新";
    });
    return true;
  }
  if (actionName === "node-action") {
    const action = button.dataset.nodeAction || "";
    if (action === "delete" && !confirm(`确认删除节点 ${button.dataset.node || ""}？`)) return true;
    await runAction(async () => {
      await post("/api/nodes/action", { id: button.dataset.node || "", action });
      if (action === "refresh") return "出口质量已刷新";
      if (action === "delete") return "节点已删除";
      return "节点已更新";
    });
    return true;
  }
  if (actionName === "node-add") {
    await runAction(async () => {
      await post("/api/nodes/add-vless", {});
      return "节点已新增";
    });
    return true;
  }
  return false;
}


export async function handleUserNodeForm(form, data, { runAction }) {
  if (form.dataset.form === "user-create") {
    await runAction(async () => {
      const out = await post("/api/users/create", data);
      form.reset();
      return `用户已创建：${out.result.username}，密码：${out.result.panel_password}`;
    });
    return true;
  }
  if (form.dataset.form === "user-edit") {
    await runAction(async () => {
      const payload = { ...data };
      if (payload.action !== "set_nodes") delete payload.node_ids;
      await post("/api/users/action", payload);
      return "用户已保存";
    });
    return true;
  }
  if (form.dataset.form === "node-save") {
    await runAction(async () => {
      await post("/api/nodes/save", data);
      return "节点已保存";
    });
    return true;
  }
  return false;
}
