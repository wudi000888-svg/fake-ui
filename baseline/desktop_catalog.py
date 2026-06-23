import ipaddress
import re
import secrets
from datetime import datetime, timezone

import store_facade
from repositories.sqlite_settings import SQLiteSettingsRepository


SETTINGS_KEY = "desktop_catalog"
DEFAULT_WG_NETWORK = "10.77.0.0/24"
DEFAULT_SERVER_WG_IP = "10.77.0.1"
DEFAULT_WG_PORT = 51820
ROLES = {"controller", "host", "both"}
PLATFORMS = {"macos", "linux", "windows"}
PROTOCOLS = {"sunshine", "rdp", "vnc", "rustdesk", "ssh", "custom"}
PROTOCOL_PORTS = {
    "sunshine": 47984,
    "rdp": 3389,
    "vnc": 5900,
    "rustdesk": 21115,
    "ssh": 22,
    "custom": 0,
}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def clean_id(value):
    text = str(value or "").strip().lower()
    aliases = {
        "macbook 控制端": "macbook",
        "macbook": "macbook",
        "windows 主机": "windows",
        "windows": "windows",
        "linux 主机": "linux",
        "linux": "linux",
    }
    if text in aliases:
        return aliases[text]
    node_id = re.sub(r"[^a-z0-9_-]+", "-", text).strip("-")
    if not node_id:
        raise RuntimeError("desktop device id is required")
    return node_id


def clean_role(value):
    role = str(value or "host").strip().lower()
    if role not in ROLES:
        raise RuntimeError("desktop role is invalid")
    return role


def clean_platform(value):
    platform = str(value or "macos").strip().lower()
    if platform not in PLATFORMS:
        raise RuntimeError("desktop platform is invalid")
    return platform


def clean_protocol(value):
    protocol = str(value or "sunshine").strip().lower()
    if protocol not in PROTOCOLS:
        raise RuntimeError("desktop protocol is invalid")
    return protocol


def default_hysteria_user(node_id):
    return f"desktop-{node_id}"


def clean_hysteria_user(value, node_id):
    user = str(value or "").strip()
    if not user:
        return default_hysteria_user(node_id)
    if user.startswith("desktop:"):
        user = "desktop-" + user.split(":", 1)[1]
    if not user.startswith("desktop-") or ":" in user:
        raise RuntimeError("desktop Hysteria2 user must start with desktop- and cannot contain colon")
    return user


def clean_wg_ip(value):
    raw = str(value or "").strip()
    if not raw:
        raise RuntimeError("WireGuard IP is required")
    try:
        return str(ipaddress.ip_address(raw.split("/", 1)[0]))
    except ValueError as exc:
        raise RuntimeError("WireGuard IP is invalid") from exc


def used_values(devices, exclude_id=""):
    values = {"ids": set(), "wg_ips": set(), "hysteria_users": set(), "wg_public_keys": set()}
    for item in devices or []:
        if str(item.get("id", "")) == exclude_id:
            continue
        if item.get("id"):
            values["ids"].add(str(item.get("id")))
        if item.get("wg_ip"):
            values["wg_ips"].add(str(item.get("wg_ip")))
        if item.get("hysteria_user"):
            values["hysteria_users"].add(str(item.get("hysteria_user")))
        if item.get("wg_public_key"):
            values["wg_public_keys"].add(str(item.get("wg_public_key")))
    return values


def load_catalog():
    store_facade.ensure_sqlite()
    data = SQLiteSettingsRepository().get(SETTINGS_KEY, {"version": 1, "devices": [], "network": {}})
    data.setdefault("version", 1)
    data.setdefault("devices", [])
    data.setdefault("network", {})
    return data


def save_catalog(data):
    store_facade.ensure_sqlite()
    payload = {
        "version": 1,
        "devices": list((data or {}).get("devices", [])),
        "network": dict((data or {}).get("network", {})),
    }
    SQLiteSettingsRepository().set(SETTINGS_KEY, payload)
    return payload


