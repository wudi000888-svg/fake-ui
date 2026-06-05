import { renderAdminNodes } from "./admin/nodes.js";
import { renderAdminOrders } from "./admin/orders.js";
import { renderAdminOverview } from "./admin/overview.js";
import { renderAdminPlans } from "./admin/plans.js";
import { renderAdminDashboard, renderAdminSimplePage } from "./admin/simple.js";
import { renderAdminSettings } from "./admin/settings.js";
import { renderAdminUsers } from "./admin/users.js";
import { renderUserAccount } from "./user/account.js";
import { renderUserDashboard } from "./user/dashboard.js";
import { renderUserLinks } from "./user/links.js";
import { renderUserOrders } from "./user/orders.js";
import { renderUserPlans } from "./user/plans.js";


export function pageForState(state) {
  if (state.shell?.role !== "admin") {
    if (state.route === "plans") return renderUserPlans(state.data);
    if (state.route === "links") return renderUserLinks(state.data);
    if (state.route === "orders") return renderUserOrders(state.data);
    if (state.route === "account") return renderUserAccount(state.data, state.shell);
    return renderUserDashboard(state.data);
  }
  const data = { ...state.data, filters: state.filters };
  if (state.route === "orders") return renderAdminOrders(data);
  if (state.route === "account" || state.route === "settings") return renderAdminSettings(data);
  if (state.route === "users") return renderAdminUsers(data);
  if (state.route === "nodes") return renderAdminNodes(data);
  if (state.route === "plans") return renderAdminPlans(data);
  if (state.route === "links") return renderAdminSimplePage("订阅", state.data.links || []);
  if (state.route === "requests") return renderAdminSimplePage("申请", state.data.registrations || []);
  if (state.route === "audit") return renderAdminSimplePage("审计", state.data.audit || []);
  if (state.route === "backups") return renderAdminSimplePage("备份", state.data.backups || []);
  if (state.route === "hy2") return renderAdminDashboard(state.data);
  return renderAdminOverview(state.data);
}
