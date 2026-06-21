import re
import uuid
from datetime import datetime, timezone

import store_facade
from repositories.sqlite_settings import SQLiteSettingsRepository


SETTINGS_KEY = "tunnel_catalog"
DEFAULT_FLOW = "xtls-rprx-vision"
DEFAULT_REALITY_SNI = "www.cloudflare.com"
DEFAULT_PORTAL_START = 18081
KIND_PUBLIC_HTTPS = "public_https"
KIND_PRIVATE_TCP = "private_tcp"
KINDS = {KIND_PUBLIC_HTTPS, KIND_PRIVATE_TCP}
BRIDGE_MODE_DEDICATED = "dedicated"
BRIDGE_MODE_SHARED = "shared"
BRIDGE_MODES = {BRIDGE_MODE_DEDICATED, BRIDGE_MODE_SHARED}
BRIDGE_PLATFORM_MACOS = "macos"
BRIDGE_PLATFORM_LINUX = "linux"
BRIDGE_PLATFORM_WINDOWS = "windows"
BRIDGE_PLATFORMS = {BRIDGE_PLATFORM_MACOS, BRIDGE_PLATFORM_LINUX, BRIDGE_PLATFORM_WINDOWS}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def clean_id(value):
    node_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(value or "").strip()).strip("-")
    if not node_id:
        raise RuntimeError("tunnel id is required")
    return node_id


def clean_domain(value):
    domain = str(value or "").strip().lower().rstrip(".")
    if not domain:
        return ""
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+", domain):
        raise RuntimeError("public domain is invalid")
    return domain


def id_from_domain(domain):
    return clean_id(domain.replace(".", "-"))


def clean_flow(value):
    return str(value or DEFAULT_FLOW).strip() or DEFAULT_FLOW


def clean_kind(value):
    kind = str(value or KIND_PUBLIC_HTTPS).strip()
    if kind not in KINDS:
        raise RuntimeError("tunnel kind is invalid")
    return kind


def clean_bridge_mode(value):
    mode = str(value or BRIDGE_MODE_DEDICATED).strip()
    if mode not in BRIDGE_MODES:
        raise RuntimeError("bridge mode is invalid")
    return mode


def clean_bridge_platform(value):
    platform = str(value or BRIDGE_PLATFORM_MACOS).strip().lower()
    if platform not in BRIDGE_PLATFORMS:
        raise RuntimeError("bridge platform is invalid")
    return platform


def used_values(tunnels, exclude_id=""):
    values = {
        "ids": set(),
        "domains": set(),
        "ports": set(),
        "uuids": set(),
        "emails": set(),
        "portal_tags": set(),
        "reverse_tags": set(),
    }
    for item in tunnels or []:
        if str(item.get("id", "")) == exclude_id:
            continue
        if item.get("id"):
            values["ids"].add(str(item.get("id")))
        if item.get("public_domain"):
            values["domains"].add(str(item.get("public_domain")).lower())
        if item.get("portal_port"):
            values["ports"].add(int(item.get("portal_port")))
        if item.get("client_id"):
            values["uuids"].add(str(item.get("client_id")))
        node_id = str(item.get("id", ""))
        if node_id:
            values["emails"].add(str(item.get("email") or f"tunnel:{node_id}"))
            values["portal_tags"].add(str(item.get("portal_tag") or f"tunnel-portal-{node_id}"))
            values["reverse_tags"].add(str(item.get("reverse_tag") or f"tunnel-reverse-{node_id}"))
    return values


def next_portal_port(tunnels):
    used = used_values(tunnels)["ports"]
    port = DEFAULT_PORTAL_START
    while port in used:
        port += 1
    return port


def load_catalog():
    store_facade.ensure_sqlite()
    data = SQLiteSettingsRepository().get(SETTINGS_KEY, {"version": 1, "tunnels": []})
    data.setdefault("version", 1)
    data.setdefault("tunnels", [])
    return data


