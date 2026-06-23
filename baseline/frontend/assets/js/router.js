import { state, setRouteFromLocation } from "./state.js?v=3.1.0";


export function navigate(route) {
  const next = route || "dashboard";
  state.route = next;
  const path = next === "dashboard" ? "/" : `/${next}`;
  if (location.pathname !== path) {
    history.pushState(null, "", path);
  }
  window.dispatchEvent(new CustomEvent("fake-ui:navigate"));
}


export function bindPopstate() {
  window.addEventListener("popstate", () => {
    setRouteFromLocation();
    window.dispatchEvent(new CustomEvent("fake-ui:navigate"));
  });
}
