import { cssEscape, fillForm, openForm, closeBySelector } from "../dom.js?v=3.0.2";


const FORM_SELECTOR = ".user-create-form, .user-edit-form, .node-edit-form, .plan-edit-form, .hy2-edit-form, .tunnel-edit-form";


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


export function fillTunnelForm(root, tunnel = {}) {
  openForm(root, ".tunnel-edit-form");
  const form = root.querySelector('form[data-form="tunnel-save"]');
  fillForm(form, {
    kind: tunnel?.kind || "public_https",
    id: tunnel?.id || "",
    public_domain: tunnel?.public_domain || "",
    name: tunnel?.name || "",
    portal_port: tunnel?.portal_port ?? "",
    target_host: tunnel?.target_host || "127.0.0.1",
    target_port: tunnel?.target_port ?? "3000",
    client_id: tunnel?.client_id || "",
    reality_sni: tunnel?.reality_sni || "www.cloudflare.com",
    bridge_mode: tunnel?.bridge_mode || "dedicated",
    bridge_id: tunnel?.bridge_id || tunnel?.id || "",
    bridge_platform: tunnel?.bridge_platform || "macos",
  }, [
    "kind",
    "id",
    "public_domain",
    "name",
    "portal_port",
    "target_host",
    "target_port",
    "client_id",
    "reality_sni",
    "bridge_mode",
    "bridge_id",
    "bridge_platform",
  ]);
  form?.scrollIntoView({ behavior: "smooth", block: "start" });
  form?.elements.name?.focus();
}


export function fillUserForm(root, user) {
  openForm(root, ".user-edit-form");
  const form = root.querySelector('form[data-form="user-edit"]');
  fillForm(form, {
    username: user?.username || "",
    enabled: user?.enabled === false ? "false" : "true",
    plan_id: user?.plan_id || "",
    days: "",
    quota_gb: "",
    note: user?.note || "",
  }, ["username", "enabled", "plan_id", "days", "quota_gb", "note"]);
  const selected = new Set(user?.node_ids || []);
  form?.querySelectorAll('input[type="checkbox"][name="node_ids"]').forEach((input) => {
    input.checked = selected.has(input.value);
  });
  form?.scrollIntoView({ behavior: "smooth", block: "start" });
  form?.elements.enabled?.focus();
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
