import os
import urllib.parse

import agent_pairing
import app_urls
import audit_log
import tunnel_bridge_bundle
import tunnel_catalog
import tunnel_config_builder
import tunnel_nginx
import xray_runtime
from api_common import ok, require_admin
from http_utils import api_error
from panel_config import DEFAULT_VLESS_ADDRESS, XRAY_BIN
from process_utils import run


def derive_public_key(private_key):
    private_key = str(private_key or "").strip()
    if not private_key:
        return ""
    code, out = run([XRAY_BIN, "x25519", "-i", private_key], timeout=15)
    if code != 0:
        return ""
    for line in out.splitlines():
        lower = line.lower()
        if "public" in lower and ":" in line:
            return line.split(":", 1)[1].strip()
    return ""


def current_reality_profile(public_domain=""):
    cfg = xray_runtime.load_config()
    inbound = tunnel_config_builder.find_reality_inbound(cfg)
    stream = inbound.get("streamSettings", {})
    reality = stream.get("realitySettings", {})
    server_names = reality.get("serverNames") or []
    short_ids = reality.get("shortIds") or []
    private_key = str(reality.get("privateKey") or "").strip()
    public_key = str(reality.get("publicKey") or "").strip() or derive_public_key(private_key)
    return {
        "server_name": (server_names[0] if server_names else "www.cloudflare.com"),
        "address": str(public_domain or DEFAULT_VLESS_ADDRESS).strip(),
        "port": 443,
        "internal_port": int(inbound.get("port") or 8443),
        "public_key": public_key,
        "private_key": private_key,
        "short_id": (short_ids[0] if short_ids else ""),
    }


def fill_tunnel_defaults(data):
    data = dict(data or {})
    public_domain = tunnel_catalog.clean_domain(data.get("public_domain", "")) if data.get("public_domain") else ""
    server_address = public_domain or str(data.get("server_address") or "").strip() or DEFAULT_VLESS_ADDRESS
    needs_profile = (
        not data.get("reality_sni")
        or not data.get("public_key")
        or not data.get("short_id")
    )
    profile = current_reality_profile(server_address) if needs_profile else {}
    data.setdefault("reality_sni", profile.get("server_name", "www.cloudflare.com"))
    data.setdefault("server_address", server_address)
    data.setdefault("server_port", profile.get("port", 443))
    data.setdefault("internal_port", profile.get("internal_port", 8443))
    if not data.get("public_key") and profile.get("public_key"):
        data["public_key"] = profile.get("public_key", "")
    if not data.get("public_key"):
        raise RuntimeError("Reality public key is required for tunnel bridge config")
    if not data.get("short_id") and profile.get("short_id"):
        data["short_id"] = profile.get("short_id", "")
    return data


def shared_bridge_tunnels(bridge_id):
    bridge_id = tunnel_catalog.clean_id(bridge_id)
    tunnels = [
        tunnel
        for tunnel in tunnel_catalog.list_tunnels(include_disabled=False)
        if tunnel.get("bridge_mode") == tunnel_catalog.BRIDGE_MODE_SHARED
        and tunnel.get("bridge_id") == bridge_id
    ]
    if not tunnels:
        raise RuntimeError("shared bridge not found")
    return tunnels


def shared_bridge_profile(tunnels):
    first = tunnels[0]
    return tunnel_catalog.reality_profile_for_tunnel(first)


def panel_url():
    return (os.getenv("PUBLIC_BASE_URL") or app_urls.absolute_url("/")).rstrip("/")


