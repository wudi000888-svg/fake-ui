import os
import re
import socket
import urllib.parse


IP_RE = re.compile(r"^\d+(?:\.\d+){3}$")


def clean_domain(value):
    domain = str(value or "").strip().lower().rstrip(".")
    if not domain:
        return ""
    if IP_RE.fullmatch(domain):
        return ""
    if "." not in domain:
        return ""
    return domain


def split_domains(value):
    result = []
    seen = set()
    for item in re.split(r"[\s,;]+", str(value or "")):
        domain = clean_domain(item)
        if domain and domain not in seen:
            result.append(domain)
            seen.add(domain)
    return result


def domain_from_url(value):
    raw = str(value or "").strip()
    if not raw:
        return ""
    if "://" not in raw:
        raw = "https://" + raw
    try:
        parsed = urllib.parse.urlparse(raw)
    except Exception:
        return ""
    return clean_domain(parsed.hostname or "")


def resolve_ips(domain):
    try:
        infos = socket.getaddrinfo(domain, None, proto=socket.IPPROTO_TCP)
    except Exception:
        return []
    ips = []
    for info in infos:
        address = (info[4] or [""])[0]
        if address and address not in ips:
            ips.append(address)
    return ips


def server_ips_from_env(default_address=""):
    raw_env = os.getenv("TUNNEL_SERVER_IPS", "")
    env_domains = split_domains(raw_env)
    literal_ips = [
        item
        for item in re.split(r"[\s,;]+", raw_env)
        if IP_RE.fullmatch(str(item or "").strip())
    ]
    ips = []
    for ip in literal_ips:
        if ip not in ips:
            ips.append(ip)
    if str(raw_env or "").strip():
        for domain in env_domains:
            for ip in resolve_ips(domain):
                if ip not in ips:
                    ips.append(ip)
        return ips
    for value in panel_domains_from_env():
        domain = clean_domain(value)
        if not domain:
            continue
        for ip in resolve_ips(domain):
            if ip not in ips:
                ips.append(ip)
    return ips


def panel_domains_from_env():
    return [
        domain
        for domain in [
            clean_domain(os.getenv("PANEL_DOMAIN", "")),
            domain_from_url(os.getenv("PUBLIC_BASE_URL", "")),
        ]
        if domain
    ]


def hy2_reserved_domains(hy2_env_loader=None):
    domains = []
    for value in [os.getenv("HY2_DOMAIN", ""), os.getenv("HY_DOMAIN", "")]:
        domain = clean_domain(value)
        if domain and domain not in domains:
            domains.append(domain)
    if hy2_env_loader:
        try:
            env = hy2_env_loader() or {}
        except Exception:
            env = {}
        domain = clean_domain(env.get("HY_DOMAIN"))
        if domain and domain not in domains:
            domains.append(domain)
    return domains


def candidate_domains(tunnels=None, extra=()):
    values = []
    values.extend(split_domains(os.getenv("TUNNEL_DOMAIN_CANDIDATES", "")))
    values.extend(split_domains(os.getenv("TUNNEL_DOMAIN_SUFFIXES", "")))
    values.extend(clean_domain(item) for item in extra or [])
    values.extend(clean_domain((item or {}).get("public_domain")) for item in tunnels or [])
    result = []
    seen = set()
    for domain in values:
        if domain and domain not in seen:
            result.append(domain)
            seen.add(domain)
    return result


def node_reserved_domains(nodes):
    keys = (
        "address",
        "domain",
        "server",
        "server_name",
        "host",
        "sni",
        "reality_sni",
        "proxy_addr",
    )
    domains = []
    seen = set()
    for node in nodes or []:
        for key in keys:
            domain = clean_domain((node or {}).get(key))
            if domain and domain not in seen:
                domains.append(domain)
                seen.add(domain)
    return domains


def tunnel_domains(tunnels):
    return [
        domain
        for domain in [clean_domain((item or {}).get("public_domain")) for item in tunnels or []]
        if domain
    ]


def classify_domain(domain, server_ips, panel_domains=(), node_domains=(), tunnels=(), nodes=(), exclude_tunnel_id=""):
    domain = clean_domain(domain)
    if not domain:
        return {"domain": "", "status": "invalid", "reason": "invalid_domain", "ips": []}

    panel_set = {clean_domain(item) for item in panel_domains or [] if clean_domain(item)}
    node_set = {clean_domain(item) for item in node_domains or [] if clean_domain(item)}
    node_set.update(node_reserved_domains(nodes))
    tunnel_set = {
        clean_domain((item or {}).get("public_domain"))
        for item in tunnels or []
        if str((item or {}).get("id", "")) != str(exclude_tunnel_id or "")
    }
    tunnel_set.discard("")

    if domain in panel_set:
        return {"domain": domain, "status": "reserved", "reason": "reserved_panel_domain", "ips": []}
    if domain in node_set:
        return {"domain": domain, "status": "reserved", "reason": "reserved_node_domain", "ips": []}
    if domain in tunnel_set:
        return {"domain": domain, "status": "reserved", "reason": "already_used_by_tunnel", "ips": []}

    ips = resolve_ips(domain)
    server_set = {str(ip).strip() for ip in server_ips or [] if str(ip).strip()}
    if server_set and not (set(ips) & server_set):
        return {"domain": domain, "status": "unresolved", "reason": "not_resolved_to_server", "ips": ips}
    if not ips:
        return {"domain": domain, "status": "unresolved", "reason": "not_resolved_to_server", "ips": []}
    return {"domain": domain, "status": "resolved", "reason": "", "ips": ips}


def domain_options(
    candidates,
    server_ips,
    panel_domains=(),
    node_domains=(),
    tunnels=(),
    nodes=(),
    exclude_tunnel_id="",
):
    available = []
    unavailable = []
    seen = set()
    for candidate in candidates or []:
        domain = clean_domain(candidate)
        if not domain or domain in seen:
            continue
        seen.add(domain)
        item = classify_domain(
            domain,
            server_ips,
            panel_domains=panel_domains,
            node_domains=node_domains,
            tunnels=tunnels,
            nodes=nodes,
            exclude_tunnel_id=exclude_tunnel_id,
        )
        if item["status"] == "resolved":
            available.append(item)
        else:
            unavailable.append(item)
    return {"available": available, "unavailable": unavailable, "server_ips": list(server_ips or [])}


def validate_tunnel_domain(domain, server_ips, panel_domains=(), node_domains=(), tunnels=(), nodes=(), exclude_tunnel_id=""):
    item = classify_domain(
        domain,
        server_ips,
        panel_domains=panel_domains,
        node_domains=node_domains,
        tunnels=tunnels,
        nodes=nodes,
        exclude_tunnel_id=exclude_tunnel_id,
    )
    reason = item.get("reason")
    if item.get("status") == "resolved":
        return item
    if not server_ips and item.get("reason") == "not_resolved_to_server":
        item = dict(item)
        item["status"] = "unchecked"
        item["reason"] = "server_ip_unknown"
        return item
    if reason == "reserved_panel_domain":
        raise RuntimeError("public domain is reserved for the panel")
    if reason == "reserved_node_domain":
        raise RuntimeError("public domain is reserved for a proxy node")
    if reason == "already_used_by_tunnel":
        raise RuntimeError("public domain is already used by another tunnel")
    if reason == "not_resolved_to_server":
        raise RuntimeError("public domain must resolve to this server before it can be used")
    raise RuntimeError("public domain is invalid")
