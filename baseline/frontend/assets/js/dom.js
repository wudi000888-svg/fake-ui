export function formData(form) {
  return Object.fromEntries(new FormData(form).entries());
}


export function cssEscape(value) {
  if (window.CSS?.escape) return window.CSS.escape(String(value || ""));
  return String(value || "").replace(/["\\]/g, "\\$&");
}


export async function copyText(text) {
  const value = String(text || "");
  if (!value) throw new Error("没有可复制的内容");
  if (navigator.clipboard?.writeText && window.isSecureContext) {
    await navigator.clipboard.writeText(value);
    return;
  }
  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();
  document.execCommand("copy");
  textarea.remove();
}


export function openForm(root, selector) {
  const el = root.querySelector(selector);
  if (!el) return false;
  el.hidden = false;
  el.querySelector("input, select, button")?.focus();
  return true;
}


export function showInlineForm(root, selector) {
  const el = root.querySelector(selector);
  if (!el) return false;
  el.hidden = !el.hidden;
  if (!el.hidden) el.querySelector("input, select, button")?.focus();
  return true;
}


export function fillForm(form, values, fields) {
  if (!form) return;
  fields.forEach((key) => {
    if (form.elements[key]) form.elements[key].value = values?.[key] ?? "";
  });
}


export function closeBySelector(root, selector) {
  root.querySelectorAll(selector).forEach((el) => {
    el.hidden = true;
  });
}
