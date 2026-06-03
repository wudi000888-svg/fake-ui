import copy

from panel_config import INBOUND_TAG
from proxy_utils import normalize_proxy_type, proxy_auth_enabled


def ensure_xray_inbound(cfg):
    for inbound in cfg.get("inbounds", []):
        if inbound.get("tag") == INBOUND_TAG:
            return inbound
    raise RuntimeError(f"未找到 Xray 入站 tag={INBOUND_TAG}")


def has_private_block(rules):
    for rule in rules:
        if rule.get("outboundTag") == "block" and "geoip:private" in rule.get("ip", []):
            return True
    return False


def has_bt_block(rules):
    for rule in rules:
        if rule.get("outboundTag") == "block" and "bittorrent" in rule.get("protocol", []):
            return True
    return False


def base_route_rules(cfg):
    cfg.setdefault("outbounds", [])
    cfg.setdefault("routing", {})
    cfg["routing"].setdefault("domainStrategy", "IPIfNonMatch")
    cfg["routing"].setdefault("rules", [])

    cfg["outbounds"] = [out for out in cfg["outbounds"] if out.get("tag") != "webshare-out"]

    if not any(out.get("tag") == "direct" for out in cfg["outbounds"]):
        cfg["outbounds"].append({"tag": "direct", "protocol": "freedom", "settings": {"domainStrategy": "UseIPv4"}})

    if not any(out.get("tag") == "block" for out in cfg["outbounds"]):
        cfg["outbounds"].append({"tag": "block", "protocol": "blackhole"})

    new_rules = []
    for rule in cfg["routing"].get("rules", []):
        inbound_tags = rule.get("inboundTag", [])
        if isinstance(inbound_tags, str):
            inbound_tags = [inbound_tags]
        if INBOUND_TAG in inbound_tags:
            continue
        if rule.get("outboundTag") == "webshare-out":
            continue
        new_rules.append(rule)

    if not has_private_block(new_rules):
        new_rules.insert(0, {"type": "field", "ip": ["geoip:private"], "outboundTag": "block"})
    if not has_bt_block(new_rules):
        new_rules.append({"type": "field", "protocol": ["bittorrent"], "outboundTag": "block"})

    return new_rules


def build_proxy_config(cfg, addr, port, user, password, proxy_type="http"):
    cfg = copy.deepcopy(cfg)
    ensure_xray_inbound(cfg)
    proxy_type = normalize_proxy_type(proxy_type)
    port_int = int(port)
    new_rules = base_route_rules(cfg)

    server = {"address": addr.strip(), "port": port_int}
    if proxy_auth_enabled(user, password):
        server["users"] = [{"user": user.strip(), "pass": password.strip()}]

    cfg["outbounds"].insert(
        0,
        {
            "tag": "webshare-out",
            "protocol": "socks" if proxy_type == "socks5" else "http",
            "settings": {"servers": [server]},
        },
    )

    new_rules.append({"type": "field", "inboundTag": [INBOUND_TAG], "network": "tcp", "outboundTag": "webshare-out"})
    new_rules.append({"type": "field", "inboundTag": [INBOUND_TAG], "network": "udp", "outboundTag": "block"})
    cfg["routing"]["rules"] = new_rules
    return cfg


def build_direct_config(cfg):
    cfg = copy.deepcopy(cfg)
    ensure_xray_inbound(cfg)
    new_rules = base_route_rules(cfg)

    direct = None
    block = None
    others = []
    for out in cfg["outbounds"]:
        if out.get("tag") == "direct":
            direct = out
        elif out.get("tag") == "block":
            block = out
        else:
            others.append(out)

    if direct is None:
        direct = {"tag": "direct", "protocol": "freedom", "settings": {"domainStrategy": "UseIPv4"}}
    if block is None:
        block = {"tag": "block", "protocol": "blackhole"}

    cfg["outbounds"] = [direct] + others + [block]
    new_rules.append({"type": "field", "inboundTag": [INBOUND_TAG], "outboundTag": "direct"})
    cfg["routing"]["rules"] = new_rules
    return cfg
