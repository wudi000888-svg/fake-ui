import { api, download, downloadText, post } from "../api.js?v=3.1.0";
import { state } from "../state.js?v=3.1.0";
import { closeForms, fillDesktopForm, fillPlanForm } from "./forms.js?v=3.1.0";
import { applyNodePayload } from "./users_nodes.js?v=3.1.0";


async function fileToBase64(file) {
  const buffer = await file.arrayBuffer();
  let binary = "";
  const bytes = new Uint8Array(buffer);
  const chunkSize = 0x8000;
  for (let i = 0; i < bytes.length; i += chunkSize) {
    binary += String.fromCharCode(...bytes.slice(i, i + chunkSize));
  }
  return btoa(binary);
}


export async function handleAdminAction(button, app, { runAction }) {
  const actionName = button.dataset.action;
  if (actionName === "plan-create-sheet") {
    closeForms(app);
    fillPlanForm(app, {});
    return true;
  }
  if (actionName === "plan-edit") {
    const plan = (state.data.plans || []).find((item) => item.id === button.dataset.plan);
    closeForms(app);
    fillPlanForm(app, plan);
    return true;
  }
  if (actionName === "plan-action") {
    const action = button.dataset.planAction || "";
    if (action === "delete" && !confirm(`确认删除套餐 ${button.dataset.plan || ""}？`)) return true;
    await runAction(async () => {
      await post("/api/plans/action", { id: button.dataset.plan || "", action });
      if (action === "delete") return "套餐已删除";
      return "套餐已更新";
    });
    return true;
  }
  if (actionName === "cache-clear") {
    await runAction(async () => {
      await post("/api/cache/clear", {});
      return "缓存已清理";
    });
    return true;
  }
  if (actionName === "desktop-create-sheet") {
    closeForms(app);
    fillDesktopForm(app, {});
    return true;
  }
  if (actionName === "desktop-form-close") {
    closeForms(app);
    return true;
  }
  if (actionName === "desktop-edit") {
    const device = (state.data.desktops || []).find((item) => item.id === button.dataset.desktop);
    closeForms(app);
    fillDesktopForm(app, device);
    return true;
  }
  if (actionName === "desktop-bundle-export") {
    const id = button.dataset.desktop || "";
    if (!id) return true;
    await download(`/api/desktops/${encodeURIComponent(id)}/bundle`);
    return true;
  }
  if (actionName === "desktop-wireguard-export") {
    const id = button.dataset.desktop || "";
    if (!id) return true;
    const out = await api(`/api/desktops/${encodeURIComponent(id)}/wireguard-config`);
    downloadText(out.filename || `${id}-wireguard.conf`, out.content || "", out.content_type || "text/plain");
    return true;
  }
  if (actionName === "desktop-server-wireguard-export") {
    const out = await api("/api/desktops/server-wireguard-config");
    downloadText(out.filename || "fake-ui-vps-wireguard.conf", out.content || "", out.content_type || "text/plain");
    return true;
  }
  if (actionName === "desktop-apply-wireguard") {
    if (!confirm("确认在 VPS 上写入并启动 WireGuard？请先确认 VPS 私钥和设备公钥都已配置。")) return true;
    await runAction(async () => {
      const out = await post("/api/desktops/apply-wireguard", {});
      return out?.result?.message || "VPS WireGuard 已应用";
    });
    return true;
  }
  if (actionName === "desktop-apply") {
    if (!confirm("确认应用远程访问配置到 Hysteria2？这只会更新 desktop-* 设备账号，并重启 Hysteria2。")) return true;
    await runAction(async () => {
      const out = await post("/api/desktops/apply", {});
      if (out?.devices) state.data.desktops = out.devices;
      if (out?.topology) state.data.desktop_topology = out.topology;
      return out?.result?.message || "远程访问配置已应用";
    });
    return true;
  }
  if (actionName === "desktop-action") {
    const action = button.dataset.desktopAction || "";
    if (action === "delete" && !confirm(`确认删除远程访问设备 ${button.dataset.desktop || ""}？`)) return true;
    await runAction(async () => {
      const out = await post("/api/desktops/action", { id: button.dataset.desktop || "", action });
      if (out?.devices) state.data.desktops = out.devices;
      if (out?.topology) state.data.desktop_topology = out.topology;
      if (action === "delete") return "远程访问设备已删除";
      return "远程访问设备已更新";
    });
    return true;
  }
  if (actionName === "backup-create") {
    await runAction(async () => {
      await post("/api/backups/create", { reason: "manual" });
      return "备份已创建";
    });
    return true;
  }
  if (actionName === "backup-download") {
    const name = button.dataset.backup || "";
    if (!name) return true;
    try {
      state.busy = true;
      await download(`/api/backups/download?name=${encodeURIComponent(name)}`, name);
      return true;
    } finally {
      state.busy = false;
    }
  }
  if (actionName === "hy2-disable") {
    await runAction(async () => {
      const out = await post("/api/hy2/disable", {});
      applyNodePayload(out);
      if (out?.hy2) state.data.hy2 = out.hy2;
      return "Hysteria2 已恢复直连，节点信息已同步";
    });
    return true;
  }
  return false;
}


