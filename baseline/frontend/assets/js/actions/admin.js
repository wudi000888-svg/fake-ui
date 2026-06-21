import { download, post } from "../api.js?v=3.0.1";
import { state } from "../state.js?v=3.0.1";
import { closeForms, fillPlanForm } from "./forms.js?v=3.0.1";
import { applyNodePayload } from "./users_nodes.js?v=3.0.1";


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
