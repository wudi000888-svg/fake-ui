import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import db
import store_facade
import desktop_catalog
import desktop_config_builder
import proxy_bypass
import tunnel_bridge_bundle
import tunnel_catalog
import tunnel_config_builder
from repositories.sqlite_base import dump_json, load_json
from repositories.sqlite_settings import SQLiteSettingsRepository


SETTINGS_KEY = "agent_pairings"
BUNDLE_KINDS = {"dedicated", "shared"}
BASE_CAPABILITIES = ["bootstrap", "local_status"]
CAPABILITIES = BASE_CAPABILITIES
DEFAULT_TTL_MINUTES = 30
AUTO_PLATFORM = "auto"


def now_utc():
    return datetime.now(timezone.utc)


def isoformat(value):
    return value.astimezone(timezone.utc).isoformat()


def parse_time(value):
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def token_hash(token):
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def load_store():
    store_facade.ensure_sqlite()
    data = SQLiteSettingsRepository().get(SETTINGS_KEY, {"version": 1, "pairings": {}})
    return normalize_store(data)


def normalize_store(data):
    data = dict(data or {})
    data.setdefault("version", 1)
    data.setdefault("pairings", {})
    return data


def load_store_from_conn(conn):
    row = conn.execute("select value_json from settings where key = ?", (SETTINGS_KEY,)).fetchone()
    return normalize_store(load_json(row["value_json"]) if row else {"version": 1, "pairings": {}})


def save_store_to_conn(conn, data):
    payload = {"version": 1, "pairings": dict((data or {}).get("pairings", {}))}
    conn.execute(
        """
        insert or replace into settings (key, value_json, updated_at)
        values (?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        """,
        (SETTINGS_KEY, dump_json(payload)),
    )
    return payload


def update_store(mutator):
    store_facade.ensure_sqlite()
    conn = db.connect()
    try:
        conn.execute("begin immediate")
        data = load_store_from_conn(conn)
        result = mutator(data)
        save_store_to_conn(conn, data)
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def save_store(data):
    store_facade.ensure_sqlite()
    payload = {"version": 1, "pairings": dict((data or {}).get("pairings", {}))}
    SQLiteSettingsRepository().set(SETTINGS_KEY, payload)
    return payload


def public_record(record):
    safe = dict(record or {})
    safe.pop("token_hash", None)
    return safe


def clean_bundle_kind(value):
    kind = str(value or "").strip().lower()
    if kind not in BUNDLE_KINDS:
        raise RuntimeError("bundle kind is invalid")
    return kind


def clean_pairing_platform(value):
    platform = str(value or "").strip().lower()
    if platform in {AUTO_PLATFORM, "universal"}:
        return AUTO_PLATFORM
    return tunnel_catalog.clean_bridge_platform(platform)


def create_pairing(bundle_kind, bridge_id, platform, created_by="admin", ttl_minutes=DEFAULT_TTL_MINUTES):
    kind = clean_bundle_kind(bundle_kind)
    clean_bridge_id = tunnel_catalog.clean_id(bridge_id)
    clean_platform = clean_pairing_platform(platform)
    created_at = now_utc()
    raw_token = secrets.token_urlsafe(32)
    token_id = "pair_" + secrets.token_urlsafe(12)
    record = {
        "token_id": token_id,
        "token_hash": token_hash(raw_token),
        "bridge_id": clean_bridge_id,
        "bundle_kind": kind,
        "platform": clean_platform,
        "expires_at": isoformat(created_at + timedelta(minutes=int(ttl_minutes or DEFAULT_TTL_MINUTES))),
        "used_at": "",
        "created_at": isoformat(created_at),
        "created_by": str(created_by or "admin"),
        "agent_id": "agent_" + secrets.token_urlsafe(12),
        "capabilities": list(CAPABILITIES),
    }
    def write(data):
        data.setdefault("pairings", {})[token_id] = record
        return {"pairing_token": raw_token, "record": public_record(record)}

    return update_store(write)


def update_pairing(token_id, updates):
    def update(data):
        pairings = data.setdefault("pairings", {})
        record = pairings.get(str(token_id or ""))
        if not record:
            raise RuntimeError("pairing token is invalid")
        record.update(dict(updates or {}))
        return public_record(record)

    return update_store(update)


def validate_pairing_record(data, token_id, pairing_token):
    pairings = data.setdefault("pairings", {})
    record = pairings.get(str(token_id or "").strip())
    if not record:
        raise RuntimeError("pairing token is invalid")
    if record.get("used_at"):
        raise RuntimeError("pairing token already used")
    expires_at = parse_time(record.get("expires_at"))
    if expires_at and expires_at <= now_utc():
        raise RuntimeError("pairing token expired")
    expected = str(record.get("token_hash") or "")
    actual = token_hash(pairing_token)
    if not expected or not hmac.compare_digest(expected, actual):
        raise RuntimeError("pairing token is invalid")
    return record


def pairing_snapshot(token_id, pairing_token):
    data = load_store()
    return dict(validate_pairing_record(data, token_id, pairing_token))


def mark_pairing_used(token_id, pairing_token, expected=None):
    expected = dict(expected or {})

    def mark(data):
        record = validate_pairing_record(data, token_id, pairing_token)
        for field in ("token_id", "bridge_id", "bundle_kind", "platform", "agent_id"):
            if expected and record.get(field) != expected.get(field):
                raise RuntimeError("pairing token changed")
        if expected and list(record.get("capabilities") or []) != list(expected.get("capabilities") or []):
            raise RuntimeError("pairing token changed")
        record["used_at"] = isoformat(now_utc())
        return dict(record)

    return update_store(mark)


def consume_pairing(token_id, pairing_token):
    return mark_pairing_used(token_id, pairing_token)


