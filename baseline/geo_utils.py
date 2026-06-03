import json

from hy2_panel import normalize_proxy_type, proxy_auth_enabled
from sync_utils import run


COUNTRY_NAMES = {
    "HK": "Hong Kong",
    "SG": "Singapore",
    "US": "United States",
    "JP": "Japan",
    "TW": "Taiwan",
    "KR": "South Korea",
    "GB": "United Kingdom",
    "DE": "Germany",
    "FR": "France",
    "NL": "Netherlands",
    "TR": "Turkey",
    "CA": "Canada",
    "AU": "Australia",
}


def country_name(code):
    code = str(code or "").strip().upper()
    return COUNTRY_NAMES.get(code, code)


def parse_ipinfo(raw):
    text = (raw or "").strip()
    if not text:
        raise RuntimeError("出口检测没有返回内容。")
    try:
        data = json.loads(text)
    except Exception:
        data = {"ip": text.splitlines()[-1].strip()}
    ip = str(data.get("ip") or "").strip()
    if not ip:
        raise RuntimeError("出口检测没有拿到 IP。")
    code = str(data.get("country") or "").strip().upper()
    return {
        "ip": ip,
        "country_code": code,
        "country": country_name(code),
        "city": str(data.get("city") or "").strip(),
    }


def direct_exit_info():
    code, out = run(["curl", "-4sS", "--connect-timeout", "10", "--max-time", "20", "https://ipinfo.io/json"], timeout=30)
    if code == 0 and (out or "").strip():
        try:
            return parse_ipinfo(out)
        except Exception:
            pass
    code, out = run(["curl", "-4sS", "--connect-timeout", "10", "--max-time", "20", "https://api.ipify.org"], timeout=30)
    if code != 0:
        raise RuntimeError(f"直连出口检测失败。\n\ncurl 返回码：{code}\n\ncurl 输出：\n{(out or '').strip()}")
    return parse_ipinfo(out)


def proxy_exit_info(addr, port, user="", password="", proxy_type="http"):
    proxy_type = normalize_proxy_type(proxy_type)
    proxy_scheme = "socks5h" if proxy_type == "socks5" else "http"
    cmd = [
        "curl",
        "-4sS",
        "--connect-timeout",
        "15",
        "--max-time",
        "30",
        "--proxy",
        f"{proxy_scheme}://{addr}:{int(port)}",
    ]
    if proxy_auth_enabled(user or "", password or ""):
        cmd += ["--proxy-user", f"{str(user).strip()}:{str(password).strip()}"]
    cmd.append("https://ipinfo.io/json")

    code, out = run(cmd, timeout=40)
    if code == 0 and (out or "").strip():
        try:
            return parse_ipinfo(out)
        except Exception:
            pass
    fallback = list(cmd)
    fallback[-1] = "https://api.ipify.org"
    code, out = run(fallback, timeout=40)
    if code != 0:
        raise RuntimeError(f"代理出口检测失败。\n\ncurl 返回码：{code}\n\ncurl 输出：\n{(out or '').strip()}")
    return parse_ipinfo(out)
