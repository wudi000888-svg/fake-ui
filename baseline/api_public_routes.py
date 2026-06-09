import audit_log
import auth_store
import registration_store
import security
from api_common import ok
from panel_config import SESSION_TTL


def handle_public_post(clean, data):
    if clean == "/api/register":
        item = registration_store.create_registration(
            data.get("username", ""),
            data.get("password", ""),
            data.get("email", ""),
            data.get("plan_id", ""),
            data.get("note", ""),
        )
        audit_log.write(data.get("username", ""), "registration.submit", data.get("username", ""), {"plan_id": data.get("plan_id", "")})
        return ok(registration=item)

    if clean == "/api/password-reset/request":
        item = registration_store.create_password_reset(data.get("username", ""))
        audit_log.write(data.get("username", ""), "password_reset.request", data.get("username", ""), {"token": item.get("token", "")[:10]})
        return ok(reset=item)

    if clean == "/api/login":
        username = data.get("username", "").strip()
        key = security.login_key_from_request(
            username,
            remote_ip=data.get("_request_remote_ip", ""),
            forwarded_for=data.get("_request_forwarded_for", ""),
        )
        if security.login_limited(key):
            audit_log.write(username or "anonymous", "auth.login_rate_limited")
            return 429, {"ok": False, "error": security.login_error_message()}
        role = auth_store.authenticate_user(username, data.get("password", ""))
        if not role:
            security.record_login_failure(key)
            audit_log.write(username or "anonymous", "auth.login_failed")
            return 401, {"ok": False, "error": "invalid username or password"}
        security.clear_login_failures(key)
        audit_log.write(username, "auth.login_success")
        token = auth_store.make_session(username, role)
        return ok(session={"username": username, "role": role}, token=token, ttl=SESSION_TTL)

    return None