def dedicated_bridge_config(bridge_id, platform):
    tunnel = tunnel_catalog.get_tunnel(bridge_id)
    cfg = tunnel_config_builder.build_bridge_config(tunnel, tunnel_catalog.reality_profile_for_tunnel(tunnel))
    metadata = tunnel_bridge_bundle.dashboard_metadata("dedicated", tunnel.get("id"), platform, [tunnel])
    return cfg, metadata


def shared_bridge_tunnels(bridge_id):
    clean_bridge_id = tunnel_catalog.clean_id(bridge_id)
    tunnels = [
        tunnel
        for tunnel in tunnel_catalog.list_tunnels(include_disabled=False)
        if tunnel.get("bridge_mode") == tunnel_catalog.BRIDGE_MODE_SHARED
        and tunnel.get("bridge_id") == clean_bridge_id
    ]
    if not tunnels:
        raise RuntimeError("shared bridge not found")
    return tunnels


def shared_bridge_config(bridge_id, platform):
    tunnels = shared_bridge_tunnels(bridge_id)
    profile = tunnel_catalog.reality_profile_for_tunnel(tunnels[0])
    cfg = tunnel_config_builder.build_shared_bridge_config(tunnels, profile)
    metadata = tunnel_bridge_bundle.dashboard_metadata("shared", bridge_id, platform, tunnels)
    return cfg, metadata


def effective_platform_for_record(record, requested_platform=""):
    stored = str((record or {}).get("platform") or "").strip().lower()
    if stored != AUTO_PLATFORM:
        return tunnel_catalog.clean_bridge_platform(stored)
    requested = str(requested_platform or "").strip().lower()
    if requested in {AUTO_PLATFORM, "universal", ""}:
        raise RuntimeError("agent platform is required")
    return tunnel_catalog.clean_bridge_platform(requested)


def bridge_config_for_pairing(record, requested_platform=""):
    platform = effective_platform_for_record(record, requested_platform)
    if record.get("bundle_kind") == "dedicated":
        return dedicated_bridge_config(record.get("bridge_id"), platform)
    if record.get("bundle_kind") == "shared":
        return shared_bridge_config(record.get("bridge_id"), platform)
    raise RuntimeError("bundle kind is invalid")


def capabilities_for_payload(xray_config, remote_desktop=None):
    values = list(BASE_CAPABILITIES)
    if xray_config:
        values.append("tcp_tunnel")
    if remote_desktop:
        values.append("remote_desktop")
    values.append("proxy_compat")
    result = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def remote_desktop_for_bridge(bridge_id):
    try:
        device = desktop_catalog.get_device(bridge_id)
    except RuntimeError:
        return None
    if not device.get("enabled", True):
        return None
    return {
        "device": device,
        "hysteria_config": desktop_config_builder.hysteria_client_config(device),
        "wireguard_config": desktop_config_builder.wireguard_config(device),
        "proxy_bypass": proxy_bypass.desktop_proxy_bypass(),
        "topology": desktop_config_builder.topology(),
    }


def validate_bootstrap_request(data):
    if not isinstance(data, dict):
        raise RuntimeError("request body must be an object")
    payload = data
    schema = payload.get("schema")
    if not ((type(schema) is int and schema == 1) or schema == "1"):
        raise RuntimeError("schema is invalid")
    token_id = str(payload.get("token_id") or "").strip()
    if not token_id:
        raise RuntimeError("token_id is required")
    pairing_token = str(payload.get("pairing_token") or "").strip()
    if not pairing_token:
        raise RuntimeError("pairing_token is required")
    return token_id, pairing_token


def bootstrap_agent(data):
    token_id, pairing_token = validate_bootstrap_request(data)
    snapshot = pairing_snapshot(token_id, pairing_token)
    effective_platform = effective_platform_for_record(snapshot, (data or {}).get("platform"))
    xray_config, dashboard_metadata = bridge_config_for_pairing(snapshot, effective_platform)
    remote_desktop = remote_desktop_for_bridge(snapshot.get("bridge_id"))
    tcp_proxy_compat = proxy_bypass.tcp_reality_proxy_bypass(xray_config)
    proxy_compat = (remote_desktop or {}).get("proxy_bypass") or tcp_proxy_compat
    record = mark_pairing_used(token_id, pairing_token, expected=snapshot)
    runtime = dashboard_metadata.get("runtime") or {}
    capabilities = capabilities_for_payload(xray_config, remote_desktop)
    agent = {
        "agent_id": record.get("agent_id"),
        "bridge_id": record.get("bridge_id"),
        "bundle_kind": record.get("bundle_kind"),
        "platform": effective_platform,
        "capabilities": capabilities,
    }
    dashboard_metadata = dict(dashboard_metadata or {})
    dashboard_metadata["capabilities"] = capabilities
    dashboard_metadata["proxy_bypass"] = proxy_compat
    if remote_desktop:
        dashboard_metadata["remote_desktop"] = {
            "device": remote_desktop.get("device"),
            "topology": remote_desktop.get("topology"),
            "proxy_bypass": remote_desktop.get("proxy_bypass"),
            "hysteria_config_path": "hysteria-desktop.yaml",
            "wireguard_config_path": "wireguard.conf",
        }
    install = {
        "service_name": runtime.get("name", ""),
        "restart_command": runtime.get("restart_command", ""),
        "log_command": runtime.get("log_command", ""),
    }
    payload = {
        "agent": agent,
        "xray_config": xray_config,
        "dashboard_metadata": dashboard_metadata,
        "install": install,
        "proxy_bypass": proxy_compat,
        "tcp_proxy_bypass": tcp_proxy_compat,
    }
    if remote_desktop:
        payload["remote_desktop"] = remote_desktop
    return payload
