import re
from datetime import datetime, timezone

from panel_config import NODE_CATALOG_FILE
from json_store import load_json, save_json
import node_display
import node_mutations


PRIMARY_VLESS_NODE_ID = "vless-main"
VLESS_OUTBOUND_TAG_PREFIX = node_mutations.VLESS_OUTBOUND_TAG_PREFIX
AUTO_VLESS_PREFIX = "vless-auto-"


def now_iso():
    return datetime.now(timezone.utc).isoformat()


DEFAULT_NODES = [
    {"id": PRIMARY_VLESS_NODE_ID, "name": "VLESS 直连", "kind": "vless", "group": "default", "region": "", "multiplier": 1.0, "status": "online", "enabled": True, "sort": 10, "outbound_mode": "direct"},
    {"id": "vless-proxy-1", "name": "VLESS 代理 1", "kind": "vless", "group": "default", "region": "", "multiplier": 1.0, "status": "online", "enabled": True, "sort": 11, "outbound_mode": "direct"},
    {"id": "vless-proxy-2", "name": "VLESS 代理 2", "kind": "vless", "group": "default", "region": "", "multiplier": 1.0, "status": "online", "enabled": True, "sort": 12, "outbound_mode": "direct"},
    {"id": "vless-proxy-3", "name": "VLESS 代理 3", "kind": "vless", "group": "default", "region": "", "multiplier": 1.0, "status": "online", "enabled": True, "sort": 13, "outbound_mode": "direct"},
    {"id": "hy2-main", "name": "Hysteria2", "kind": "hy2", "group": "default", "region": "", "multiplier": 1.0, "status": "online", "enabled": True, "sort": 20},
]
REQUIRED_DEFAULT_IDS = {PRIMARY_VLESS_NODE_ID, "hy2-main"}


def load_catalog():
    data = load_json(
        NODE_CATALOG_FILE,
        lambda: {"version": 1, "vless_defaults_initialized": True, "nodes": [dict(n) for n in DEFAULT_NODES]},
        create=True,
    )
    if ensure_default_nodes(data):
        save_catalog(data)
    return data


def ensure_default_nodes(data):
    changed = False
    nodes = data.setdefault("nodes", [])
    by_id = {str(n.get("id", "")): n for n in nodes}
    for default in DEFAULT_NODES:
        node_id = default["id"]
        if data.get("vless_defaults_initialized") and node_id not in REQUIRED_DEFAULT_IDS:
            continue
        if node_id not in by_id:
            item = dict(default)
            item["created_at"] = now_iso()
            nodes.append(item)
            by_id[node_id] = item
            changed = True
        else:
            node = by_id[node_id]
            for key, value in default.items():
                if key not in node or node.get(key) in (None, ""):
                    node[key] = value
                    changed = True
    if not data.get("vless_defaults_initialized"):
        data["vless_defaults_initialized"] = True
        changed = True
    if normalize_default_vless_sort(data):
        changed = True
    return changed


def default_vless_nodes_from_store(store, include_disabled=True):
    result = []
    for node in store.get("nodes", []):
        if node.get("kind") != "vless":
            continue
        if node.get("group", "default") != "default":
            continue
        if not include_disabled and not node.get("enabled", True):
            continue
        result.append(node)
    return result


def is_managed_default_vless(node):
    node_id = str(node.get("id", ""))
    return (
        node.get("kind") == "vless"
        and node.get("group", "default") == "default"
        and (node_id == PRIMARY_VLESS_NODE_ID or node_id.startswith("vless-proxy-") or node_id.startswith(AUTO_VLESS_PREFIX))
    )


def default_vless_index(node):
    node_id = str(node.get("id", ""))
    if node_id == PRIMARY_VLESS_NODE_ID:
        return 1
    for prefix in ("vless-proxy-", AUTO_VLESS_PREFIX):
        if node_id.startswith(prefix):
            m = re.search(r"(\d+)$", node_id)
            if m:
                return int(m.group(1))
    return 0


def normalize_default_vless_sort(store):
    changed = False
    nodes = [node for node in default_vless_nodes_from_store(store, include_disabled=True) if is_managed_default_vless(node)]
    nodes.sort(key=lambda n: (int(n.get("sort", 100) or 100), default_vless_index(n), str(n.get("id", ""))))
    for idx, node in enumerate(nodes, start=1):
        wanted = 9 + idx
        if int(node.get("sort", 0) or 0) != wanted:
            node["sort"] = wanted
            node["updated_at"] = now_iso()
            changed = True
    return changed


