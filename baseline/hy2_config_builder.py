import secrets
import urllib.parse

import hy2_env_service
import user_store
import desktop_config_builder
from panel_config import HY2_MASQUERADE_URL
from proxy_utils import normalize_proxy_type, proxy_auth_enabled


def active_auth_users():
    data = user_store.load_users()
    changed = False
    result = {}

    for username, user in data.setdefault("users", {}).items():
        if not user.get("hy2_username"):
            user["hy2_username"] = username
            changed = True
        if not user.get("hy2_password"):
            user["hy2_password"] = secrets.token_urlsafe(18)
            changed = True
        user.setdefault("last_hy2_stats", {"tx": 0, "rx": 0})

        if user_store.user_is_active(username, user):
            result[user["hy2_username"]] = user["hy2_password"]

    if changed:
        user_store.save_users(data)

    return result


def build_config(mode="direct", addr="", port="", user="", password="", proxy_type="http"):
    env = hy2_env_service.read_env()
    domain = env["HY_DOMAIN"]
    listen_port = env.get("HY_PORT", "443")
    hy_pass = env.get("HY_PASSWORD") or env.get("HY_ADMIN_PASSWORD")
    traffic_secret = hy2_env_service.traffic_secret()

    if not hy_pass:
        raise RuntimeError("未找到 HY_PASSWORD / HY_ADMIN_PASSWORD，无法生成 Hysteria2 配置。")

    auth_users = {"admin": hy_pass}
    auth_users.update(active_auth_users())
    auth_users.update(desktop_config_builder.desktop_auth_users())

    lines = [
        f"listen: :{listen_port}",
        "",
        "tls:",
        f"  cert: /etc/letsencrypt/live/{domain}/fullchain.pem",
        f"  key: /etc/letsencrypt/live/{domain}/privkey.pem",
        "",
        "auth:",
        "  type: userpass",
        "  userpass:",
    ]
    for hy_user, hy_password in auth_users.items():
        lines.append(f"    {hy_user}: {hy_password}")

    lines += [
        "",
        "masquerade:",
        "  type: proxy",
        "  proxy:",
        f"    url: {HY2_MASQUERADE_URL}",
        "    rewriteHost: true",
        "",
        "trafficStats:",
        "  listen: 127.0.0.1:9999",
        f"  secret: {traffic_secret}",
        "",
    ]

    if mode == "http":
        lines.extend(proxy_outbound_lines(addr, port, user, password, proxy_type))
    else:
        lines.extend(direct_outbound_lines())

    return "\n".join(lines)


def proxy_outbound_lines(addr, port, user, password, proxy_type="http"):
    proxy_type = normalize_proxy_type(proxy_type)
    port_int = int(port)
    user = user.strip()
    password = password.strip()
    outbound_type = "socks5" if proxy_type == "socks5" else "http"
    outbound_name = f"{outbound_type}-proxy"

    lines = [
        "outbounds:",
        f"  - name: {outbound_name}",
        f"    type: {outbound_type}",
    ]
    if proxy_type == "http":
        if proxy_auth_enabled(user, password):
            encoded_user = urllib.parse.quote(user, safe="")
            encoded_password = urllib.parse.quote(password, safe="")
            url = f"http://{encoded_user}:{encoded_password}@{addr.strip()}:{port_int}"
        else:
            url = f"http://{addr.strip()}:{port_int}"
        lines += [
            "    http:",
            f"      url: {url}",
            "      insecure: false",
        ]
    else:
        lines += [
            "    socks5:",
            f"      addr: {addr.strip()}:{port_int}",
        ]
        if proxy_auth_enabled(user, password):
            lines += [
                f"      username: {user}",
                f"      password: {password}",
            ]

    lines += [
        "  - name: direct",
        "    type: direct",
        "    direct:",
        "      mode: 4",
        "",
    ]
    return lines


def direct_outbound_lines():
    return [
        "outbounds:",
        "  - name: direct",
        "    type: direct",
        "    direct:",
        "      mode: 4",
        "",
    ]
