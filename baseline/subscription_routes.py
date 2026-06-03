import admin_profile
import app_urls
import links
import subscription_guard
import user_store
from qr_service import qr_png_for_link


def subscription_qr_png(path):
    clean = path.split("?", 1)[0].rstrip("/")
    parts = clean.strip("/").split("/")
    if len(parts) < 2:
        raise RuntimeError("missing token")

    token = parts[1]
    mode = parts[2].lower().strip() if len(parts) >= 3 else ""
    username, user = user_store.find_user_by_token(token)
    if not username:
        username, user = admin_profile.find_by_token(token)
    if not username or not user_store.user_is_active(username, user):
        raise RuntimeError("expired")

    if mode in ("raw", "uri", "plain"):
        url = app_urls.subscription_url(token, "raw")
    elif mode in ("mihomo", "clash", "clash-meta", "meta"):
        url = app_urls.subscription_url(token, "mihomo")
    else:
        url = app_urls.subscription_url(token)
    return qr_png_for_link(url)


def build_subscription_http_response(path, headers, fallback_ip=""):
    token = path.split("?", 1)[0].strip("/").split("/")[1]
    sub_ip = subscription_guard.client_ip(headers, fallback_ip)
    sub_user, _ = user_store.find_user_by_token(token)
    if not sub_user:
        sub_user, _ = admin_profile.find_by_token(token)

    if sub_user and subscription_guard.too_many_requests(sub_user, sub_ip):
        subscription_guard.log_access(sub_user, token, path, sub_ip, headers.get("User-Agent", ""), "rate_limited")
        return 429, "Subscription rate limited", {}, token

    body, response_headers = links.build_subscription_response_by_path(path)
    subscription_guard.log_access(sub_user or "", token, path, sub_ip, headers.get("User-Agent", ""), "ok")
    return 200, body, response_headers, token


def log_subscription_error(path, headers, fallback_ip="", token=""):
    try:
        subscription_guard.log_access("", token, path, fallback_ip, headers.get("User-Agent", ""), "error")
    except Exception:
        pass