def save_catalog(data):
    save_json(NODE_CATALOG_FILE, data)


def list_nodes(include_disabled=True):
    nodes = load_catalog().get("nodes", [])
    if not include_disabled:
        nodes = [n for n in nodes if n.get("enabled", True)]
    return sorted(nodes, key=lambda n: (n.get("group", ""), int(n.get("sort", 0) or 0), n.get("id", "")))


def public_node(node, admin=False):
    return node_display.public_node(node, admin=admin, outbound_mode_fn=outbound_mode)


def list_public_nodes(include_disabled=True, admin=False):
    return [public_node(n, admin=admin) for n in list_nodes(include_disabled=include_disabled)]


def get_node(node_id):
    node_id = str(node_id or "").strip()
    for node in list_nodes(include_disabled=True):
        if node.get("id") == node_id:
            return dict(node)
    raise RuntimeError("node not found")


def nodes_for_user(user, kind=None, include_disabled=False):
    exact_ids = (user or {}).get("node_ids")
    if isinstance(exact_ids, str):
        exact_ids = [item.strip() for item in exact_ids.split(",") if item.strip()]
    elif exact_ids:
        exact_ids = [str(item).strip() for item in exact_ids if str(item).strip()]
    else:
        exact_ids = []
    exact_set = set(exact_ids)

    groups = (user or {}).get("node_groups") or ["default"]
    if isinstance(groups, str):
        groups = [groups]
    result = []
    for node in list_nodes(include_disabled=include_disabled):
        if kind and node.get("kind") != kind:
            continue
        if exact_set:
            if node.get("id") in exact_set:
                result.append(node)
            continue
        if node.get("group", "default") in groups:
            result.append(node)
    return result


def vless_nodes(include_disabled=False):
    return [n for n in list_nodes(include_disabled=include_disabled) if n.get("kind") == "vless"]


def allowed_kinds_for_user(user):
    allowed = []
    for node in nodes_for_user(user, include_disabled=False):
        if node.get("kind") not in allowed:
            allowed.append(node.get("kind"))
    if allowed:
        return allowed
    if (user or {}).get("node_ids"):
        return []
    return ["vless", "hy2"]


def outbound_mode(node):
    return node_mutations.outbound_mode(node)


def vless_node_email(username, node_id):
    return node_mutations.vless_node_email(username, node_id, PRIMARY_VLESS_NODE_ID)


def vless_uuid_for_user(user, node_id):
    return node_mutations.vless_uuid_for_user(user, node_id, PRIMARY_VLESS_NODE_ID)


def safe_outbound_tag(node_id):
    return node_mutations.safe_outbound_tag(node_id)


def display_name_for_node(node, fallback):
    return node_display.display_name_for_node(node, fallback)


def upsert_node(data):
    node_id = (data.get("id") or data.get("name") or "").strip()
    if not node_id:
        raise RuntimeError("node id is required")
    store = load_catalog()
    nodes = store.setdefault("nodes", [])
    existing = next((item for item in nodes if item.get("id") == node_id), {})
    kind = (data.get("kind") or existing.get("kind") or "vless").strip()
    mode = (data.get("outbound_mode") if "outbound_mode" in data else existing.get("outbound_mode", "direct"))
    mode = str(mode or "direct").strip().lower()
    if mode not in ("direct", "http", "socks5"):
        raise RuntimeError("outbound mode must be direct, http or socks5")
    proxy_addr = str(data.get("proxy_addr", existing.get("proxy_addr", "")) or "").strip()
    proxy_port = str(data.get("proxy_port", existing.get("proxy_port", "")) or "").strip()
    proxy_user = str(data.get("proxy_user", existing.get("proxy_user", "")) or "").strip()
    password_provided = "proxy_password" in data
    proxy_password = str(data.get("proxy_password", existing.get("proxy_password", "")) or "").strip()
    if password_provided and not proxy_password and proxy_user and proxy_user == existing.get("proxy_user", "") and existing.get("proxy_password"):
        proxy_password = existing.get("proxy_password", "")
    if not proxy_user:
        proxy_password = ""
    if kind == "vless" and mode != "direct":
        if not proxy_addr or not proxy_port:
            raise RuntimeError("proxy address and port are required for proxy mode")
        int(proxy_port)
    node = {
        "id": node_id,
        "name": (data.get("name") or existing.get("name") or node_id).strip(),
        "kind": kind,
        "group": (data.get("group") or existing.get("group") or "default").strip(),
        "region": (data.get("region") or existing.get("region") or "").strip(),
        "multiplier": float(data.get("multiplier", existing.get("multiplier", 1)) or 1),
        "status": (data.get("status") or existing.get("status") or "online").strip(),
        "latency_ms": int(data.get("latency_ms", existing.get("latency_ms", 0)) or 0),
        "enabled": bool(data.get("enabled", existing.get("enabled", True))),
        "sort": int(data.get("sort", existing.get("sort", 100)) or 100),
        "outbound_mode": mode if kind == "vless" else "direct",
        "proxy_addr": proxy_addr if kind == "vless" else "",
        "proxy_port": proxy_port if kind == "vless" else "",
        "proxy_user": proxy_user if kind == "vless" else "",
        "proxy_password": proxy_password if kind == "vless" else "",
        "proxy_test_ip": str(data.get("proxy_test_ip", existing.get("proxy_test_ip", "")) or "").strip(),
        "exit_ip": str(data.get("exit_ip", existing.get("exit_ip", "")) or "").strip(),
        "country": str(data.get("country", existing.get("country", "")) or "").strip(),
        "country_code": str(data.get("country_code", existing.get("country_code", "")) or "").strip().upper(),
        "city": str(data.get("city", existing.get("city", "")) or "").strip(),
        "updated_at": now_iso(),
    }
    if node["kind"] not in ("vless", "hy2"):
        raise RuntimeError("node kind must be vless or hy2")
    for idx, item in enumerate(nodes):
        if item.get("id") == node_id:
            merged = {**item, **node}
            nodes[idx] = merged
            node = merged
            break
    else:
        node["created_at"] = now_iso()
        nodes.append(node)
    normalize_default_vless_sort(store)
    save_catalog(store)
    return node


