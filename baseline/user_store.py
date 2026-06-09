import secrets
import uuid
from datetime import datetime, timedelta, timezone

import store_facade
import node_catalog
from repositories.sqlite_users import SQLiteUsersRepository


def now_utc():
    return datetime.now(timezone.utc)


def parse_time(value):
    if not value:
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def make_expiry(days):
    return (now_utc() + timedelta(days=int(days))).isoformat()


def load_users():
    store_facade.ensure_sqlite()
    data = {"version": 2, "users": {u["username"]: u for u in SQLiteUsersRepository().list()}}
    if ensure_hy2_credentials(data):
        save_users(data)
    return data


def load_users_required():
    return load_users()


def save_users(data):
    store_facade.ensure_sqlite()
    repo = SQLiteUsersRepository()
    for username, user in (data or {}).get("users", {}).items():
        item = dict(user)
        item["username"] = username
        repo.upsert(item)
    return data


def delete_user(username):
    store_facade.ensure_sqlite()
    return SQLiteUsersRepository().delete(str(username or "").strip())


def remove_vless_node_uuid(node_id):
    node_id = str(node_id or "").strip()
    if not node_id:
        return 0
    data = load_users()
    changed = 0
    for user in data.setdefault("users", {}).values():
        mapping = user.get("vless_node_uuids")
        if isinstance(mapping, dict) and node_id in mapping:
            mapping.pop(node_id, None)
            changed += 1
    if changed:
        save_users(data)
    return changed


def ensure_hy2_credentials(data):
    changed = False
    users = data.setdefault("users", {})

    for username, u in users.items():
        if not u.get("vless_uuid"):
            u["vless_uuid"] = str(uuid.uuid4())
            changed = True
        mapping = u.setdefault("vless_node_uuids", {})
        for node in node_catalog.vless_nodes(include_disabled=True):
            node_id = node.get("id", "")
            if not node_id:
                continue
            if node_id == node_catalog.PRIMARY_VLESS_NODE_ID:
                if mapping.get(node_id) != u["vless_uuid"]:
                    mapping[node_id] = u["vless_uuid"]
                    changed = True
            elif not mapping.get(node_id):
                mapping[node_id] = str(uuid.uuid4())
                changed = True
        if not u.get("hy2_username"):
            u["hy2_username"] = username
            changed = True
        if not u.get("hy2_password"):
            u["hy2_password"] = secrets.token_urlsafe(18)
            changed = True
        u.setdefault("last_hy2_stats", {"tx": 0, "rx": 0})

    return changed


def user_is_active(username, user):
    if not user or not user.get("enabled", True):
        return False

    exp = parse_time(user.get("expires_at"))
    if exp is not None and exp <= now_utc():
        return False

    quota = int(user.get("quota_bytes", 0) or 0)
    used = int(user.get("used_bytes", 0) or 0)
    return not (quota > 0 and used >= quota)


def active_users():
    data = load_users_required()
    result = {}
    changed = ensure_hy2_credentials(data)
    t = now_utc()

    for username, u in data.get("users", {}).items():
        exp = parse_time(u.get("expires_at"))
        expired = exp is not None and exp <= t

        quota_bytes = int(u.get("quota_bytes", 0) or 0)
        used_bytes = int(u.get("used_bytes", 0) or 0)
        quota_exceeded = quota_bytes > 0 and used_bytes >= quota_bytes

        if u.get("expired") != bool(expired):
            u["expired"] = bool(expired)
            changed = True

        if u.get("quota_exceeded") != bool(quota_exceeded):
            u["quota_exceeded"] = bool(quota_exceeded)
            changed = True

        if u.get("enabled") and not expired and not quota_exceeded:
            result[username] = u

    if changed:
        save_users(data)

    return result


def get_user(username):
    data = load_users()
    return data.get("users", {}).get(username)


def find_user_by_token(token):
    data = load_users()
    for username, user in data.get("users", {}).items():
        if user.get("sub_token") == token:
            return username, user
    return None, None


def public_status(username, user):
    if not user:
        return "不存在"
    if not user.get("enabled", True):
        return "已禁用"

    exp = parse_time(user.get("expires_at"))
    if exp and exp <= now_utc():
        return "已过期"

    return "有效"


def traffic_gb_to_bytes(value):
    value = str(value or "").strip()
    if not value:
        return 0

    gb = float(value)
    if gb < 0:
        raise RuntimeError("流量额度不能小于 0。")

    return int(gb * 1024 * 1024 * 1024)


def bytes_to_gb_text(value):
    try:
        n = int(value or 0)
    except Exception:
        n = 0

    return f"{n / 1024 / 1024 / 1024:.2f} GB"


def quota_text(user):
    used = int(user.get("used_bytes", 0) or 0)
    quota = int(user.get("quota_bytes", 0) or 0)

    if quota <= 0:
        return f"{bytes_to_gb_text(used)} / 不限量"

    remain = max(0, quota - used)
    return f"{bytes_to_gb_text(used)} / {bytes_to_gb_text(quota)}，剩余 {bytes_to_gb_text(remain)}"


def quota_status_text(user):
    quota = int(user.get("quota_bytes", 0) or 0)
    used = int(user.get("used_bytes", 0) or 0)

    if quota > 0 and used >= quota:
        return "流量已用尽"

    return "流量正常"
