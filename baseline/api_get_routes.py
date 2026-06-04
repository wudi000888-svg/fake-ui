import urllib.parse

import api_v2_routes
import audit_log
import backup_manager
import hy2_panel
import node_catalog
import operations_service as ops
import orders_store
import plans_store
import registration_store
import subscription_guard
import xray_panel
from api_common import ok, require_admin
from api_payment_routes import handle_payment_get
from http_utils import api_error


def handle_get(path, session):
    clean = urllib.parse.urlparse(path).path

    v2_result = api_v2_routes.handle_get(clean, session)
    if v2_result is not None:
        return v2_result

    if clean == "/api/session":
        return ok(session=ops.public_session(session))
    if not session:
        return api_error("not authenticated", 401)

    if clean == "/api/dashboard":
        return ok(data=ops.dashboard(session))

    if clean == "/api/status":
        if (err := require_admin(session)):
            return err
        xray_status = xray_panel.current_status()
        xray_status["enabled"] = ":" in str(xray_status.get("proxy", ""))
        return ok(xray=xray_status, hy2=hy2_panel.hy2_status())

    if clean == "/api/users":
        if (err := require_admin(session)):
            return err
        return ok(users=ops.list_users())

    if clean == "/api/plans":
        if (err := require_admin(session)):
            return err
        return ok(plans=plans_store.list_plans())

    if clean == "/api/orders":
        username = None
        if (session.get("role") or session.get("r")) != "admin":
            username = session.get("u", "")
        return ok(orders=orders_store.list_orders(username=username, limit=200))

    if clean == "/api/registrations":
        if (err := require_admin(session)):
            return err
        return ok(
            registrations=registration_store.list_registrations(),
            password_resets=registration_store.list_resets(),
        )

    if clean == "/api/subscription-access":
        if (err := require_admin(session)):
            return err
        return ok(access=subscription_guard.tail(500), ip_summary=subscription_guard.ip_summary())

    if clean == "/api/nodes":
        if (err := require_admin(session)):
            return err
        return ok(nodes=node_catalog.list_public_nodes(admin=True))

    if clean == "/api/audit":
        if (err := require_admin(session)):
            return err
        return ok(audit=audit_log.tail(300))

    if clean == "/api/backups":
        if (err := require_admin(session)):
            return err
        return ok(backups=backup_manager.list_backups(100))

    if clean == "/api/links":
        role = session.get("role") or session.get("r")
        username = session.get("u", "")
        return ok(links=ops.admin_links() if role == "admin" else ops.user_links(username))

    payment_result = handle_payment_get(clean, session)
    if payment_result is not None:
        return payment_result

    return api_error("not found", 404)
