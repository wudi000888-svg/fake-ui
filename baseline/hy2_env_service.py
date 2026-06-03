import os
import secrets

from panel_config import HY2_ENV_FILE, HY2_TRAFFIC_SECRET_FILE


def read_env():
    data = {}
    if not HY2_ENV_FILE.exists():
        raise RuntimeError("未找到 /opt/hysteria2/.env")
    for line in HY2_ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    if not data.get("HY_DOMAIN") or not data.get("HY_PASSWORD"):
        raise RuntimeError("/opt/hysteria2/.env 缺少 HY_DOMAIN 或 HY_PASSWORD")
    data.setdefault("HY_PORT", "443")
    return data


def traffic_secret():
    if HY2_TRAFFIC_SECRET_FILE.exists():
        secret = HY2_TRAFFIC_SECRET_FILE.read_text(encoding="utf-8").strip()
        if secret:
            return secret
    secret = secrets.token_urlsafe(32)
    HY2_TRAFFIC_SECRET_FILE.write_text(secret + "\n", encoding="utf-8")
    os.chmod(HY2_TRAFFIC_SECRET_FILE, 0o600)
    return secret
