import hashlib
import hmac
import secrets
from datetime import timedelta

import audit_log
import auth_store
import email_service
import operations_service as ops
import registration_store
import user_store


MAX_ATTEMPTS = 5
CODE_TTL_MINUTES = 10


def generate_code():
    return f"{secrets.randbelow(1000000):06d}"


def hash_code(code):
    return hashlib.sha256(str(code or "").encode()).hexdigest()


def _find_user(identifier):
    identifier = str(identifier or "").strip()
    if not identifier:
        raise RuntimeError("username or email is required")
    users = user_store.load_users().get("users", {})
    if identifier in users:
        return identifier, users[identifier]
    matches = [(username, user) for username, user in users.items() if str(user.get("email", "")).lower() == identifier.lower()]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise RuntimeError("email matches multiple users")
    return "", None


def send_code(identifier):
    if not ops.get_public_settings().get("password_reset_enabled"):
        raise PermissionError("password reset is disabled")

    username, user = _find_user(identifier)
    if not username or not user or not user.get("email"):
        return {"message": "verification code sent"}

    code = generate_code()
    token = secrets.token_hex(24)
    item = {
        "token": token,
        "username": username,
        "email": user.get("email", ""),
        "status": "pending",
        "code_hash": hash_code(code),
        "attempts": 0,
        "created_at": registration_store.now_iso(),
        "expires_at": (registration_store.now_utc() + timedelta(minutes=CODE_TTL_MINUTES)).isoformat(),
    }
    registration_store.save_password_reset(item)
    email_service.send_verification_code(user.get("email", ""), code)
    audit_log.write(username, "password_reset.code_sent", username)
    return {"message": "verification code sent"}


def confirm(identifier, code, new_password):
    if not ops.get_public_settings().get("password_reset_enabled"):
        raise PermissionError("password reset is disabled")
    if len(new_password or "") < 8:
        raise RuntimeError("new password must be at least 8 characters")

    username, user = _find_user(identifier)
    if not username or not user:
        raise RuntimeError("invalid verification code")

    pending = [
        item for item in registration_store.list_resets("pending")
        if item.get("username") == username and item.get("email") == user.get("email", "")
    ]
    if not pending:
        raise RuntimeError("invalid verification code")
    item = sorted(pending, key=lambda i: i.get("created_at", ""), reverse=True)[0]

    exp = user_store.parse_time(item.get("expires_at"))
    if exp and exp <= registration_store.now_utc():
        registration_store.update_reset(item.get("token", ""), status="expired")
        raise RuntimeError("verification code expired")
    if int(item.get("attempts", 0) or 0) >= MAX_ATTEMPTS:
        raise RuntimeError("too many verification attempts")

    if not hmac.compare_digest(str(item.get("code_hash", "")), hash_code(code)):
        attempts = int(item.get("attempts", 0) or 0) + 1
        updates = {"attempts": attempts}
        if attempts >= MAX_ATTEMPTS:
            updates["status"] = "locked"
        registration_store.update_reset(item.get("token", ""), **updates)
        raise RuntimeError("invalid verification code")

    data = user_store.load_users()
    data["users"][username]["panel_password"] = auth_store.make_password_hash(new_password)
    user_store.save_users(data)
    registration_store.update_reset(item.get("token", ""), status="consumed")
    audit_log.write(username, "password_reset.confirm", username)
    return {"message": "password reset complete"}
