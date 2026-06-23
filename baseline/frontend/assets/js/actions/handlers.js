import { api, post } from "../api.js?v=3.0.2";
import { formData } from "../dom.js?v=3.0.2";
import { navigate } from "../router.js?v=3.0.2";
import { state, setNotice } from "../state.js?v=3.0.2";
import { setFilter } from "./forms.js?v=3.0.2";
import { handleAdminAction, handleAdminForm } from "./admin.js?v=3.0.2";
import { handleOrderAction, handleOrderForm } from "./orders.js?v=3.0.2";
import { handlePaymentAction, handlePaymentForm } from "./payments.js?v=3.0.2";
import { handleUserNodeAction, handleUserNodeForm } from "./users_nodes.js?v=3.0.2";


export function bindAppActions(app, { refresh, render, loadAuthenticatedApp }) {
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
        await loadAuthenticatedApp();
        navigate("dashboard");
        setNotice("登录成功", "success");
        await render();
        return;
      }
      if (form.dataset.form === "register") {
        const result = await post("/api/register", data);
        navigate("login");
        setNotice(result.message || "注册成功，请登录", "success");
        location.href = "/login?registered=1";
        await render();
        return;
      }
      if (form.dataset.form === "password-reset-send") {
        const result = await post("/api/password-reset/send-code", data);
        setNotice(result.message || "验证码已发送", "success");
        await render();
        return;
      }
      if (form.dataset.form === "password-reset-confirm") {
        const result = await post("/api/password-reset/confirm", data);
        navigate("login");
        setNotice(result.message || "密码已重置，请登录", "success");
        await render();
        return;
      }
      if (form.dataset.form === "self-email") {
        await runAction(async () => {
          await post("/api/self/email", data);
          return "邮箱已保存";
        });
        return;
      }
      if (form.dataset.form === "self-password") {
        if ((data.new_password || "") !== (data.new_password_confirm || "")) {
          throw new Error("两次输入的新密码不一致");
        }
        await runAction(async () => {
          await post("/api/self/password", {
            old_password: data.old_password || "",
            new_password: data.new_password || "",
          });
          form.reset();
          return "密码已更新";
        });
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
      if (button.dataset.action === "retry-boot") {
        await loadAuthenticatedApp();
        setNotice("已恢复连接", "success");
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
      if (button.dataset.action === "tunnels-filter") {
        setFilter(app, state, "tunnels");
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
        window.localStorage.removeItem("fake-ui-csrf");
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
