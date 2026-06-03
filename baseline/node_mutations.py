import re

VLESS_OUTBOUND_TAG_PREFIX = "panel-vless-"


def outbound_mode(node):
    mode = str((node or {}).get("outbound_mode") or "direct").strip().lower()
    if mode not in ("direct", "http", "socks5"):
        return "direct"
    return mode


def vless_node_email(username, node_id, primary_node_id="vless-main"):
    if node_id == primary_node_id:
        return f"panel-user:{username}"
    return f"panel-user:{username}:{node_id}"


def vless_uuid_for_user(user, node_id, primary_node_id="vless-main"):
    mapping = (user or {}).get("vless_node_uuids") or {}
    if node_id in mapping:
        return mapping[node_id]
    if node_id == primary_node_id:
        return (user or {}).get("vless_uuid", "")
    return ""


def safe_outbound_tag(node_id):
    clean = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(node_id)).strip("-")
    return VLESS_OUTBOUND_TAG_PREFIX + (clean or "node")