def normalize_network(data=None, existing=None):
    data = data or {}
    existing = existing or {}
    wg_network = str(data.get("wg_network", existing.get("wg_network", DEFAULT_WG_NETWORK)) or DEFAULT_WG_NETWORK).strip()
    try:
        network = ipaddress.ip_network(wg_network, strict=False)
    except ValueError as exc:
        raise RuntimeError("WireGuard network is invalid") from exc
    server_wg_ip = clean_wg_ip(data.get("server_wg_ip", existing.get("server_wg_ip", DEFAULT_SERVER_WG_IP)))
    if ipaddress.ip_address(server_wg_ip) not in network:
        raise RuntimeError("server WireGuard IP must be inside WireGuard network")
    listen_port = int(data.get("server_listen_port", existing.get("server_listen_port", DEFAULT_WG_PORT)) or DEFAULT_WG_PORT)
    if listen_port <= 0 or listen_port > 65535:
        raise RuntimeError("server WireGuard listen port is invalid")
    return {
        "wg_network": str(network),
        "server_wg_ip": server_wg_ip,
        "server_wg_cidr": f"{server_wg_ip}/{network.prefixlen}",
        "server_wg_private_key": str(data.get("server_wg_private_key", existing.get("server_wg_private_key", "")) or "").strip(),
        "server_wg_public_key": str(data.get("server_wg_public_key", existing.get("server_wg_public_key", "")) or "").strip(),
        "server_listen_port": listen_port,
        "updated_at": now_iso(),
    }


def get_network():
    store = load_catalog()
    return normalize_network(store.get("network", {}))


def update_network(data):
    store = load_catalog()
    network = normalize_network(data or {}, store.get("network", {}))
    store["network"] = network
    save_catalog(store)
    return network


def normalize_device(data, existing=None, existing_devices=None):
    data = data or {}
    existing = existing or {}
    existing_devices = existing_devices or []
    node_id = clean_id(data.get("id") or existing.get("id") or data.get("name") or existing.get("name"))
    role = clean_role(data.get("role", existing.get("role", "host")))
    platform = clean_platform(data.get("platform", existing.get("platform", "macos")))
    protocol = clean_protocol(data.get("desktop_protocol", existing.get("desktop_protocol", "sunshine")))
    wg_ip = clean_wg_ip(data.get("wg_ip", existing.get("wg_ip", "")))
    hysteria_user = clean_hysteria_user(data.get("hysteria_user", existing.get("hysteria_user", "")), node_id)
    hysteria_password = str(data.get("hysteria_password", existing.get("hysteria_password", "")) or "").strip()
    if not hysteria_password:
        hysteria_password = secrets.token_urlsafe(24)
    desktop_port = int(data.get("desktop_port", existing.get("desktop_port", 0)) or 0)
    if not desktop_port:
        desktop_port = PROTOCOL_PORTS[protocol]
    values = used_values(existing_devices, exclude_id=node_id)
    if node_id in values["ids"]:
        raise RuntimeError("desktop device id is duplicated")
    if wg_ip in values["wg_ips"]:
        raise RuntimeError("WireGuard IP is duplicated")
    if hysteria_user in values["hysteria_users"]:
        raise RuntimeError("desktop Hysteria2 user is duplicated")
    wg_public_key = str(data.get("wg_public_key", existing.get("wg_public_key", "")) or "").strip()
    if wg_public_key and wg_public_key in values["wg_public_keys"]:
        raise RuntimeError("WireGuard public key is duplicated")
    item = {
        "id": node_id,
        "name": str(data.get("name", existing.get("name", node_id)) or node_id).strip(),
        "enabled": bool(data.get("enabled", existing.get("enabled", True))),
        "role": role,
        "platform": platform,
        "desktop_protocol": protocol,
        "desktop_port": desktop_port,
        "wg_ip": wg_ip,
        "wg_cidr": f"{wg_ip}/32",
        "wg_private_key": str(data.get("wg_private_key", existing.get("wg_private_key", "")) or "").strip(),
        "wg_public_key": wg_public_key,
        "wg_preshared_key": str(data.get("wg_preshared_key", existing.get("wg_preshared_key", "")) or "").strip(),
        "hysteria_user": hysteria_user,
        "hysteria_password": hysteria_password,
        "listen_host": str(data.get("listen_host", existing.get("listen_host", "127.0.0.1")) or "127.0.0.1").strip(),
        "listen_port": int(data.get("listen_port", existing.get("listen_port", DEFAULT_WG_PORT)) or DEFAULT_WG_PORT),
        "remote_host": str(data.get("remote_host", existing.get("remote_host", "127.0.0.1")) or "127.0.0.1").strip(),
        "remote_port": int(data.get("remote_port", existing.get("remote_port", DEFAULT_WG_PORT)) or DEFAULT_WG_PORT),
        "updated_at": now_iso(),
    }
    if item["desktop_port"] < 0 or item["desktop_port"] > 65535:
        raise RuntimeError("desktop port is invalid")
    if item["listen_port"] <= 0 or item["listen_port"] > 65535:
        raise RuntimeError("WireGuard listen port is invalid")
    if item["remote_port"] <= 0 or item["remote_port"] > 65535:
        raise RuntimeError("WireGuard remote port is invalid")
    item["connection_target"] = item["wg_ip"]
    if "created_at" in existing:
        item["created_at"] = existing["created_at"]
    else:
        item["created_at"] = now_iso()
    return item


