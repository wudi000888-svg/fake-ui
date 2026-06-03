import base64
import json
import time
import urllib.parse

import hy2_panel
import node_catalog
import admin_profile
import user_store
import xray_panel
from panel_config import DEFAULT_VLESS_ADDRESS, QUOTA_COLLECT_CMD
from sync_utils import run_shell


def subscription_expire_timestamp(user):
    exp = user_store.parse_time(user.get("expires_at"))
    if not exp:
        return int(time.time()) + 10 * 365 * 24 * 3600
    return int(exp.timestamp())


def subscription_userinfo_header(user):
    used = int(user.get("used_bytes", 0) or 0)
    quota = int(user.get("quota_bytes", 0) or 0)

    if quota <= 0:
        quota = 1024 * 1024 * 1024 * 1024 * 1024

    expire = subscription_expire_timestamp(user)
    return f"upload=0; download={used}; total={quota}; expire={expire}"


def subscription_title(username, user):
    used = int(user.get("used_bytes", 0) or 0)
    quota = int(user.get("quota_bytes", 0) or 0)
    exp = str(user.get("expires_at", ""))[:10] or "unknown"

    if quota > 0:
        remain = max(0, quota - used)
        remain_gb = remain / 1024 / 1024 / 1024
        return f"{username}-remain-{remain_gb:.2f}GB-exp-{exp}"

    return f"{username}-unlimited-exp-{exp}"


def vless_reality_params():
    settings = xray_panel.read_link_settings()
    cfg = xray_panel.load_config()
    inbound = xray_panel.ensure_xray_inbound(cfg)

    reality = inbound.get("streamSettings", {}).get("realitySettings", {})
    sni = (reality.get("serverNames") or [""])[0]
    sid = (reality.get("shortIds") or [""])[0]
    private_key = reality.get("privateKey", "")

    flow = ""
    clients = inbound.get("settings", {}).get("clients", [])
    for c in clients:
        if c.get("flow"):
            flow = c.get("flow")
            break

    if not sni or not private_key:
        raise RuntimeError("VLESS Reality 参数不完整。")

    pbk = xray_panel.reality_public_key_from_private(private_key)
    return settings, inbound, sni, sid, pbk, flow


def build_vless_link_from_params(username, user, node, params_tuple):
    settings, inbound, sni, sid, pbk, flow = params_tuple
    node = node or (node_catalog.nodes_for_user(user, kind="vless", include_disabled=False) or [{}])[0]
    node_id = node.get("id", node_catalog.PRIMARY_VLESS_NODE_ID)
    uuid = node_catalog.vless_uuid_for_user(user, node_id)
    if not uuid:
        raise RuntimeError("用户 VLESS Reality 参数不完整。")
    params = {
        "encryption": "none",
        "security": "reality",
        "sni": sni,
        "fp": "chrome",
        "pbk": pbk,
        "type": "tcp",
        "headerType": "none",
    }

    if flow:
        params["flow"] = flow
    if sid:
        params["sid"] = sid

    address = str(settings.get("vless_address", DEFAULT_VLESS_ADDRESS))
    port = str(settings.get("vless_port", 443))
    name = urllib.parse.quote(node_catalog.display_name_for_node(node, f"{username}_VLESS_Reality"))
    query = urllib.parse.urlencode(params, safe="-_.~")
    return f"vless://{uuid}@{address}:{port}?{query}#{name}"


def build_vless_link_for_airport_user(username, user, node=None):
    return build_vless_link_from_params(username, user, node, vless_reality_params())


def build_vless_links_for_airport_user(username, user):
    params_tuple = vless_reality_params()
    result = []
    for node in node_catalog.nodes_for_user(user, kind="vless", include_disabled=False):
        if node_catalog.vless_uuid_for_user(user, node.get("id", "")):
            result.append(build_vless_link_from_params(username, user, node, params_tuple))
    return result


def build_hy2_link_for_airport_user(username, user):
    env = hy2_panel.hy2_read_env()
    domain = env["HY_DOMAIN"]
    port = env.get("HY_PORT", "443")

    hy_user = urllib.parse.quote(user.get("hy2_username") or username, safe="")
    hy_pass = urllib.parse.quote(user.get("hy2_password", ""), safe="")
    name = urllib.parse.quote(node_catalog.display_name("hy2", f"{username}_HY2"))

    return f"hysteria2://{hy_user}:{hy_pass}@{domain}:{port}/?sni={domain}&insecure=0#{name}"


