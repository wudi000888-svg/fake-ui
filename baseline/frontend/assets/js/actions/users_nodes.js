import { post } from "../api.js";
import { openForm } from "../dom.js";
import { state } from "../state.js";
import { closeForms, fillNodeForm, fillUserForm } from "./forms.js";


export function applyNodePayload(out) {
  if (out?.nodes) state.data.nodes = out.nodes;
  if (out?.node && !out.nodes) {
    const nodes = state.data.nodes || [];
    const index = nodes.findIndex((item) => item.id === out.node.id);
    state.data.nodes = index >= 0
      ? nodes.map((item) => item.id === out.node.id ? out.node : item)
      : [...nodes, out.node];
  }
}


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
      const out = await post("/api/nodes/action", { id: button.dataset.node || "", action: "refresh" });
      applyNodePayload(out);
      return "出口质量已刷新，节点信息已同步";
    });
    return true;
  }
  if (actionName === "node-action") {
    const action = button.dataset.nodeAction || "";
    if (action === "delete" && !confirm(`确认删除节点 ${button.dataset.node || ""}？`)) return true;
    await runAction(async () => {
      const out = await post("/api/nodes/action", { id: button.dataset.node || "", action });
      applyNodePayload(out);
      if (action === "refresh") return "出口质量已刷新";
      if (action === "delete") return "节点已删除";
      return "节点已更新";
    });
    return true;
  }
  if (actionName === "node-add") {
    await runAction(async () => {
      const out = await post("/api/nodes/add-vless", {});
      applyNodePayload(out);
      return "节点已新增，出口信息已同步";
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
      await post("/api/users/update", payload);
      return "用户已保存";
    });
    return true;
  }
  if (form.dataset.form === "node-save") {
    await runAction(async () => {
      const out = await post("/api/nodes/save", data);
      applyNodePayload(out);
      return "节点已保存，出口信息已同步";
    });
    return true;
  }
  return false;
}
