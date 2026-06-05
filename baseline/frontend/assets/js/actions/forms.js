import { cssEscape, fillForm, openForm, closeBySelector } from "../dom.js";


const FORM_SELECTOR = ".user-create-form, .user-edit-form, .node-edit-form, .plan-edit-form";


export function closeForms(root) {
  closeBySelector(root, FORM_SELECTOR);
}


export function setFilter(root, state, key) {
  const input = root.querySelector(`[data-filter="${cssEscape(key)}"]`);
  state.filters[key] = input?.value || "";
}


export function openCheckout(root, planId) {
  root.querySelectorAll(".checkout-panel").forEach((panel) => {
    panel.hidden = panel.dataset.checkoutFor !== planId;
  });
  const panel = root.querySelector(`.checkout-panel[data-checkout-for="${cssEscape(planId)}"]`);
  panel?.querySelector("select, button")?.focus();
  panel?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  return Boolean(panel);
}


export function closeCheckout(root, planId = "") {
  const selector = planId ? `.checkout-panel[data-checkout-for="${cssEscape(planId)}"]` : ".checkout-panel";
  root.querySelectorAll(selector).forEach((panel) => {
    panel.hidden = true;
  });
}


export function fillNodeForm(root, node) {
  openForm(root, ".node-edit-form");
  const form = root.querySelector('form[data-form="node-save"]');
  fillForm(form, node || {}, [
    "id",
    "name",
    "kind",
    "group",
    "region",
    "multiplier",
    "status",
    "latency_ms",
    "outbound_mode",
    "sort",
    "proxy_addr",
    "proxy_port",
    "proxy_user",
  ]);
  if (form?.elements.proxy_password) form.elements.proxy_password.value = "";
  form?.scrollIntoView({ behavior: "smooth", block: "start" });
  form?.elements.name?.focus();
}


export function fillUserForm(root, user) {
  openForm(root, ".user-edit-form");
  const form = root.querySelector('form[data-form="user-edit"]');
  fillForm(form, {
    username: user?.username || "",
    action: "extend",
    plan_id: user?.plan_id || "",
    days: "30",
    quota_gb: "",
    node_ids: (user?.node_ids || []).join(","),
  }, ["username", "action", "plan_id", "days", "quota_gb", "node_ids"]);
  form?.scrollIntoView({ behavior: "smooth", block: "start" });
  form?.elements.action?.focus();
}


export function fillPlanForm(root, plan = {}) {
  openForm(root, ".plan-edit-form");
  const form = root.querySelector('form[data-form="plan-save"]');
  fillForm(form, {
    id: plan?.id || "",
    name: plan?.name || "",
    days: plan?.days ?? "30",
    traffic_gb: plan?.traffic_gb ?? "0",
    price: plan?.price ?? "0",
    node_groups: Array.isArray(plan?.node_groups) ? plan.node_groups.join(",") : (plan?.node_groups || "default"),
    sort: plan?.sort ?? "100",
    enabled: plan?.enabled === false ? "false" : "true",
  }, ["id", "name", "days", "traffic_gb", "price", "node_groups", "sort", "enabled"]);
  if (form?.elements.id) form.elements.id.readOnly = Boolean(plan?.id);
  form?.scrollIntoView({ behavior: "smooth", block: "start" });
  form?.elements.name?.focus();
}
