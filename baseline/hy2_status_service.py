import urllib.parse

import hy2_env_service
from panel_config import HY2_CONFIG_FILE, HY2_LOGS_CMD, HY2_STATUS_CMD
from sync_utils import run_shell


def _parse_url_proxy(url):
    parsed = urllib.parse.urlparse(url)
    return {
        "addr": parsed.hostname or "",
        "port": int(parsed.port or 0),
        "user": urllib.parse.unquote(parsed.username or ""),
        "password": urllib.parse.unquote(parsed.password or ""),
        "type": "socks5" if parsed.scheme.startswith("socks") else "http",
    }


def _parse_socks5_block(lines, start):
    endpoint = {"addr": "", "port": 0, "user": "", "password": "", "type": "socks5"}
    for raw in lines[start + 1:]:
        stripped = raw.strip()
        if raw.startswith("  - ") or stripped.startswith("type: "):
            break
        if stripped.startswith("addr: "):
            host_port = stripped.replace("addr: ", "", 1).strip()
            if ":" in host_port:
                host, port = host_port.rsplit(":", 1)
                endpoint["addr"] = host.strip()
                endpoint["port"] = int(port.strip() or 0)
        elif stripped.startswith("username: "):
            endpoint["user"] = stripped.replace("username: ", "", 1).strip()
        elif stripped.startswith("password: "):
            endpoint["password"] = stripped.replace("password: ", "", 1).strip()
    return endpoint if endpoint["addr"] and endpoint["port"] else {}


def _format_proxy(endpoint):
    if not endpoint:
        return "未配置"
    user = urllib.parse.quote(endpoint.get("user", ""), safe="")
    password = urllib.parse.quote(endpoint.get("password", ""), safe="")
    auth = f"{user}:{password}@" if user or password else ""
    return f"{endpoint.get('type', 'http')}://{auth}{endpoint.get('addr', '')}:{endpoint.get('port', 0)}"


def _clean_shell_output(value):
    return str(value or "").strip().strip('"').strip("'")


def status():
    env = hy2_env_service.read_env()
    text = HY2_CONFIG_FILE.read_text(encoding="utf-8") if HY2_CONFIG_FILE.exists() else ""
    proxy_type = ""
    if "type: socks5" in text and "socks5-proxy" in text:
        proxy_type = "SOCKS5"
    elif "type: http" in text and "http-proxy" in text:
        proxy_type = "HTTP"
    enabled = bool(proxy_type)
    proxy = _format_proxy(proxy_endpoint())
    code, running = run_shell(HY2_STATUS_CMD, timeout=15)
    code2, logs = run_shell(HY2_LOGS_CMD, timeout=15)
    return {
        "domain": env.get("HY_DOMAIN", ""),
        "port": env.get("HY_PORT", "443"),
        "enabled": enabled,
        "proxy_type": proxy_type,
        "proxy": proxy,
        "running": _clean_shell_output(running) if code == 0 else "unknown",
        "logs": str(logs or "").strip(),
    }


def outbound_mode():
    text = HY2_CONFIG_FILE.read_text(encoding="utf-8") if HY2_CONFIG_FILE.exists() else ""
    if "type: socks5" in text and "socks5-proxy" in text:
        return "socks5"
    if "type: http" in text and "http-proxy" in text:
        return "http"
    return "direct"


def proxy_endpoint():
    text = HY2_CONFIG_FILE.read_text(encoding="utf-8") if HY2_CONFIG_FILE.exists() else ""
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        line = line.strip()
        if line.startswith("url: http://") or line.startswith("url: socks5://"):
            url = line.replace("url: ", "", 1)
            return _parse_url_proxy(url)
        if line == "socks5:":
            endpoint = _parse_socks5_block(lines, idx)
            if endpoint:
                return endpoint
    return {}
