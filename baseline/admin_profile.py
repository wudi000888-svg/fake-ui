import secrets
import uuid
from datetime import timedelta

import node_catalog
from panel_config import ADMIN_PROFILE_FILE
from json_store import load_json, save_json
import user_store


ADMIN_USERNAME = "admin"
ADMIN_HY2_USERNAME = "panel-admin"


def load_profile():
    data = load_json(ADMIN_PROFILE_FILE, {"version": 1, "user": {}})
    if ensure_profile(data):
        save_profile(data)
    return data


def save_profile(data):
    save_json(ADMIN_PROFILE_FILE, data)


def ensure_profile(data):
    changed = False
    user = data.setdefault("user", {})
    user["enabled"] = True
    user["role"] = "admin"
    user["node_groups"] = ["default"]
    user["quota_bytes"] = 0
    user["used_bytes"] = 0
    if not user.get("expires_at"):
        user["expires_at"] = (user_store.now_utc() + timedelta(days=3650)).isoformat()
        changed = True
    if not user.get("sub_token"):
        user["sub_token"] = secrets.token_hex(24)
        changed = True
    if not user.get("vless_uuid"):
        user["vless_uuid"] = str(uuid.uuid4())
        changed = True
    mapping = user.setdefault("vless_node_uuids", {})
    for node in node_catalog.vless_nodes(include_disabled=True):
        node_id = node.get("id", "")
        if not node_id:
            continue
        if node_id == node_catalog.PRIMARY_VLESS_NODE_ID:
            if mapping.get(node_id) != user["vless_uuid"]:
                mapping[node_id] = user["vless_uuid"]
                changed = True
        elif not mapping.get(node_id):
            mapping[node_id] = str(uuid.uuid4())
            changed = True
    existing_ids = {node.get("id", "") for node in node_catalog.vless_nodes(include_disabled=True)}
    for node_id in list(mapping.keys()):
        if node_id not in existing_ids:
            mapping.pop(node_id, None)
            changed = True
    if not user.get("hy2_username") or user.get("hy2_username") == ADMIN_USERNAME:
        user["hy2_username"] = ADMIN_HY2_USERNAME
        changed = True
    if not user.get("hy2_password"):
        user["hy2_password"] = secrets.token_urlsafe(18)
        changed = True
    user.setdefault("last_hy2_stats", {"tx": 0, "rx": 0})
    return changed


def get_admin_user():
    return load_profile().get("user", {})


def find_by_token(token):
    user = get_admin_user()
    if user.get("sub_token") == token:
        return ADMIN_USERNAME, user
    return None, None


def remove_vless_node_uuid(node_id):
    data = load_profile()
    mapping = data.setdefault("user", {}).setdefault("vless_node_uuids", {})
    if node_id in mapping:
        mapping.pop(node_id, None)
        save_profile(data)
