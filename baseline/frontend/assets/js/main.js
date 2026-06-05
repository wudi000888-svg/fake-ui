import { api } from "./api.js";
import { state, setNotice } from "./state.js";
import { bindPopstate } from "./router.js";
import { layout, bindLayoutEvents } from "./components/layout.js";
import { loginView } from "./components/login.js";
import { bindAppActions } from "./actions/handlers.js";
import { pageForState } from "./pages/registry.js";


const app = document.querySelector("#app");


export async function refresh() {
  const result = await api("/api/dashboard");
  state.session = result.data.session;
  state.data = result.data || {};
}


export async function render() {
  if (!state.session) {
    app.innerHTML = loginView();
    return;
  }
  app.innerHTML = layout(pageForState(state));
}


async function boot() {
  try {
    const sessionResult = await api("/api/session");
    state.session = sessionResult.session;
    if (state.session) {
      state.shell = await api("/api/app-shell");
      await refresh();
    }
  } catch (error) {
    setNotice(error.message, "error");
  }
  bindPopstate();
  bindLayoutEvents(app);
  bindAppActions(app, { refresh, render });
  window.addEventListener("fake-ui:navigate", render);
  await render();
}


boot();
