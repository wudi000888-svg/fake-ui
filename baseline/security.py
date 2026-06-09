import secrets
import time

from http_utils import api_error
from panel_config import SESSION_TTL


_LOGIN_ATTEMPTS = {}
LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_MAX_ATTEMPTS = 8
CSRF_HEADER = "X-CSRF-Token"


def security_headers(content_type=""):
    headers = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "same-origin",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    }
    if "text/html" in str(content_type):
        headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
    return headers


def session_cookie(token, max_age=SESSION_TTL):
    value = f"panel_session={token}; Path=/; HttpOnly; Secure; SameSite=Lax"
    if max_age is not None:
        value += f"; Max-Age={int(max_age)}"
    return value


def clear_session_cookie():
    return session_cookie("", max_age=0)


def csrf_cookie(token, max_age=SESSION_TTL):
    return f"panel_csrf={token}; Path=/; Secure; SameSite=Lax; Max-Age={int(max_age)}"


def csrf_token_for_session(session):
    if not session:
        return ""
    token = session.get("csrf")
    if not token:
        token = secrets.token_urlsafe(24)
        session["csrf"] = token
    return token


def login_key(handler, username):
    forwarded = handler.headers.get("X-Forwarded-For", "")
    ip = forwarded.split(",", 1)[0].strip() or getattr(handler, "client_address", [""])[0]
    return login_key_from_request(username, remote_ip=getattr(handler, "client_address", [""])[0], forwarded_for=forwarded)


def login_key_from_request(username, remote_ip="", forwarded_for=""):
    ip = str(forwarded_for or "").split(",", 1)[0].strip() or str(remote_ip or "").strip()
    return f"{ip}:{str(username or '').lower()}"


def login_error_message():
    return "too many login attempts; please try again later"


def login_limited(key, now=None):
    now = int(now or time.time())
    attempts = [ts for ts in _LOGIN_ATTEMPTS.get(key, []) if now - ts < LOGIN_WINDOW_SECONDS]
    _LOGIN_ATTEMPTS[key] = attempts
    return len(attempts) >= LOGIN_MAX_ATTEMPTS


def record_login_failure(key, now=None):
    now = int(now or time.time())
    attempts = [ts for ts in _LOGIN_ATTEMPTS.get(key, []) if now - ts < LOGIN_WINDOW_SECONDS]
    attempts.append(now)
    _LOGIN_ATTEMPTS[key] = attempts


def clear_login_failures(key):
    _LOGIN_ATTEMPTS.pop(key, None)


def csrf_error_for(handler, session):
    if not session:
        return None
    role = session.get("role") or session.get("r")
    if not role:
        return None
    expected = session.get("csrf", "")
    supplied = handler.headers.get(CSRF_HEADER, "")
    if not expected or not secrets.compare_digest(str(expected), str(supplied)):
        return api_error("csrf validation failed", 403)
    return None
