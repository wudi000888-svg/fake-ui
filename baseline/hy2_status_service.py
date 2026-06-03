import urllib.parse

import hy2_env_service
from panel_config import HY2_CONFIG_FILE, HY2_LOGS_CMD, HY2_STATUS_CMD
from sync_utils import run_shell


def status():
    env = hy2_env_service.read_env()
    text = HY2_CONFIG_FILE.read_text(encoding="utf-8") if HY2_CONFIG_FILE.exists() else ""
    proxy_type = ""
    if "type: socks5" in text and "socks5-proxy" in text:
        proxy_type = "SOCKS5"
    elif "type: http" in text and "http-proxy" in text:
        proxy_type = "HTTP"
    enabled = bool(proxy_type)
    proxy = "未配置"
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("url: http://") or line.startswith("url: socks5://"):
            proxy = line.replace("url: ", "")
            break
    code, running = run_shell(HY2_STATUS_CMD, timeout=15)
    code2, logs = run_shell(HY2_LOGS_CMD, timeout=15)
    return {
        "domain": env.get("HY_DOMAIN", ""),
        "port": env.get("HY_PORT", "443"),
        "enabled": enabled,
        "proxy_type": proxy_type,
        "proxy": proxy,
        "running": running.strip() if code == 0 else "unknown",
        "logs": logs.strip(),
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
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("url: http://") or line.startswith("url: socks5://"):
            url = line.replace("url: ", "", 1)
            parsed = urllib.parse.urlparse(url)
            user = urllib.parse.unquote(parsed.username or "")
            password = urllib.parse.unquote(parsed.password or "")
            return {
                "addr": parsed.hostname or "",
                "port": int(parsed.port or 0),
                "user": user,
                "password": password,
                "type": "socks5" if parsed.scheme.startswith("socks") else "http",
            }
    return {}
