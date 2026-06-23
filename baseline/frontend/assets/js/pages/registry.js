import { renderAdminNodes } from "./admin/nodes.js?v=3.1.0";
import { renderAdminOrders } from "./admin/orders.js?v=3.1.0";
import { renderAdminOverview } from "./admin/overview.js?v=3.1.0";
import { renderAdminBackups } from "./admin/backups.js?v=3.1.0";
import { renderAdminHy2 } from "./admin/hy2.js?v=3.1.0";
import { renderAdminPlans } from "./admin/plans.js?v=3.1.0";
import { renderAdminDashboard, renderAdminSimplePage } from "./admin/simple.js?v=3.1.0";
import { renderAdminSettings } from "./admin/settings.js?v=3.1.0";
import { renderAdminTunnels } from "./admin/tunnels.js?v=3.1.0";
import { renderAdminRemoteDesktop } from "./admin/remote_desktop.js?v=3.1.0";
import { renderAdminUsers } from "./admin/users.js?v=3.1.0";
import { renderUserAccount } from "./user/account.js?v=3.1.0";
import { renderUserDashboard } from "./user/dashboard.js?v=3.1.0";
import { renderUserLinks } from "./user/links.js?v=3.1.0";
import { renderUserOrders } from "./user/orders.js?v=3.1.0";
import { renderUserPlans } from "./user/plans.js?v=3.1.0";


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
  if (state.route === "tunnels") return renderAdminTunnels(data);
  if (state.route === "remote-desktop") return renderAdminRemoteDesktop(data);
  if (state.route === "plans") return renderAdminPlans(data);
  if (state.route === "links") return renderAdminSimplePage("订阅", state.data.links || []);
  if (state.route === "requests") return renderAdminSimplePage("申请", state.data.registrations || []);
  if (state.route === "audit") return renderAdminSimplePage("审计", state.data.audit || []);
  if (state.route === "backups") return renderAdminBackups(data);
  if (state.route === "hy2") return renderAdminHy2(data);
  return renderAdminOverview(state.data);
}
