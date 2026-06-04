import urllib.parse
from datetime import datetime, timezone

import admin_profile
import app_urls
import audit_log
import backup_manager
import hy2_panel
import links
import node_catalog
import orders_store
import payments_store
import plans_store
import registration_store
import subscription_guard
import user_store
import xray_panel


def public_session(payload):
    if not payload:
        return None
    return {"username": payload.get("u", ""), "role": payload.get("role") or payload.get("r", "")}


def user_metrics(username, user):
    used = int((user or {}).get("used_bytes", 0) or 0)
    quota = int((user or {}).get("quota_bytes", 0) or 0)
    remain = max(0, quota - used) if quota > 0 else 0
    used_percent = round(min(100, used / quota * 100), 2) if quota > 0 else 0
    expires_at = (user or {}).get("expires_at", "")
    days_left = None
    seconds_left = None
    try:
        exp = user_store.parse_time(expires_at)
        if exp:
            diff = exp - datetime.now(timezone.utc)
            seconds_left = int(diff.total_seconds())
            days_left = max(0, (seconds_left + 86399) // 86400)
    except Exception:
        pass
    plan = plans_store.get_plan((user or {}).get("plan_id", "")) or {}
    return {
        "username": username,
        "status": user_store.public_status(username, user),
        "plan_id": (user or {}).get("plan_id", ""),
        "plan_name": plan.get("name", (user or {}).get("plan_id", "") or "自定义套餐"),
        "node_groups": (user or {}).get("node_groups", ["default"]),
        "expires_at": expires_at,
        "days_left": days_left,
        "seconds_left": seconds_left,
        "used_bytes": used,
        "quota_bytes": quota,
        "remain_bytes": remain,
        "used_percent": used_percent,
        "quota_text": user_store.quota_text(user or {}),
        "quota_status": user_store.quota_status_text(user or {}),
    }


def visible_nodes_for_user(user):
    return [node_catalog.public_node(node, admin=False) for node in node_catalog.nodes_for_user(user or {}, include_disabled=False)]


def effective_node_ids_for_user(user):
    return [node.get("id", "") for node in node_catalog.nodes_for_user(user or {}, include_disabled=False) if node.get("id")]


def user_summary(username, user):
    sub_token = user.get("sub_token", "")
    base_sub = app_urls.subscription_url(sub_token) if sub_token else ""
    return {
        "username": username,
        "enabled": bool(user.get("enabled", True)),
        "status": user_store.public_status(username, user),
        "expires_at": user.get("expires_at", ""),
        "note": user.get("note", ""),
        "quota": user_store.quota_text(user),
        "quota_status": user_store.quota_status_text(user),
        "metrics": user_metrics(username, user),
        "used_bytes": int(user.get("used_bytes", 0) or 0),
        "quota_bytes": int(user.get("quota_bytes", 0) or 0),
        "plan_id": user.get("plan_id", ""),
        "node_groups": user.get("node_groups", ["default"]),
        "node_ids": user.get("node_ids", []),
        "effective_node_ids": effective_node_ids_for_user(user),
        "sub_token": sub_token,
        "subscription_url": base_sub,
        "raw_subscription_url": base_sub + "/raw" if base_sub else "",
        "mihomo_subscription_url": base_sub + "/mihomo" if base_sub else "",
        "vless_qr": f"/uqr/{urllib.parse.quote(username)}/vless",
        "hy2_qr": f"/uqr/{urllib.parse.quote(username)}/hy2",
    }


def list_users():
    data = user_store.load_users()
    return [user_summary(username, user) for username, user in sorted(data.get("users", {}).items())]


def user_links(username):
    user = user_store.get_user(username)
    if not user or not user_store.user_is_active(username, user):
        raise RuntimeError("user is inactive or expired")
    vless_links = links.build_vless_links_for_airport_user(username, user)
    result = {
        "username": username,
        "status": user_store.public_status(username, user),
        "quota": user_store.quota_text(user),
        "metrics": user_metrics(username, user),
        "subscription_url": app_urls.subscription_url(user.get("sub_token", "")),
        "vless": vless_links[0] if vless_links else "",
        "vless_links": vless_links,
        "vless_qrs": [
            f"/uqr/{urllib.parse.quote(username)}/vless/{urllib.parse.quote(node.get('id', ''))}"
            for node in node_catalog.nodes_for_user(user, kind="vless", include_disabled=False)
            if node_catalog.vless_uuid_for_user(user, node.get("id", ""))
        ],
        "hy2": links.build_hy2_link_for_airport_user(username, user),
        "vless_qr": f"/uqr/{urllib.parse.quote(username)}/vless",
        "hy2_qr": f"/uqr/{urllib.parse.quote(username)}/hy2",
    }
    token = user.get("sub_token", "")
    if token:
        result.update(
            {
                "raw_subscription_url": app_urls.subscription_url(token, "raw"),
                "mihomo_subscription_url": app_urls.subscription_url(token, "mihomo"),
                "subscription_qr": app_urls.subscription_qr_path(token),
            }
        )
    return result


def admin_links():
    user = admin_profile.get_admin_user()
    token = user.get("sub_token", "")
    base_sub = app_urls.subscription_url(token) if token else ""
    result = {
        "username": admin_profile.ADMIN_USERNAME,
        "subscription_url": base_sub,
        "raw_subscription_url": base_sub + "/raw" if base_sub else "",
        "mihomo_subscription_url": base_sub + "/mihomo" if base_sub else "",
        "vless_qr": "/qr/vless",
        "hy2_qr": "/qr/hy2",
        "subscription_qr": app_urls.subscription_qr_path(token) if token else "",
    }
    try:
        vless_links = links.build_vless_links_for_airport_user(admin_profile.ADMIN_USERNAME, user)
        result.update(
            {
                "vless": vless_links[0] if vless_links else "",
                "vless_links": vless_links,
                "vless_qrs": [
                    f"/qr/vless/{urllib.parse.quote(node.get('id', ''))}"
                    for node in node_catalog.nodes_for_user(user, kind="vless", include_disabled=False)
                    if node_catalog.vless_uuid_for_user(user, node.get("id", ""))
                ],
                "hy2": links.build_hy2_link_for_airport_user(admin_profile.ADMIN_USERNAME, user),
            }
        )
    except Exception as exc:
        result.update({"error": str(exc), "vless": "", "vless_links": [], "vless_qrs": [], "hy2": ""})
    return result


def dashboard(session):
    role = session.get("role") or session.get("r")
    username = session.get("u", "")
    payload = {"session": public_session(session)}
    if role == "admin":
        xray_status = xray_panel.current_status()
        xray_status["enabled"] = ":" in str(xray_status.get("proxy", ""))
        payload.update(
            {
                "xray": xray_status,
                "hy2": hy2_panel.hy2_status(),
                "links": admin_links(),
                "users": list_users(),
                "plans": plans_store.list_plans(),
                "orders": orders_store.list_orders(limit=80),
                "payment_methods": payments_store.list_methods(admin=True),
                "payments": payments_store.list_payments(admin=True, limit=80),
                "payment_rates": payments_store.load_rates(),
                "nodes": node_catalog.list_public_nodes(admin=True),
                "audit": audit_log.tail(80),
                "backups": backup_manager.list_backups(20),
                "registrations": registration_store.list_registrations(),
                "password_resets": registration_store.list_resets(),
                "subscription_access": subscription_guard.tail(120),
            }
        )
    else:
        user = user_store.get_user(username)
        payload["profile"] = user_metrics(username, user) if user else {}
        try:
            payload["links"] = user_links(username)
        except Exception as exc:
            payload["links"] = {"error": str(exc), "metrics": payload["profile"]}
        payload["orders"] = orders_store.list_orders(username=username, limit=30)
        payload["plans"] = plans_store.list_plans(include_disabled=False)
        payload["nodes"] = visible_nodes_for_user(user) if user else []
        payload["payment_methods"] = payments_store.list_methods(admin=False)
        payload["payments"] = payments_store.list_payments(username=username, admin=False, limit=30)
    return payload
