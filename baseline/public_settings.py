import store_facade
import email_settings
from repositories.sqlite_settings import SQLiteSettingsRepository


DEFAULTS = {
    "registration_enabled": False,
    "password_reset_enabled": False,
    "email_provider": "",
    "smtp_configured": False,
}


def read():
    store_facade.ensure_sqlite()
    data = dict(DEFAULTS)
    saved = SQLiteSettingsRepository().get("public_settings", {})
    if isinstance(saved, dict):
        data.update(saved)
    data["registration_enabled"] = bool(data.get("registration_enabled", False))
    data["password_reset_enabled"] = bool(data.get("password_reset_enabled", False))
    email_public = email_settings.public_view()
    data["email_provider"] = email_public.get("email_provider", "")
    data["smtp_configured"] = bool(email_public.get("smtp_configured", False))
    return data


def update(data):
    store_facade.ensure_sqlite()
    current = read()
    if "registration_enabled" in (data or {}):
        value = data.get("registration_enabled")
        if isinstance(value, str):
            value = value.lower() in {"1", "true", "yes", "y", "on"}
        current["registration_enabled"] = bool(value)
    if "password_reset_enabled" in (data or {}):
        value = data.get("password_reset_enabled")
        if isinstance(value, str):
            value = value.lower() in {"1", "true", "yes", "y", "on"}
        current["password_reset_enabled"] = bool(value)
    SQLiteSettingsRepository().set("public_settings", current)
    return current
