import secrets
from datetime import datetime, timedelta, timezone

from panel_config import REGISTRATION_FILE
from json_store import load_json, save_json


def now_utc():
    return datetime.now(timezone.utc)


def now_iso():
    return now_utc().isoformat()


def load_data():
    return load_json(REGISTRATION_FILE, {"version": 1, "pending": [], "resets": []}, create=True)


def save_data(data):
    save_json(REGISTRATION_FILE, data)


def create_registration(username, password, email="", plan_id="", note=""):
    username = username.strip()
    if not username:
        raise RuntimeError("username is required")
    if not username.replace("_", "").replace("-", "").isalnum():
        raise RuntimeError("username can only contain letters, numbers, underscore and dash")
    if len(password or "") < 8:
        raise RuntimeError("password must be at least 8 characters")
    token = secrets.token_hex(24)
    item = {
        "token": token,
        "username": username,
        "password": password,
        "email": email.strip(),
        "plan_id": plan_id.strip(),
        "note": note,
        "status": "pending",
        "created_at": now_iso(),
        "expires_at": (now_utc() + timedelta(days=7)).isoformat(),
    }
    data = load_data()
    data.setdefault("pending", []).append(item)
    save_data(data)
    return {k: v for k, v in item.items() if k != "password"}


def list_registrations(status=None):
    items = load_data().get("pending", [])
    if status:
        items = [i for i in items if i.get("status") == status]
    return sorted([{k: v for k, v in i.items() if k != "password"} for i in items], key=lambda i: i.get("created_at", ""), reverse=True)


def get_registration(token):
    for item in load_data().get("pending", []):
        if item.get("token") == token:
            return item
    return None


def update_registration(token, **updates):
    data = load_data()
    for item in data.get("pending", []):
        if item.get("token") == token:
            item.update(updates)
            item["updated_at"] = now_iso()
            save_data(data)
            return {k: v for k, v in item.items() if k != "password"}
    raise RuntimeError("registration not found")


def create_password_reset(username):
    token = secrets.token_hex(24)
    item = {
        "token": token,
        "username": username.strip(),
        "status": "pending",
        "created_at": now_iso(),
        "expires_at": (now_utc() + timedelta(hours=24)).isoformat(),
    }
    data = load_data()
    data.setdefault("resets", []).append(item)
    save_data(data)
    return item


def list_resets(status=None):
    items = load_data().get("resets", [])
    if status:
        items = [i for i in items if i.get("status") == status]
    return sorted(items, key=lambda i: i.get("created_at", ""), reverse=True)


def get_reset(token):
    for item in load_data().get("resets", []):
        if item.get("token") == token:
            return item
    return None


def update_reset(token, **updates):
    data = load_data()
    for item in data.get("resets", []):
        if item.get("token") == token:
            item.update(updates)
            item["updated_at"] = now_iso()
            save_data(data)
            return item
    raise RuntimeError("reset request not found")