def save_catalog(data):
    store_facade.ensure_sqlite()
    payload = {"version": 1, "tunnels": list((data or {}).get("tunnels", []))}
    SQLiteSettingsRepository().set(SETTINGS_KEY, payload)
    return payload


def normalize_tunnel(data, existing=None, existing_tunnels=None):
    existing = existing or {}
    existing_tunnels = existing_tunnels or []
    public_domain = clean_domain(data.get("public_domain", existing.get("public_domain", "")))
    kind_default = KIND_PUBLIC_HTTPS if public_domain else KIND_PRIVATE_TCP
    kind = clean_kind(data.get("kind", existing.get("kind", kind_default)))
    node_id_seed = (
        data.get("id")
        or existing.get("id")
        or (id_from_domain(public_domain) if public_domain else "")
        or data.get("name")
        or existing.get("name")
    )
    node_id = clean_id(node_id_seed)
    client_id = str(data.get("client_id", existing.get("client_id", "")) or "").strip()
    if not client_id:
        client_id = str(uuid.uuid4())
    values = used_values(existing_tunnels, exclude_id=node_id)
    if node_id in values["ids"]:
        raise RuntimeError("tunnel id is duplicated")
    if public_domain and public_domain in values["domains"]:
        raise RuntimeError("public domain is duplicated")
    portal_port = int(data.get("portal_port", existing.get("portal_port", 0)) or 0)
    if not portal_port:
        portal_port = next_portal_port(existing_tunnels)
    if portal_port in values["ports"]:
        raise RuntimeError("portal port is duplicated")
    if client_id in values["uuids"]:
        raise RuntimeError("tunnel UUID is duplicated")
    bridge_mode = clean_bridge_mode(data.get("bridge_mode", existing.get("bridge_mode", BRIDGE_MODE_DEDICATED)))
    bridge_id = clean_id(data.get("bridge_id", existing.get("bridge_id", node_id)) or node_id)
    bridge_platform = clean_bridge_platform(data.get("bridge_platform", existing.get("bridge_platform", BRIDGE_PLATFORM_MACOS)))
    email = f"tunnel:{node_id}"
    portal_tag = f"tunnel-portal-{node_id}"
    reverse_tag = f"tunnel-reverse-{node_id}"
    if email in values["emails"] or portal_tag in values["portal_tags"] or reverse_tag in values["reverse_tags"]:
        raise RuntimeError("tunnel tag is duplicated")
    item = {
        "id": node_id,
        "kind": kind,
        "name": str(data.get("name", existing.get("name", node_id)) or node_id).strip(),
        "enabled": bool(data.get("enabled", existing.get("enabled", True))),
        "mode": str(data.get("mode", existing.get("mode", "port")) or "port").strip(),
        "public_domain": public_domain,
        "portal_port": portal_port,
        "target_host": str(data.get("target_host", existing.get("target_host", "127.0.0.1")) or "127.0.0.1").strip(),
        "target_port": int(data.get("target_port", existing.get("target_port", 0)) or 0),
        "client_id": client_id,
        "email": email,
        "portal_tag": portal_tag,
        "reverse_tag": reverse_tag,
        "bridge_mode": bridge_mode,
        "bridge_id": bridge_id,
        "bridge_platform": bridge_platform,
        "flow": clean_flow(data.get("flow", existing.get("flow", DEFAULT_FLOW))),
        "reality_sni": str(data.get("reality_sni", existing.get("reality_sni", DEFAULT_REALITY_SNI)) or DEFAULT_REALITY_SNI).strip(),
        "server_address": str(data.get("server_address", existing.get("server_address", public_domain)) or public_domain).strip(),
        "server_port": int(data.get("server_port", existing.get("server_port", 443)) or 443),
        "internal_port": int(data.get("internal_port", existing.get("internal_port", 9443)) or 9443),
        "public_key": str(data.get("public_key", existing.get("public_key", "")) or "").strip(),
        "private_key": str(data.get("private_key", existing.get("private_key", "")) or "").strip(),
        "short_id": str(data.get("short_id", existing.get("short_id", "")) or "").strip(),
        "updated_at": now_iso(),
    }
    if item["mode"] != "port":
        raise RuntimeError("only port tunnel mode is supported")
    if item["kind"] == KIND_PUBLIC_HTTPS and not item["public_domain"]:
        raise RuntimeError("public domain is required")
    if not item["portal_port"]:
        raise RuntimeError("portal port is required")
    if not item["target_host"] or not item["target_port"]:
        raise RuntimeError("target host and port are required")
    if not item["server_address"]:
        raise RuntimeError("server address is required")
    if "created_at" in existing:
        item["created_at"] = existing["created_at"]
    else:
        item["created_at"] = now_iso()
    return item