def next_default_vless_number(store=None):
    store = store or load_catalog()
    max_num = 0
    for node in default_vless_nodes_from_store(store, include_disabled=True):
        node_id = str(node.get("id", ""))
        if node_id == PRIMARY_VLESS_NODE_ID or node_id.startswith("vless-proxy-") or node_id.startswith(AUTO_VLESS_PREFIX):
            max_num = max(max_num, default_vless_index(node))
    active_count = len(default_vless_nodes_from_store(store, include_disabled=False))
    return max(max_num + 1, active_count + 1)


def create_default_vless_node():
    store = load_catalog()
    nodes = store.setdefault("nodes", [])
    number = next_default_vless_number(store)
    existing_ids = {str(n.get("id", "")) for n in nodes}
    node_id = f"{AUTO_VLESS_PREFIX}{number}"
    while node_id in existing_ids:
        number += 1
        node_id = f"{AUTO_VLESS_PREFIX}{number}"
    node = {
        "id": node_id,
        "name": f"VLESS 直连 {number}",
        "kind": "vless",
        "group": "default",
        "region": "",
        "multiplier": 1.0,
        "status": "online",
        "enabled": True,
        "sort": 100,
        "outbound_mode": "direct",
        "proxy_addr": "",
        "proxy_port": "",
        "proxy_user": "",
        "proxy_password": "",
        "proxy_test_ip": "",
        "exit_ip": "",
        "country": "",
        "country_code": "",
        "city": "",
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    nodes.append(node)
    normalize_default_vless_sort(store)
    save_catalog(store)
    return node


def delete_node(node_id):
    node_id = str(node_id or "").strip()
    if not node_id:
        raise RuntimeError("node id is required")
    if node_id == PRIMARY_VLESS_NODE_ID:
        raise RuntimeError("主 VLESS 节点不能删除，可以停用新增节点。")
    store = load_catalog()
    nodes = store.setdefault("nodes", [])
    for idx, node in enumerate(nodes):
        if node.get("id") == node_id:
            if node.get("kind") != "vless":
                raise RuntimeError("这里只允许删除 VLESS 节点，H2 不会被改动。")
            removed = nodes.pop(idx)
            normalize_default_vless_sort(store)
            save_catalog(store)
            return removed
    raise RuntimeError("node not found")


def display_name(kind, fallback):
    candidates = [n for n in list_nodes(include_disabled=False) if n.get("kind") == kind]
    if not candidates:
        return fallback
    return display_name_for_node(candidates[0], fallback)


def set_node_enabled(node_id, enabled):
    store = load_catalog()
    for node in store.get("nodes", []):
        if node.get("id") == node_id:
            node["enabled"] = bool(enabled)
            node["updated_at"] = now_iso()
            normalize_default_vless_sort(store)
            save_catalog(store)
            return node
    raise RuntimeError("node not found")
