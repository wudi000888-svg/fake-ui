import copy
import re

from panel_config import INBOUND_TAG


PORTAL_INBOUND_PREFIX = "tunnel-portal-"
REVERSE_OUTBOUND_PREFIX = "tunnel-reverse-"
BRIDGE_REVERSE_INBOUND_TAG = "tunnel-reverse-in"
BRIDGE_REVERSE_OUTBOUND_TAG = "tunnel-reverse-out"
BRIDGE_LOCAL_OUTBOUND_TAG = "tunnel-local-service"
DEFAULT_FLOW = "xtls-rprx-vision"


def safe_tag(value):
    clean = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(value or "").strip().lower()).strip("-")
    return clean or "node"


def enabled_nodes(nodes):
    return [copy.deepcopy(node) for node in (nodes or []) if node.get("enabled", True)]


def int_field(data, key, default=0):
    value = data.get(key, default)
    try:
        return int(value)
    except Exception:
        return int(default)


def portal_tag(node):
    return PORTAL_INBOUND_PREFIX + safe_tag(node.get("id"))


def reverse_tag(node):
    return REVERSE_OUTBOUND_PREFIX + safe_tag(node.get("id"))


def bridge_email(node):
    return str(node.get("email") or ("tunnel:" + safe_tag(node.get("id")))).strip()


def flow_for_node(node):
    return str(node.get("flow") or DEFAULT_FLOW).strip() or DEFAULT_FLOW


def reality_server_name(profile):
    return str(profile.get("server_name") or profile.get("sni") or profile.get("reality_sni") or "").strip()


def reality_short_id(profile):
    short_id = profile.get("short_id")
    if short_id is None:
        short_ids = profile.get("short_ids") or []
        short_id = short_ids[0] if short_ids else ""
    return str(short_id or "").strip()


def is_tunnel_client(client):
    email = str(client.get("email", ""))
    reverse = client.get("reverse") or {}
    return email.startswith("tunnel:") or str(reverse.get("tag", "")).startswith(REVERSE_OUTBOUND_PREFIX)


def find_reality_inbound(cfg):
    for inbound in cfg.get("inbounds", []):
        if inbound.get("tag") == INBOUND_TAG:
            return inbound
    raise RuntimeError(f"未找到 Xray 入站 tag={INBOUND_TAG}")


def build_portal_config(base_cfg, nodes):
    cfg = copy.deepcopy(base_cfg)
    inbound = find_reality_inbound(cfg)
    settings = inbound.setdefault("settings", {})
    existing_clients = settings.setdefault("clients", [])
    panel_client_ids = {
        str(client.get("id", "")).strip()
        for client in existing_clients
        if not is_tunnel_client(client) and str(client.get("id", "")).strip()
    }
    clients = [client for client in existing_clients if not is_tunnel_client(client)]
    settings["clients"] = clients

    cfg.setdefault("outbounds", [])
    if not any(out.get("tag") == "direct" for out in cfg["outbounds"]):
        cfg["outbounds"].append({"tag": "direct", "protocol": "freedom", "settings": {"domainStrategy": "UseIPv4"}})

    cfg.setdefault("routing", {})
    cfg["routing"].setdefault("domainStrategy", "IPIfNonMatch")
    rules = []
    for rule in cfg["routing"].setdefault("rules", []):
        inbound_tags = rule.get("inboundTag", [])
        if isinstance(inbound_tags, str):
            inbound_tags = [inbound_tags]
        if any(str(tag).startswith(PORTAL_INBOUND_PREFIX) for tag in inbound_tags):
            continue
        if str(rule.get("outboundTag", "")).startswith(REVERSE_OUTBOUND_PREFIX):
            continue
        rules.append(rule)
    cfg["routing"]["rules"] = rules
    cfg["inbounds"] = [
        inbound for inbound in cfg.get("inbounds", [])
        if not str(inbound.get("tag", "")).startswith(PORTAL_INBOUND_PREFIX)
    ]

    tunnel_rules = []
    seen_client_ids = set()
    seen_portal_ports = set()
    seen_portal_tags = set()
    seen_reverse_tags = set()
    seen_emails = {str(client.get("email", "")).strip() for client in clients if client.get("email")}
    for node in enabled_nodes(nodes):
        client_id = str(node.get("client_id") or "").strip()
        if not client_id:
            raise RuntimeError(f"tunnel {node.get('id')} UUID is required")
        if client_id in panel_client_ids:
            raise RuntimeError(f"tunnel {node.get('id')} UUID conflicts with an existing panel user")
        if client_id in seen_client_ids:
            raise RuntimeError(f"tunnel {node.get('id')} UUID is duplicated")
        seen_client_ids.add(client_id)

        port = int_field(node, "portal_port")
        if port in seen_portal_ports:
            raise RuntimeError(f"tunnel portal port {port} is duplicated")
        seen_portal_ports.add(port)

        p_tag = portal_tag(node)
        r_tag = reverse_tag(node)
        email = bridge_email(node)
        if p_tag in seen_portal_tags:
            raise RuntimeError(f"tunnel portal tag {p_tag} is duplicated")
        if r_tag in seen_reverse_tags:
            raise RuntimeError(f"tunnel reverse tag {r_tag} is duplicated")
        if email in seen_emails:
            raise RuntimeError(f"tunnel email {email} is duplicated")
        seen_portal_tags.add(p_tag)
        seen_reverse_tags.add(r_tag)
        seen_emails.add(email)

        client = {
            "id": client_id,
            "email": email,
            "reverse": {"tag": r_tag},
        }
        flow = flow_for_node(node)
        if flow:
            client["flow"] = flow
        settings["clients"].append(client)
        cfg["inbounds"].append(
            {
                "tag": portal_tag(node),
                "listen": "0.0.0.0",
                "port": port,
                "protocol": "tunnel",
                "settings": {"allowedNetwork": "tcp"},
            }
        )
        tunnel_rules.append(
            {
                "type": "field",
                "inboundTag": [p_tag],
                "outboundTag": r_tag,
            }
        )
    cfg["routing"]["rules"] = tunnel_rules + cfg["routing"]["rules"]
    return cfg