def upsert_tunnel(data):
    store = load_catalog()
    tunnels = store.setdefault("tunnels", [])
    public_domain = clean_domain(data.get("public_domain", "")) if data.get("public_domain") else ""
    node_id = clean_id(data.get("id") or (id_from_domain(public_domain) if public_domain else "") or data.get("name"))
    for idx, item in enumerate(tunnels):
        if item.get("id") == node_id:
            tunnel = normalize_tunnel(data, item, existing_tunnels=tunnels)
            tunnels[idx] = tunnel
            save_catalog(store)
            return tunnel
    tunnel = normalize_tunnel(data, existing_tunnels=tunnels)
    tunnels.append(tunnel)
    save_catalog(store)
    return tunnel


def list_tunnels(include_disabled=True):
    tunnels = load_catalog().get("tunnels", [])
    if not include_disabled:
        tunnels = [item for item in tunnels if item.get("enabled", True)]
    return sorted([dict(item) for item in tunnels], key=lambda item: (int(item.get("portal_port", 0) or 0), item.get("id", "")))


def get_tunnel(node_id):
    node_id = clean_id(node_id)
    for item in list_tunnels(include_disabled=True):
        if item.get("id") == node_id:
            return dict(item)
    raise RuntimeError("tunnel not found")


def delete_tunnel(node_id):
    node_id = clean_id(node_id)
    store = load_catalog()
    tunnels = store.setdefault("tunnels", [])
    for idx, item in enumerate(tunnels):
        if item.get("id") == node_id:
            removed = tunnels.pop(idx)
            save_catalog(store)
            return removed
    raise RuntimeError("tunnel not found")


def set_tunnel_enabled(node_id, enabled):
    store = load_catalog()
    for item in store.setdefault("tunnels", []):
        if item.get("id") == clean_id(node_id):
            item["enabled"] = bool(enabled)
            item["updated_at"] = now_iso()
            save_catalog(store)
            return item
    raise RuntimeError("tunnel not found")


def public_tunnel(item):
    tunnel = dict(item)
    tunnel.pop("private_key", None)
    tunnel["display_name"] = tunnel.get("name") or tunnel.get("id", "")
    tunnel["portal"] = f":{tunnel.get('portal_port')}"
    tunnel["target"] = f"{tunnel.get('target_host')}:{tunnel.get('target_port')}"
    tunnel["domain"] = tunnel.get("public_domain", "")
    tunnel.setdefault("bridge_mode", BRIDGE_MODE_DEDICATED)
    tunnel.setdefault("bridge_id", tunnel.get("id", ""))
    tunnel.setdefault("bridge_platform", BRIDGE_PLATFORM_MACOS)
    return tunnel


def list_public_tunnels(include_disabled=True):
    return [public_tunnel(item) for item in list_tunnels(include_disabled=include_disabled)]


def reality_profile_for_tunnel(tunnel):
    return {
        "server_name": tunnel.get("reality_sni") or DEFAULT_REALITY_SNI,
        "address": tunnel.get("server_address", ""),
        "port": tunnel.get("server_port", 443),
        "internal_port": tunnel.get("internal_port", 9443),
        "public_key": tunnel.get("public_key", ""),
        "private_key": tunnel.get("private_key", ""),
        "short_id": tunnel.get("short_id", ""),
    }
