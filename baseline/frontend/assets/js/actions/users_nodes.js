import { api, download, downloadText, post } from "../api.js?v=3.0.1";
import { openForm } from "../dom.js?v=3.0.1";
import { state } from "../state.js?v=3.0.1";
import { closeForms, fillNodeForm, fillTunnelForm, fillUserForm } from "./forms.js?v=3.0.1";


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


export function applyTunnelPayload(out) {
  if (out?.domain_options) state.data.domain_options = out.domain_options;
  if (out?.tunnels) state.data.tunnels = out.tunnels;
  if (out?.tunnel && !out.tunnels) {
    const tunnels = state.data.tunnels || [];
    const index = tunnels.findIndex((item) => item.id === out.tunnel.id);
    state.data.tunnels = index >= 0
      ? tunnels.map((item) => item.id === out.tunnel.id ? out.tunnel : item)
      : [...tunnels, out.tunnel];
  }
}


export async function handleUserNodeAction(button, app, { runAction }) {
  const actionName = button.dataset.action;
  if (actionName === "user-create-sheet") {
    closeForms(app);
    openForm(app, ".user-create-form");
    return true;
  }
  if (actionName === "user-form-close" || actionName === "node-form-close" || actionName === "plan-form-close" || actionName === "tunnel-form-close") {
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
  if (actionName === "tunnel-create-sheet") {
    closeForms(app);
    fillTunnelForm(app, {});
    return true;
  }
  if (actionName === "tunnel-edit") {
    const tunnel = (state.data.tunnels || []).find((item) => item.id === button.dataset.tunnel);
    closeForms(app);
    fillTunnelForm(app, tunnel);
    return true;
  }
  if (actionName === "tunnel-agent-config-export") {
    const id = button.dataset.tunnel || "";
    if (!id) return true;
    const out = await api(`/api/tunnels/${encodeURIComponent(id)}/bridge-config`);
    downloadText(out.filename || `${id}-xray-bridge.json`, JSON.stringify(out.config || {}, null, 2));
    return true;
  }
  if (actionName === "tunnel-agent-bundle-export") {
    const id = button.dataset.tunnel || "";
    if (!id) return true;
    const platform = button.dataset.platform || "";
    const path = platform
      ? `/api/tunnels/${encodeURIComponent(id)}/${encodeURIComponent(platform)}-agent-bundle`
      : `/api/tunnels/${encodeURIComponent(id)}/agent-bundle`;
    await download(path);
    return true;
  }
  if (actionName === "tunnel-universal-agent-bundle-export") {
    const kind = button.dataset.agentKind || "";
    if (kind === "shared") {
      const bridgeId = button.dataset.bridge || "";
      if (!bridgeId) return true;
      await download(`/api/tunnels/bridges/${encodeURIComponent(bridgeId)}/agent-bundle`);
      return true;
    }
    const id = button.dataset.tunnel || "";
    if (!id) return true;
    await download(`/api/tunnels/${encodeURIComponent(id)}/agent-bundle`);
    return true;
  }
  if (actionName === "tunnel-shared-agent-config-export") {
    const bridgeId = button.dataset.bridge || "";
    if (!bridgeId) return true;
    const out = await api(`/api/tunnels/bridges/${encodeURIComponent(bridgeId)}/bridge-config`);
    downloadText(out.filename || `${bridgeId}-xray-bridge.json`, JSON.stringify(out.config || {}, null, 2));
    return true;
  }
  if (actionName === "tunnel-shared-agent-bundle-export") {
    const bridgeId = button.dataset.bridge || "";
    if (!bridgeId) return true;
    const platform = button.dataset.platform || "";
    const path = platform
      ? `/api/tunnels/bridges/${encodeURIComponent(bridgeId)}/${encodeURIComponent(platform)}-agent-bundle`
      : `/api/tunnels/bridges/${encodeURIComponent(bridgeId)}/agent-bundle`;
    await download(path);
    return true;
  }
  if (actionName === "tunnel-portal-export") {
    const out = await api("/api/tunnels/portal-config");
    downloadText(out.filename || "fake-ui-tunnel-portal.json", JSON.stringify(out.config || {}, null, 2));
    return true;
  }
  if (actionName === "tunnel-portal-apply") {
    if (!confirm("确认把当前穿透入口应用到 Xray？应用前会测试配置，失败会回滚。")) return true;
    await runAction(async () => {
      const out = await post("/api/tunnels/apply", {});
      applyTunnelPayload(out);
      return out.message || "穿透入口已应用";
    });
    return true;
  }
  if (actionName === "tunnel-action") {
    const action = button.dataset.tunnelAction || "";
    if (action === "delete" && !confirm(`确认删除穿透节点 ${button.dataset.tunnel || ""}？`)) return true;
    await runAction(async () => {
      const out = await post("/api/tunnels/action", { id: button.dataset.tunnel || "", action });
      applyTunnelPayload(out);
      if (action === "delete") return "穿透节点已删除";
      return "穿透节点已更新";
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
  if (form.dataset.form === "tunnel-save") {
    await runAction(async () => {
      const out = await post("/api/tunnels/save", data);
      applyTunnelPayload(out);
      return "穿透节点已保存";
    });
    return true;
  }
  return false;
}
