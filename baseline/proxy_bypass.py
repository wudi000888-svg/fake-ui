import ipaddress
import os
import re

import hy2_env_service


def clean_host(value):
    host = str(value or "").strip().strip("[]").rstrip(".")
    if not host:
        return ""
    if "/" in host:
        host = host.split("/", 1)[0].strip()
    if ":" in host and not re.fullmatch(r"\d+(?:\.\d+){3}", host):
        host = host.rsplit(":", 1)[0].strip("[]")
    return host


def is_ip(value):
    try:
        ipaddress.ip_address(clean_host(value))
        return True
    except ValueError:
        return False


def first_server_ip():
    for raw in str(os.getenv("TUNNEL_SERVER_IPS", "") or "").split(","):
        host = clean_host(raw)
        if host and is_ip(host):
            return host
    return ""


def host_rule(host):
    host = clean_host(host)
    if not host:
        return ""
    if is_ip(host):
        return f"IP-CIDR,{host}/32,DIRECT,no-resolve"
    return f"DOMAIN,{host},DIRECT"


def clash_rule(host):
    host = clean_host(host)
    if not host:
        return ""
    if is_ip(host):
        return f"IP-CIDR,{host}/32,DIRECT,no-resolve"
    return f"DOMAIN,{host},DIRECT"


def sing_box_rule(host):
    host = clean_host(host)
    if not host:
        return ""
    if is_ip(host):
        return f'{{ "ip_cidr": ["{host}/32"], "outbound": "direct" }}'
    return f'{{ "domain": ["{host}"], "outbound": "direct" }}'


def dedupe(lines):
    result = []
    seen = set()
    for line in lines:
        text = str(line or "").strip()
        if text and text not in seen:
            result.append(text)
            seen.add(text)
    return result


def templates(connect_host="", sni="", process_names=()):
    connect_host = clean_host(connect_host)
    sni = clean_host(sni)
    shadowrocket = dedupe([host_rule(sni), host_rule(connect_host)])
    clash = dedupe([*(f"PROCESS-NAME,{name},DIRECT" for name in process_names), clash_rule(sni), clash_rule(connect_host)])
    surge = dedupe([host_rule(sni), host_rule(connect_host)])
    sing_box = dedupe([sing_box_rule(sni), sing_box_rule(connect_host)])
    v2rayn = dedupe(
        [
            "在路由设置里把以下目标设为直连：",
            sni,
            connect_host,
            "如果客户端支持进程规则，也把 hysteria / xray / fake-ui bridge 进程设为直连。",
        ]
    )
    return {
        "Shadowrocket": "\n".join(shadowrocket),
        "Clash / Mihomo": "\n".join(clash),
        "Surge": "\n".join(surge),
        "sing-box": "[\n  " + ",\n  ".join(sing_box) + "\n]" if sing_box else "[]",
        "v2rayN / NekoRay": "\n".join(v2rayn),
    }


def guide(transport, connect_host="", sni="", port=443, process_names=()):
    connect_host = clean_host(connect_host)
    sni = clean_host(sni)
    return {
        "transport": transport,
        "connect_host": connect_host,
        "sni": sni,
        "port": int(port or 443),
        "direct_rules": dedupe([host_rule(sni), host_rule(connect_host)]),
        "process_names": list(process_names or []),
        "templates": templates(connect_host, sni, process_names),
        "note": "本地代理或 TUN 开启时，请让这些域名、IP 或客户端进程走 DIRECT。",
    }


def desktop_endpoint():
    try:
        env = hy2_env_service.read_env()
    except RuntimeError:
        env = {}
    domain = clean_host(env.get("HY_DOMAIN", ""))
    port = int(os.getenv("HY2_PORT") or os.getenv("HY_PORT") or env.get("HY_PORT", "443") or 443)
    sni = clean_host(os.getenv("HY2_SNI") or os.getenv("HY_SNI") or env.get("HY_SNI") or domain)
    connect_host = clean_host(os.getenv("HY2_CONNECT_HOST") or os.getenv("HY_CONNECT_HOST") or first_server_ip() or domain)
    return {"connect_host": connect_host, "sni": sni, "port": port, "domain": domain}


def desktop_proxy_bypass():
    endpoint = desktop_endpoint()
    return guide(
        "hysteria2_udp_443",
        connect_host=endpoint.get("connect_host"),
        sni=endpoint.get("sni"),
        port=endpoint.get("port"),
        process_names=["hysteria", "hysteria.exe", "wireguard", "wireguard.exe"],
    )


def reverse_addresses(config):
    values = []
    for outbound in (config or {}).get("outbounds") or []:
        if outbound.get("protocol") != "vless":
            continue
        if not str(outbound.get("tag") or "").startswith("tunnel-reverse"):
            continue
        settings = outbound.get("settings") or {}
        address = clean_host(settings.get("address"))
        if address and address not in values:
            values.append(address)
    return values


def reality_sni(config):
    for outbound in (config or {}).get("outbounds") or []:
        stream = outbound.get("streamSettings") or {}
        if stream.get("security") != "reality":
            continue
        reality = stream.get("realitySettings") or {}
        server_name = reality.get("serverName") or reality.get("server_name")
        if server_name:
            return clean_host(server_name)
        names = reality.get("serverNames") or []
        if names:
            return clean_host(names[0])
    return ""


def tcp_reality_proxy_bypass(config):
    addresses = reverse_addresses(config)
    connect_host = addresses[0] if addresses else first_server_ip()
    sni = reality_sni(config) or connect_host
    return guide(
        "tcp_reality",
        connect_host=connect_host,
        sni=sni,
        port=443,
        process_names=["xray", "xray.exe", "fake-ui bridge"],
    )