def build_bridge_config(node, reality_profile):
    server_name = reality_server_name(reality_profile)
    target_host = str(node.get("target_host") or "127.0.0.1").strip()
    target_port = int_field(node, "target_port")
    cfg = {
        "log": {"loglevel": "warning"},
        "outbounds": [
            {
                "tag": "direct",
                "protocol": "freedom",
            },
            {
                "tag": BRIDGE_LOCAL_OUTBOUND_TAG,
                "protocol": "freedom",
                "settings": {
                    "redirect": f"{target_host}:{target_port}",
                    "finalRules": [
                        {
                            "action": "allow",
                            "network": "tcp",
                            "ip": target_host,
                            "port": str(target_port),
                        }
                    ],
                },
            },
            {
                "tag": BRIDGE_REVERSE_OUTBOUND_TAG,
                "protocol": "vless",
                "settings": {
                    "address": str(reality_profile.get("address") or "").strip(),
                    "port": int_field(reality_profile, "port", 443),
                    "id": str(node.get("client_id") or "").strip(),
                    "encryption": "none",
                    "flow": flow_for_node(node),
                    "reverse": {"tag": BRIDGE_REVERSE_INBOUND_TAG},
                },
                "streamSettings": {
                    "network": "tcp",
                    "security": "reality",
                    "realitySettings": {
                        "serverName": server_name,
                        "publicKey": str(reality_profile.get("public_key") or "").strip(),
                        "shortId": reality_short_id(reality_profile),
                        "fingerprint": str(reality_profile.get("fingerprint") or "chrome").strip(),
                    },
                },
            },
        ],
        "routing": {
            "domainStrategy": "IPIfNonMatch",
            "rules": [
                {
                    "type": "field",
                    "inboundTag": [BRIDGE_REVERSE_INBOUND_TAG],
                    "outboundTag": BRIDGE_LOCAL_OUTBOUND_TAG,
                }
            ],
        },
    }
    return cfg


def bridge_reverse_in_tag(node):
    return BRIDGE_REVERSE_INBOUND_TAG + "-" + safe_tag(node.get("id"))


def bridge_reverse_out_tag(node):
    return BRIDGE_REVERSE_OUTBOUND_TAG + "-" + safe_tag(node.get("id"))


def bridge_local_out_tag(node):
    return BRIDGE_LOCAL_OUTBOUND_TAG + "-" + safe_tag(node.get("id"))


def build_shared_bridge_config(nodes, reality_profile):
    server_name = reality_server_name(reality_profile)
    cfg = {
        "log": {"loglevel": "warning"},
        "outbounds": [
            {
                "tag": "direct",
                "protocol": "freedom",
            }
        ],
        "routing": {
            "domainStrategy": "IPIfNonMatch",
            "rules": [],
        },
    }
    seen_tags = {"direct"}
    for node in enabled_nodes(nodes):
        node_id = str(node.get("id") or "").strip()
        target_host = str(node.get("target_host") or "127.0.0.1").strip()
        target_port = int_field(node, "target_port")
        local_tag = bridge_local_out_tag(node)
        reverse_out = bridge_reverse_out_tag(node)
        reverse_in = bridge_reverse_in_tag(node)
        for tag in (local_tag, reverse_out, reverse_in):
            if tag in seen_tags:
                raise RuntimeError(f"shared bridge tag is duplicated for {node_id}")
            seen_tags.add(tag)
        cfg["outbounds"].append(
            {
                "tag": local_tag,
                "protocol": "freedom",
                "settings": {
                    "redirect": f"{target_host}:{target_port}",
                    "finalRules": [
                        {
                            "action": "allow",
                            "network": "tcp",
                            "ip": target_host,
                            "port": str(target_port),
                        }
                    ],
                },
            }
        )
        cfg["outbounds"].append(
            {
                "tag": reverse_out,
                "protocol": "vless",
                "settings": {
                    "address": str(reality_profile.get("address") or "").strip(),
                    "port": int_field(reality_profile, "port", 443),
                    "id": str(node.get("client_id") or "").strip(),
                    "encryption": "none",
                    "flow": flow_for_node(node),
                    "reverse": {"tag": reverse_in},
                },
                "streamSettings": {
                    "network": "tcp",
                    "security": "reality",
                    "realitySettings": {
                        "serverName": server_name,
                        "publicKey": str(reality_profile.get("public_key") or "").strip(),
                        "shortId": reality_short_id(reality_profile),
                        "fingerprint": str(reality_profile.get("fingerprint") or "chrome").strip(),
                    },
                },
            }
        )
        cfg["routing"]["rules"].append(
            {
                "type": "field",
                "inboundTag": [reverse_in],
                "outboundTag": local_tag,
            }
        )
    return cfg