export async function handleAdminForm(form, data, app, { runAction }) {
  if (form.dataset.form === "public-settings-save") {
    await runAction(async () => {
      const out = await post("/api/public-settings", {
        registration_enabled: data.registration_enabled === "true",
      });
      state.data.public_settings = out.public_settings || {};
      state.publicSettings = out.public_settings || {};
      if (state.shell) state.shell.public_settings = state.publicSettings;
      return "公开设置已保存";
    });
    return true;
  }
  if (form.dataset.form === "email-settings-save") {
    await runAction(async () => {
      const out = await post("/api/email-settings", {
        ...data,
        password_reset_enabled: data.password_reset_enabled === "true",
        smtp_tls: data.smtp_tls !== "false",
      });
      state.data.email_settings = out.email_settings || {};
      state.data.public_settings = out.public_settings || {};
      state.publicSettings = out.public_settings || {};
      if (state.shell) state.shell.public_settings = state.publicSettings;
      return "邮箱设置已保存";
    });
    return true;
  }
  if (form.dataset.form === "backup-import") {
    await runAction(async () => {
      const file = form.elements.backup_file?.files?.[0];
      if (!file) throw new Error("请选择备份文件");
      if (!confirm("确认导入并恢复这个备份？系统会先自动创建安全备份。")) return "已取消导入";
      await post("/api/backups/upload", { filename: file.name, content_b64: await fileToBase64(file) });
      form.reset();
      return "备份已导入并恢复";
    });
    return true;
  }
  if (form.dataset.form === "hy2-save") {
    await runAction(async () => {
      const out = await post("/api/hy2/apply", data);
      applyNodePayload(out);
      if (out?.hy2) state.data.hy2 = out.hy2;
      return "Hysteria2 出口已保存，节点信息已同步";
    });
    return true;
  }
  if (form.dataset.form === "desktop-save") {
    await runAction(async () => {
      const out = await post("/api/desktops/save", {
        ...data,
        enabled: data.enabled !== "false",
      });
      if (out?.devices) state.data.desktops = out.devices;
      if (out?.topology) state.data.desktop_topology = out.topology;
      form.reset();
      closeForms(app);
      return "远程访问设备已保存";
    });
    return true;
  }
  if (form.dataset.form === "desktop-network-save") {
    await runAction(async () => {
      const out = await post("/api/desktops/network", data);
      if (out?.network) state.data.desktop_network = out.network;
      if (out?.topology) state.data.desktop_topology = out.topology;
      return "远程访问网络设置已保存";
    });
    return true;
  }
  if (form.dataset.form !== "plan-save") return false;
  await runAction(async () => {
    await post("/api/plans/save", {
      ...data,
      enabled: data.enabled !== "false",
    });
    form.reset();
    closeForms(app);
    return "套餐已保存";
  });
  return true;
}