def handle_tunnel_get(path, session):
    parsed = urllib.parse.urlparse(path)
    clean = parsed.path
    if not clean.startswith("/api/tunnels"):
        return None
    if (err := require_admin(session)):
        return err

    if clean == "/api/tunnels":
        return ok(tunnels=tunnel_catalog.list_public_tunnels())

    if clean == "/api/tunnels/portal-config":
        cfg = tunnel_config_builder.build_portal_config(
            xray_runtime.load_config(),
            tunnel_catalog.list_tunnels(include_disabled=False),
        )
        return ok(filename="fake-ui-tunnel-portal.json", config=cfg)

    prefix = "/api/tunnels/"
    bridge_prefix = "/api/tunnels/bridges/"
    if clean.startswith(bridge_prefix):
        rest = clean[len(bridge_prefix):].strip("/")
        parts = [urllib.parse.unquote(part) for part in rest.split("/") if part]
        if len(parts) != 2:
            return api_error("not found", 404)
        bridge_id, action = parts
        try:
            tunnels = shared_bridge_tunnels(bridge_id)
        except RuntimeError as exc:
            return api_error(str(exc), 404)
        if action.endswith("-agent-bundle"):
            platform = action[:-len("-agent-bundle")]
            if platform not in tunnel_catalog.BRIDGE_PLATFORMS:
                return api_error("bridge platform is invalid", 400)
            pairing = agent_pairing.create_pairing("shared", bridge_id, platform, created_by=session.get("u", "admin"))
            content = tunnel_bridge_bundle.build_paired_agent_bundle(bridge_id, tunnels, pairing, panel_url(), platform)
            return ok(
                filename=f"{bridge_id}-{platform}-agent-bridge.tgz",
                content=content,
                content_type="application/gzip",
            )
        try:
            cfg = tunnel_config_builder.build_shared_bridge_config(tunnels, shared_bridge_profile(tunnels))
        except RuntimeError as exc:
            return api_error(str(exc), 404)
        if action == "bridge-config":
            return ok(filename=f"{bridge_id}-xray-bridge.json", config=cfg)
        if action.endswith("-bundle"):
            platform = action[:-len("-bundle")]
            if platform not in tunnel_catalog.BRIDGE_PLATFORMS:
                return api_error("bridge platform is invalid", 400)
            content = tunnel_bridge_bundle.build_agent_bundle(bridge_id, tunnels, cfg, platform)
            return ok(
                filename=f"{bridge_id}-{platform}-bridge.tgz",
                content=content,
                content_type="application/gzip",
            )
        return api_error("not found", 404)

    suffix = "/bridge-config"
    if clean.startswith(prefix) and clean.endswith(suffix):
        node_id = urllib.parse.unquote(clean[len(prefix):-len(suffix)].strip("/"))
        tunnel = tunnel_catalog.get_tunnel(node_id)
        cfg = tunnel_config_builder.build_bridge_config(tunnel, tunnel_catalog.reality_profile_for_tunnel(tunnel))
        return ok(filename=f"{tunnel.get('id')}-xray-bridge.json", config=cfg)

    suffix = "-agent-bundle"
    if clean.startswith(prefix) and clean.endswith(suffix):
        rest = clean[len(prefix):-len(suffix)].strip("/")
        parts = [urllib.parse.unquote(part) for part in rest.split("/") if part]
        if len(parts) != 2:
            return api_error("not found", 404)
        node_id, platform = parts
        if platform not in tunnel_catalog.BRIDGE_PLATFORMS:
            return api_error("bridge platform is invalid", 400)
        tunnel = tunnel_catalog.get_tunnel(node_id)
        pairing = agent_pairing.create_pairing("dedicated", tunnel.get("id"), platform, created_by=session.get("u", "admin"))
        content = tunnel_bridge_bundle.build_paired_bundle(tunnel, pairing, panel_url(), platform)
        return ok(
            filename=f"{tunnel.get('id')}-{platform}-agent-bridge.tgz",
            content=content,
            content_type="application/gzip",
        )

    suffix = "-bundle"
    if clean.startswith(prefix) and clean.endswith(suffix):
        rest = clean[len(prefix):-len(suffix)].strip("/")
        parts = [urllib.parse.unquote(part) for part in rest.split("/") if part]
        if len(parts) != 2:
            return api_error("not found", 404)
        node_id, platform = parts
        if platform not in tunnel_catalog.BRIDGE_PLATFORMS:
            return api_error("bridge platform is invalid", 400)
        tunnel = tunnel_catalog.get_tunnel(node_id)
        cfg = tunnel_config_builder.build_bridge_config(tunnel, tunnel_catalog.reality_profile_for_tunnel(tunnel))
        content = tunnel_bridge_bundle.build_bundle(tunnel, cfg, platform)
        return ok(
            filename=f"{tunnel.get('id')}-{platform}-bridge.tgz",
            content=content,
            content_type="application/gzip",
        )

    return api_error("not found", 404)


def handle_tunnel_post(clean, data, session):
    if not clean.startswith("/api/tunnels"):
        return None
    if (err := require_admin(session)):
        return err

    if clean == "/api/tunnels/save":
        try:
            tunnel = tunnel_catalog.upsert_tunnel(fill_tunnel_defaults(data or {}))
        except RuntimeError as exc:
            return api_error(str(exc), 400)
        audit_log.write(session.get("u", "admin"), "tunnel.save", tunnel.get("id", ""), tunnel_catalog.public_tunnel(tunnel))
        return ok(tunnel=tunnel_catalog.public_tunnel(tunnel), tunnels=tunnel_catalog.list_public_tunnels())

    if clean == "/api/tunnels/action":
        action = (data or {}).get("action", "")
        node_id = (data or {}).get("id", "")
        if action == "delete":
            tunnel = tunnel_catalog.delete_tunnel(node_id)
        elif action in ("enable", "disable"):
            tunnel = tunnel_catalog.set_tunnel_enabled(node_id, action == "enable")
        else:
            raise RuntimeError("unknown tunnel action")
        audit_log.write(session.get("u", "admin"), "tunnel." + action, node_id)
        return ok(tunnel=tunnel_catalog.public_tunnel(tunnel), tunnels=tunnel_catalog.list_public_tunnels())

    if clean == "/api/tunnels/apply":
        tunnels = tunnel_catalog.list_tunnels(include_disabled=False)
        cfg = tunnel_config_builder.build_portal_config(
            xray_runtime.load_config(),
            tunnels,
        )
        backup = xray_runtime.write_and_restart_xray(cfg)
        nginx = tunnel_nginx.apply_native_nginx(tunnels)
        audit_log.write(session.get("u", "admin"), "tunnel.apply", "xray-nginx", {"backup": str(backup), "nginx": nginx})
        return ok(message="穿透入口已应用到 Xray / Nginx", backup=str(backup), nginx=nginx, tunnels=tunnel_catalog.list_public_tunnels())

    return api_error("not found", 404)
