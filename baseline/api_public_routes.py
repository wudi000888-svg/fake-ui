import audit_log
import auth_store
import operations_service as ops
import password_reset_service
import registration_store
import security
import user_admin
from api_common import ok
from panel_config import SESSION_TTL
from http_utils import api_error


def handle_public_post(clean, data):
    if clean == "/api/register":
        if not ops.get_public_settings().get("registration_enabled"):
            return api_error("registration is disabled", 403)
        item = registration_store.build_registration_item(
            data.get("username", ""),
            data.get("password", ""),
            data.get("email", ""),
            data.get("plan_id", ""),
            data.get("note", ""),
        )
        result = user_admin.create_self_registered_user(
            item.get("username", ""),
            item.get("password_hash"),
            email=item.get("email", ""),
            note=item.get("note", ""),
        )
        audit_log.write(item.get("username", ""), "registration.self_register", item.get("username", ""))
        return ok(
            message="registration complete; please log in",
            registration={k: v for k, v in item.items() if k not in {"password", "password_hash"}},
            result=result,
        )

    if clean == "/api/password-reset/request":
        item = registration_store.create_password_reset(data.get("username", ""))
        audit_log.write(data.get("username", ""), "password_reset.request", data.get("username", ""), {"token": item.get("token", "")[:10]})
        return ok(reset=item)

    if clean == "/api/password-reset/send-code":
        try:
            return ok(**password_reset_service.send_code(data.get("username") or data.get("email") or data.get("identifier", "")))
        except PermissionError as exc:
            return api_error(str(exc), 403)
        except RuntimeError as exc:
            return api_error(str(exc), 400)

    if clean == "/api/password-reset/confirm":
        try:
            return ok(
                **password_reset_service.confirm(
                    data.get("username") or data.get("email") or data.get("identifier", ""),
                    data.get("code", ""),
                    data.get("new_password", ""),
                )
            )
        except PermissionError as exc:
            return api_error(str(exc), 403)
        except RuntimeError as exc:
            return api_error(str(exc), 400)

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