def build_airport_subscription_text(username, user):
    if not user_store.user_is_active(username, user):
        raise RuntimeError("expired")

    kinds = node_catalog.allowed_kinds_for_user(user)
    links = []
    if "vless" in kinds:
        links.extend(build_vless_links_for_airport_user(username, user))
    if "hy2" in kinds:
        try:
            links.append(build_hy2_link_for_airport_user(username, user))
        except Exception:
            pass

    return "\n".join(links) + "\n"


def build_mihomo_config_for_airport_user(username, user):
    settings, inbound, sni, sid, pbk, flow = vless_reality_params()
    address = str(settings.get("vless_address", DEFAULT_VLESS_ADDRESS))
    port = int(settings.get("vless_port", 443))
    nodes = [
        node for node in node_catalog.nodes_for_user(user, kind="vless", include_disabled=False)
        if node_catalog.vless_uuid_for_user(user, node.get("id", ""))
    ]
    if not nodes:
        raise RuntimeError("用户 VLESS Reality 参数不完整。")

    def q(v):
        return json.dumps(str(v), ensure_ascii=False)

    lines = [
        "mixed-port: 7890",
        "allow-lan: false",
        "mode: rule",
        "log-level: info",
        "",
        "proxies:",
    ]

    proxy_names = []
    for node in nodes:
        node_name = node_catalog.display_name_for_node(node, f"{username}-VLESS-Reality")
        proxy_names.append(node_name)
        lines += [
            f"  - name: {q(node_name)}",
            "    type: vless",
            f"    server: {q(address)}",
            f"    port: {port}",
            f"    uuid: {q(node_catalog.vless_uuid_for_user(user, node.get('id', '')))}",
            "    network: tcp",
            "    tls: true",
            "    udp: true",
            f"    servername: {q(sni)}",
            "    client-fingerprint: chrome",
        ]
        if flow:
            lines.append(f"    flow: {q(flow)}")
        lines += [
            "    reality-opts:",
            f"      public-key: {q(pbk)}",
            f"      short-id: {q(sid)}",
        ]

    lines += [
        "",
        "proxy-groups:",
        "  - name: PROXY",
        "    type: select",
        "    proxies:",
    ]
    lines.extend([f"      - {q(name)}" for name in proxy_names])
    lines += ["", "rules:", "  - MATCH,PROXY", ""]

    return "\n".join(lines)


def build_subscription_response_by_path(path):
    parsed = urllib.parse.urlparse(path)
    clean = parsed.path.rstrip("/")
    qs = urllib.parse.parse_qs(parsed.query)
    prefix = "/sub/"

    if not clean.startswith(prefix):
        raise RuntimeError("无效订阅路径。")

    parts = clean[len(prefix):].split("/")
    token = parts[0]
    if len(parts) >= 2:
        mode = parts[1].lower().strip()
    else:
        mode = qs.get("target", [""])[0].lower().strip()

    username, user = user_store.find_user_by_token(token)
    if not username:
        username, user = admin_profile.find_by_token(token)
    if not username or not user:
        raise RuntimeError("invalid token")
    if not user_store.user_is_active(username, user):
        raise RuntimeError("expired")

    try:
        run_shell(QUOTA_COLLECT_CMD, timeout=60)
        user = user_store.get_user(username) or user
    except Exception:
        pass

    raw = build_airport_subscription_text(username, user)

    if mode in ("raw", "uri", "plain"):
        body = raw
        filename = f"{username}-raw.txt"
    elif mode in ("mihomo", "clash", "clash-meta", "meta"):
        body = build_mihomo_config_for_airport_user(username, user)
        filename = f"{username}-mihomo.yaml"
    else:
        body = base64.b64encode(raw.encode()).decode()
        filename = f"{username}.txt"

    headers = {
        "Subscription-Userinfo": subscription_userinfo_header(user),
        "Profile-Update-Interval": "12",
        "Profile-Title": subscription_title(username, user),
        "Content-Disposition": f'attachment; filename="{filename}"',
    }

    return body, headers


def build_subscription_by_path(path):
    body, headers = build_subscription_response_by_path(path)
    return body
