import { api, post } from "../api.js";
import { formData } from "../dom.js";
import { navigate } from "../router.js";
import { state, setNotice } from "../state.js";
import { setFilter } from "./forms.js";
import { handleAdminAction, handleAdminForm } from "./admin.js";
import { handleOrderAction, handleOrderForm } from "./orders.js";
import { handlePaymentAction, handlePaymentForm } from "./payments.js";
import { handleUserNodeAction, handleUserNodeForm } from "./users_nodes.js";


export function bindAppActions(app, { refresh, render }) {
  async function runAction(work, success = "操作已完成") {
    try {
      state.busy = true;
      const message = await work();
      await refresh();
      setNotice(message || success, "success");
    } catch (error) {
      setNotice(error.message, "error");
    } finally {
      state.busy = false;
      await render();
    }
  }

  const context = { refresh, render, runAction, setNotice };

  app.addEventListener("submit", async (event) => {
    const form = event.target.closest("[data-form]");
    if (!form) return;
    event.preventDefault();
    const data = formData(form);
    try {
      if (form.dataset.form === "login") {
        const result = await post("/api/login", data);
        state.session = result.session;
        state.shell = await api("/api/app-shell");
        await refresh();
        setNotice("登录成功", "success");
        await render();
        return;
      }
      if (await handleOrderForm(form, data, context)) return;
      if (await handlePaymentForm(form, data, context)) return;
      if (await handleUserNodeForm(form, data, context)) return;
      if (await handleAdminForm(form, data, app, context)) return;
    } catch (error) {
      setNotice(error.message, "error");
    }
    await render();
  });

  app.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-action]");
    if (!button) return;
    if (state.busy && button.dataset.action !== "logout") return;
    try {
      if (button.dataset.action === "refresh") {
        await refresh();
        setNotice("已刷新", "success");
      }
      if (button.dataset.action === "open-plans") {
        navigate("plans");
        return;
      }
      if (button.dataset.action === "open-links") {
        navigate("links");
        return;
      }
      if (button.dataset.action === "open-nodes") {
        navigate("nodes");
        return;
      }
      if (button.dataset.action === "users-filter") {
        setFilter(app, state, "users");
        await render();
        return;
      }
      if (button.dataset.action === "nodes-filter") {
        setFilter(app, state, "nodes");
        await render();
        return;
      }
      if (button.dataset.action === "orders-filter") {
        setFilter(app, state, "orders");
        await render();
        return;
      }
      if (button.dataset.action === "plans-filter") {
        setFilter(app, state, "plans");
        await render();
        return;
      }
      if (await handleOrderAction(button, app, context)) return;
      if (await handlePaymentAction(button, app, context)) return;
      if (await handleUserNodeAction(button, app, context)) return;
      if (await handleAdminAction(button, app, context)) return;
      if (button.dataset.action === "logout") {
        await post("/api/logout", {});
        state.session = null;
        state.shell = null;
        state.data = {};
        setNotice("已退出", "success");
      }
    } catch (error) {
      setNotice(error.message, "error");
    }
    await render();
  });
}
