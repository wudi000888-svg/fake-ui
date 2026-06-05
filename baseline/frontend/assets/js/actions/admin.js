import { post } from "../api.js";
import { state } from "../state.js";
import { closeForms, fillPlanForm } from "./forms.js";


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
  return false;
}


export async function handleAdminForm(form, data, app, { runAction }) {
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
