import os
from pathlib import Path


def env_path(name, default):
    return Path(os.getenv(name, str(default)))


def env_int(name, default):
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return int(default)


APP_DIR = env_path("PANEL_APP_DIR", Path(__file__).resolve().parent)
HOST = os.getenv("PANEL_HOST", "127.0.0.1")
PORT = env_int("PANEL_PORT", 9100)
PANEL_DOMAIN = os.getenv("PANEL_DOMAIN", "panel.example.com")
HY2_DOMAIN = os.getenv("HY2_DOMAIN", "hy2.example.com")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", f"https://{PANEL_DOMAIN}").rstrip("/")
DEFAULT_VLESS_ADDRESS = os.getenv("DEFAULT_VLESS_ADDRESS", "vless.example.com")
DEFAULT_VLESS_NAME = os.getenv("DEFAULT_VLESS_NAME", f"VLESS_Reality_{DEFAULT_VLESS_ADDRESS}")
DEFAULT_HY2_NAME = os.getenv("DEFAULT_HY2_NAME", f"HY2_{HY2_DOMAIN}")
HY2_MASQUERADE_URL = os.getenv("HY2_MASQUERADE_URL", "https://example.com")
QR_CMD = os.getenv("QR_CMD", "qrencode")

PANEL_DIR = env_path("PANEL_DIR", "/opt/xray-proxy-panel")
AUTH_FILE = PANEL_DIR / "auth.json"
LINK_SETTINGS_FILE = PANEL_DIR / "link_settings.json"
SUB_TOKEN_FILE = PANEL_DIR / "sub_token.txt"
USERS_FILE = PANEL_DIR / "users.json"
PLANS_FILE = PANEL_DIR / "plans.json"
ORDERS_FILE = PANEL_DIR / "orders.json"
AUDIT_LOG_FILE = PANEL_DIR / "audit.log"
NODE_CATALOG_FILE = PANEL_DIR / "nodes.json"
ADMIN_PROFILE_FILE = PANEL_DIR / "admin_profile.json"
BACKUP_DIR = PANEL_DIR / "backups"
REGISTRATION_FILE = PANEL_DIR / "registrations.json"
SUB_ACCESS_LOG_FILE = PANEL_DIR / "subscription_access.log"
HY2_TRAFFIC_SECRET_FILE = PANEL_DIR / "hy2_traffic_secret.txt"

LOGIN_FILE = env_path("LOGIN_FILE", "/root/xray-proxy-panel-login.txt")
USER_LOGIN_FILE = env_path("USER_LOGIN_FILE", "/root/xray-proxy-panel-user-login.txt")
AIRPORT_LOGIN_LOG = env_path("AIRPORT_LOGIN_LOG", "/root/xray-proxy-panel-airport-users.txt")

XRAY_BIN = os.getenv("XRAY_BIN", "xray")
XRAY_API_SERVER = os.getenv("XRAY_API_SERVER", "127.0.0.1:10085")
XRAY_CONFIG = env_path("XRAY_CONFIG", "/usr/local/etc/xray/config.json")
XRAY_BACKUP_DIR = env_path("XRAY_BACKUP_DIR", "/root/xray-config-backups")
XRAY_RESTART_CMD = os.getenv("XRAY_RESTART_CMD", "systemctl restart xray")
XRAY_STATUS_CMD = os.getenv("XRAY_STATUS_CMD", "systemctl is-active xray")
INBOUND_TAG = "vless-reality-in"
MANAGED_PREFIX = "panel-user:"

HY2_DIR = env_path("HY2_DIR", "/opt/hysteria2")
HY2_ENV_FILE = env_path("HY2_ENV_FILE", HY2_DIR / ".env")
HY2_CONFIG_FILE = env_path("HY2_CONFIG_FILE", HY2_DIR / "server.yaml")
HY2_BACKUP_DIR = env_path("HY2_BACKUP_DIR", "/root/hysteria2-config-backups")
HY2_RESTART_CMD = os.getenv("HY2_RESTART_CMD", "docker compose -f /opt/hysteria2/docker-compose.yml restart hysteria2")
HY2_STATUS_CMD = os.getenv("HY2_STATUS_CMD", 'docker inspect -f "{{.State.Running}}" hysteria2')
HY2_LOGS_CMD = os.getenv("HY2_LOGS_CMD", "docker logs --tail=80 hysteria2")

QUOTA_COLLECT_CMD = os.getenv("QUOTA_COLLECT_CMD", f"python3 {APP_DIR / 'quota_collect.py'}")
ENFORCE_USERS_CMD = os.getenv("ENFORCE_USERS_CMD", f"python3 {APP_DIR / 'enforce_users.py'}")

SESSION_TTL = 30 * 24 * 3600
