import cache_store
import admin_metrics_service
import dashboard_service
import public_settings
import user_store
from app_version import APP_VERSION
from api_common import ok, require_admin
from http_utils import api_error


USER_NAV = [
    {"id": "dashboard", "label": "首页", "icon": "⌂"},
    {"id": "plans", "label": "套餐", "icon": "▣"},
    {"id": "links", "label": "订阅", "icon": "↗"},
    {"id": "orders", "label": "订单", "icon": "≡"},
    {"id": "account", "label": "账号", "icon": "○"},
]


ADMIN_NAV = [
    {"id": "dashboard", "label": "仪表盘", "icon": "▦"},
    {"id": "users", "label": "用户管理", "icon": "◉"},
    {"id": "orders", "label": "订单管理", "icon": "≡"},
    {"id": "nodes", "label": "节点管理", "icon": "◇"},
    {"id": "tunnels", "label": "内网穿透", "icon": "⇄"},
    {"id": "settings", "label": "系统设置", "icon": "⚙"},
]


ADMIN_EXTENDED_NAV = [
    {"id": "plans", "label": "套餐管理", "icon": "□"},
    {"id": "requests", "label": "注册与找回", "icon": "＋"},
    {"id": "audit", "label": "审计日志", "icon": "◎"},
    {"id": "backups", "label": "备份", "icon": "⇣"},
    {"id": "hy2", "label": "Hysteria2", "icon": "H"},
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
        "version": APP_VERSION,
        "nav": ADMIN_NAV if role == "admin" else USER_NAV,
        "secondary_nav": ADMIN_EXTENDED_NAV if role == "admin" else [],
        "public_settings": public_settings.read(),
    }


def handle_get(clean, session):
    clean_path = clean.split("?", 1)[0]
    if clean_path == "/api/app-shell":
        return ok(**shell_payload(session))

    if clean_path == "/api/me":
        if not session:
            return api_error("not authenticated", 401)
        username = username_for(session)
        if role_for(session) == "admin":
            return ok(username=username, role="admin", metrics={}, subscription_url="")
        user = user_store.get_user(username)
        if not user:
            return api_error("user not found", 404)
        return ok(**dashboard_service.user_summary(username, user))

    if clean_path == "/api/admin/overview":
        if (err := require_admin(session)):
            return err
        payload = cache_store.app_cache.get(
            "dashboard",
            "admin",
            ttl=10,
            loader=lambda: dashboard_service.dashboard(session),
        )
        return ok(data=payload)

    if clean_path == "/api/admin/metrics/overview":
        if (err := require_admin(session)):
            return err
        return ok(metrics=admin_metrics_service.overview())

    if clean_path == "/api/admin/metrics/traffic":
        if (err := require_admin(session)):
            return err
        return ok(traffic=admin_metrics_service.traffic_series(admin_metrics_service.query_params(clean)))

    if clean_path == "/api/admin/metrics/users/top":
        if (err := require_admin(session)):
            return err
        return ok(**admin_metrics_service.top_users(admin_metrics_service.query_params(clean)))

    if clean_path == "/api/admin/metrics/nodes":
        if (err := require_admin(session)):
            return err
        return ok(**admin_metrics_service.nodes(admin_metrics_service.query_params(clean)))

    if clean_path == "/api/admin/metrics/plans":
        if (err := require_admin(session)):
            return err
        return ok(**admin_metrics_service.plans())

    if clean_path == "/api/cache/status":
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
