import links
import hy2_panel
import admin_profile
import node_catalog
import user_store
import xray_panel
import simple_pages
import payments_store
from qr_service import qr_png_for_link


def handle_user_node_qr(handler):
    try:
        parts = handler.path.split("?", 1)[0].strip("/").split("/")
        target_user = parts[1]
        kind = parts[2]
        node_id = parts[3] if len(parts) > 3 else ""
        if handler.current_role() != "admin" and handler.current_username() != target_user:
            handler.forbidden()
            return
        user = user_store.get_user(target_user)
        if not user or not user_store.user_is_active(target_user, user):
            raise RuntimeError("用户无效或已过期")
        if kind == "vless":
            node = node_catalog.get_node(node_id) if node_id else None
            link = links.build_vless_link_for_airport_user(target_user, user, node)
        elif kind == "hy2":
            link = links.build_hy2_link_for_airport_user(target_user, user)
        else:
            raise RuntimeError("未知节点类型")
        handler.respond_bytes(qr_png_for_link(link), "image/png")
    except Exception as exc:
        handler.respond_text("Invalid QR: " + str(exc), 403)


def handle_admin_node_qr(handler, username, role):
    try:
        if role != "admin":
            handler.forbidden()
            return
        parts = handler.path.split("?", 1)[0].rstrip("/").strip("/").split("/")
        kind = parts[1] if len(parts) > 1 else ""
        node_id = parts[2] if len(parts) > 2 else ""
        link = build_admin_node_link(kind, node_id)
        handler.respond_bytes(qr_png_for_link(link), "image/png")
    except Exception as exc:
        handler.respond(simple_pages.qr_error(str(exc)), 403)


def handle_payment_qr(handler):
    try:
        parts = handler.path.split("?", 1)[0].rstrip("/").strip("/").split("/")
        payment_id = parts[1] if len(parts) > 1 else ""
        payment = payments_store.get_payment(payment_id)
        if not payment:
            handler.respond_text("Invalid QR: payment not found", 404)
            return
        if handler.current_role() != "admin" and handler.current_username() != payment.get("username"):
            handler.forbidden()
            return
        payload = payment.get("qr_payload") or payment.get("address") or ""
        if not payload:
            raise RuntimeError("payment QR payload missing")
        handler.respond_bytes(qr_png_for_link(payload), "image/png")
    except Exception as exc:
        handler.respond_text("Invalid QR: " + str(exc), 403)


def build_admin_node_link(kind, node_id=""):
    if kind == "vless":
        if node_id:
            return links.build_vless_link_for_airport_user(
                admin_profile.ADMIN_USERNAME,
                admin_profile.get_admin_user(),
                node_catalog.get_node(node_id),
            )
        user = admin_profile.get_admin_user()
        node = (node_catalog.nodes_for_user(user, kind="vless", include_disabled=False) or [None])[0]
        return links.build_vless_link_for_airport_user(admin_profile.ADMIN_USERNAME, user, node)
    if kind in ("hy2", "hysteria2"):
        return hy2_panel.build_hy2_link()
    raise RuntimeError("unknown node type: " + str(kind))