def upsert_device(data):
    store = load_catalog()
    devices = store.setdefault("devices", [])
    node_id = clean_id((data or {}).get("id") or (data or {}).get("name"))
    for idx, item in enumerate(devices):
        if item.get("id") == node_id:
            device = normalize_device(data, item, devices)
            devices[idx] = device
            save_catalog(store)
            return device
    device = normalize_device(data, existing_devices=devices)
    devices.append(device)
    save_catalog(store)
    return device


def list_devices(include_disabled=True):
    devices = load_catalog().get("devices", [])
    if not include_disabled:
        devices = [item for item in devices if item.get("enabled", True)]
    return sorted([public_device(item) for item in devices], key=lambda item: (item.get("role", ""), item.get("id", "")))


def get_device(node_id):
    node_id = clean_id(node_id)
    for item in load_catalog().get("devices", []):
        if item.get("id") == node_id:
            return public_device(item)
    raise RuntimeError("desktop device not found")


def delete_device(node_id):
    node_id = clean_id(node_id)
    store = load_catalog()
    devices = store.setdefault("devices", [])
    for idx, item in enumerate(devices):
        if item.get("id") == node_id:
            removed = devices.pop(idx)
            save_catalog(store)
            return public_device(removed)
    raise RuntimeError("desktop device not found")


def set_device_enabled(node_id, enabled):
    store = load_catalog()
    for item in store.setdefault("devices", []):
        if item.get("id") == clean_id(node_id):
            item["enabled"] = bool(enabled)
            item["updated_at"] = now_iso()
            save_catalog(store)
            return public_device(item)
    raise RuntimeError("desktop device not found")


def public_device(device):
    item = dict(device or {})
    item["connection_target"] = item.get("wg_ip", "")
    item["display_name"] = item.get("name") or item.get("id", "")
    item["desktop_target"] = f"{item.get('wg_ip', '')}:{item.get('desktop_port', '')}"
    return item


def active_auth_users():
    users = {}
    for item in load_catalog().get("devices", []):
        if item.get("enabled", True) and item.get("hysteria_user") and item.get("hysteria_password"):
            users[str(item["hysteria_user"])] = str(item["hysteria_password"])
    return users
