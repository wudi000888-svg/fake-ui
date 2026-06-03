import base64
import hashlib
import hmac
import json
import secrets
import time

from panel_config import AUTH_FILE, SESSION_TTL
from json_store import load_json, save_json
import user_store


def now():
    return int(time.time())


def b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def make_password_hash(password: str):
    salt = secrets.token_hex(16)
    iterations = 260000
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations)
    return {
        "alg": "pbkdf2_sha256",
        "salt": salt,
        "iter": iterations,
        "hash": dk.hex(),
    }


def verify_password(password: str, record):
    try:
        if "iter" in record:
            salt = record["salt"]
            iterations = int(record["iter"])
            expected = record["hash"]
            dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations).hex()
            return hmac.compare_digest(dk, expected)

        if "iterations" in record:
            salt = b64d(record["salt"])
            iterations = int(record["iterations"])
            expected = record["hash"]
            dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
            return hmac.compare_digest(b64e(dk), expected)
    except Exception:
        return False

    return False


def load_auth():
    if not AUTH_FILE.exists():
        raise RuntimeError("auth.json 不存在。")
    return load_json(AUTH_FILE, {})


def save_auth(auth):
    save_json(AUTH_FILE, auth)


def sign(payload_b64, secret):
    return hmac.new(secret.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()


def get_auth_users():
    auth = load_auth()
    users = auth.get("users", {})
    if not isinstance(users, dict) or not users:
        raise RuntimeError("auth.json 中没有 users。")
    return auth, users


def authenticate_user(username, password):
    auth, users = get_auth_users()
    rec = users.get(username)
    if rec and verify_password(password, rec.get("password", {})):
        return rec.get("role", "user")

    airport_user = user_store.get_user(username)
    if airport_user and user_store.user_is_active(username, airport_user):
        if verify_password(password, airport_user.get("panel_password", {})):
            return "user"

    return None


def make_session(username, role):
    auth = load_auth()
    payload = json.dumps(
        {"u": username, "r": role, "t": now(), "n": secrets.token_urlsafe(8)},
        separators=(",", ":"),
    )
    payload_b64 = b64e(payload.encode())
    sig = sign(payload_b64, auth["session_secret"])
    return f"{payload_b64}.{sig}"


def session_payload(token):
    try:
        payload_b64, sig = token.split(".", 1)
        auth = load_auth()
        expected = sign(payload_b64, auth["session_secret"])
        if not hmac.compare_digest(sig, expected):
            return None

        payload = json.loads(b64d(payload_b64).decode())
        if now() - int(payload.get("t", 0)) > SESSION_TTL:
            return None

        username = payload.get("u", "")
        role = payload.get("r", "")

        auth, auth_users = get_auth_users()
        if username in auth_users:
            real_role = auth_users[username].get("role", "user")
            if role != real_role:
                return None
            payload["role"] = real_role
            return payload

        airport_user = user_store.get_user(username)
        if airport_user and user_store.user_is_active(username, airport_user):
            if role == "user":
                payload["role"] = "user"
                return payload

        return None
    except Exception:
        return None
