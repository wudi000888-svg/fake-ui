import store_facade
from repositories.sqlite_settings import SQLiteSettingsRepository


KEY = "email_settings"

DEFAULTS = {
    "email_provider": "",
    "smtp_host": "",
    "smtp_port": 587,
    "smtp_username": "",
    "smtp_password": "",
    "smtp_from": "",
    "smtp_tls": True,
}


def _bool(value, default=False):
    if value in (None, ""):
        return default
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def read_private():
    store_facade.ensure_sqlite()
    data = dict(DEFAULTS)
    saved = SQLiteSettingsRepository().get(KEY, {})
    if isinstance(saved, dict):
        data.update(saved)
    try:
        data["smtp_port"] = int(data.get("smtp_port") or 587)
    except Exception:
        data["smtp_port"] = 587
    data["smtp_tls"] = _bool(data.get("smtp_tls"), True)
    return data


def public_view(settings=None):
    data = dict(settings or read_private())
    data.pop("smtp_password", None)
    data["smtp_configured"] = bool(data.get("smtp_host") and (settings or read_private()).get("smtp_password"))
    return data


def update(data):
    store_facade.ensure_sqlite()
    current = read_private()
    incoming = data or {}
    for key in ("email_provider", "smtp_host", "smtp_username", "smtp_from"):
        if key in incoming:
            current[key] = str(incoming.get(key) or "").strip()
    if "smtp_port" in incoming:
        current["smtp_port"] = int(incoming.get("smtp_port") or 587)
    if "smtp_tls" in incoming:
        current["smtp_tls"] = _bool(incoming.get("smtp_tls"), True)
    if str(incoming.get("smtp_password") or ""):
        current["smtp_password"] = str(incoming.get("smtp_password") or "")
    SQLiteSettingsRepository().set(KEY, current)
    return public_view(current)
