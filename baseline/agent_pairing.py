import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import store_facade
import tunnel_bridge_bundle
import tunnel_catalog
import tunnel_config_builder
from repositories.sqlite_settings import SQLiteSettingsRepository


SETTINGS_KEY = "agent_pairings"
BUNDLE_KINDS = {"dedicated", "shared"}
CAPABILITIES = ["bootstrap", "local_status"]
DEFAULT_TTL_MINUTES = 30


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
    data.setdefault("version", 1)
    data.setdefault("pairings", {})
    return data


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


def create_pairing(bundle_kind, bridge_id, platform, created_by="admin", ttl_minutes=DEFAULT_TTL_MINUTES):
    kind = clean_bundle_kind(bundle_kind)
    clean_bridge_id = tunnel_catalog.clean_id(bridge_id)
    clean_platform = tunnel_catalog.clean_bridge_platform(platform)
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
    data = load_store()
    data.setdefault("pairings", {})[token_id] = record
    save_store(data)
    return {"pairing_token": raw_token, "record": public_record(record)}


def update_pairing(token_id, updates):
    data = load_store()
    pairings = data.setdefault("pairings", {})
    record = pairings.get(str(token_id or ""))
    if not record:
        raise RuntimeError("pairing token is invalid")
    record.update(dict(updates or {}))
    save_store(data)
    return public_record(record)


def consume_pairing(token_id, pairing_token):
    data = load_store()
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
    record["used_at"] = isoformat(now_utc())
    save_store(data)
    return dict(record)


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


def bridge_config_for_pairing(record):
    if record.get("bundle_kind") == "dedicated":
        return dedicated_bridge_config(record.get("bridge_id"), record.get("platform"))
    if record.get("bundle_kind") == "shared":
        return shared_bridge_config(record.get("bridge_id"), record.get("platform"))
    raise RuntimeError("bundle kind is invalid")


def validate_bootstrap_request(data):
    payload = data or {}
    if int(payload.get("schema") or 0) != 1:
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
    record = consume_pairing(token_id, pairing_token)
    xray_config, dashboard_metadata = bridge_config_for_pairing(record)
    runtime = dashboard_metadata.get("runtime") or {}
    agent = {
        "agent_id": record.get("agent_id"),
        "bridge_id": record.get("bridge_id"),
        "bundle_kind": record.get("bundle_kind"),
        "platform": record.get("platform"),
        "capabilities": list(record.get("capabilities") or CAPABILITIES),
    }
    install = {
        "service_name": runtime.get("name", ""),
        "restart_command": runtime.get("restart_command", ""),
        "log_command": runtime.get("log_command", ""),
    }
    return {
        "agent": agent,
        "xray_config": xray_config,
        "dashboard_metadata": dashboard_metadata,
        "install": install,
    }
