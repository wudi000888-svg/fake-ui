import cache_store
import dashboard_service
import user_store
from api_common import ok, require_admin
from http_utils import api_error


USER_NAV = [
    {"id": "dashboard", "label": "首页"},
    {"id": "plans", "label": "套餐"},
    {"id": "links", "label": "订阅"},
    {"id": "orders", "label": "订单"},
    {"id": "account", "label": "账号"},
]


ADMIN_NAV = [
    {"id": "dashboard", "label": "概览"},
    {"id": "users", "label": "用户"},
    {"id": "orders", "label": "订单"},
    {"id": "nodes", "label": "节点"},
    {"id": "settings", "label": "设置"},
]


ADMIN_EXTENDED_NAV = [
    {"id": "plans", "label": "套餐"},
    {"id": "requests", "label": "申请"},
    {"id": "audit", "label": "审计"},
    {"id": "backups", "label": "备份"},
    {"id": "hy2", "label": "Hysteria2"},
]


def role_for(session):
    return (session or {}).get("role") or (session or {}).get("r") or "user"


def username_for(session):
    return (session or {}).get("u", "")


def shell_payload(session):
    role = role_for(session)
    return {
        "role": role,
        "username": username_for(session),
        "version": "2.0.0",
        "nav": ADMIN_NAV if role == "admin" else USER_NAV,
        "secondary_nav": ADMIN_EXTENDED_NAV if role == "admin" else [],
    }


def handle_get(clean, session):
    if clean == "/api/app-shell":
        return ok(**shell_payload(session))

    if clean == "/api/me":
        if not session:
            return api_error("not authenticated", 401)
        username = username_for(session)
        if role_for(session) == "admin":
            return ok(username=username, role="admin", metrics={}, subscription_url="")
        user = user_store.get_user(username)
        if not user:
            return api_error("user not found", 404)
        return ok(**dashboard_service.user_summary(username, user))

    if clean == "/api/admin/overview":
        if (err := require_admin(session)):
            return err
        payload = cache_store.app_cache.get(
            "dashboard",
            "admin",
            ttl=10,
            loader=lambda: dashboard_service.dashboard(session),
        )
        return ok(data=payload)

    if clean == "/api/cache/status":
        if (err := require_admin(session)):
            return err
        return ok(cache=cache_store.app_cache.stats())

    return None


def handle_post(clean, data, session):
    if clean == "/api/cache/clear":
        if (err := require_admin(session)):
            return err
        namespace = (data or {}).get("namespace")
        cache_store.app_cache.invalidate(namespace)
        return ok(cache=cache_store.app_cache.stats())
    return None
