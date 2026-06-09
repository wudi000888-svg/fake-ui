import secrets
from datetime import datetime, timedelta, timezone

import store_facade
import auth_store
from repositories.sqlite_registrations import SQLitePasswordResetsRepository, SQLiteRegistrationsRepository


def now_utc():
    return datetime.now(timezone.utc)


def now_iso():
    return now_utc().isoformat()


def load_data():
    store_facade.ensure_sqlite()
    return {
        "version": 2,
        "pending": SQLiteRegistrationsRepository().list(),
        "resets": SQLitePasswordResetsRepository().list(),
    }


def save_data(data):
    store_facade.ensure_sqlite()
    reg_repo = SQLiteRegistrationsRepository()
    reset_repo = SQLitePasswordResetsRepository()
    for item in (data or {}).get("pending", []):
        reg_repo.upsert(item)
    for item in (data or {}).get("resets", []):
        reset_repo.upsert(item)
    return data


def build_registration_item(username, password, email="", plan_id="", note=""):
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
        "password_hash": auth_store.make_password_hash(password),
        "email": email.strip(),
        "plan_id": plan_id.strip(),
        "note": note,
        "status": "pending",
        "created_at": now_iso(),
        "expires_at": (now_utc() + timedelta(days=7)).isoformat(),
    }
    return item


def create_registration(username, password, email="", plan_id="", note=""):
    store_facade.ensure_sqlite()
    item = build_registration_item(username, password, email, plan_id, note)
    SQLiteRegistrationsRepository().upsert(item)
    return {k: v for k, v in item.items() if k != "password"}


def list_registrations(status=None):
    items = load_data().get("pending", [])
    if status:
        items = [i for i in items if i.get("status") == status]
    return sorted([{k: v for k, v in i.items() if k != "password"} for i in items], key=lambda i: i.get("created_at", ""), reverse=True)


def get_registration(token):
    return SQLiteRegistrationsRepository().get(token)


def update_registration(token, **updates):
    item = SQLiteRegistrationsRepository().update(token, **updates, updated_at=now_iso())
    return {k: v for k, v in item.items() if k != "password"}


def create_password_reset(username):
    token = secrets.token_hex(24)
    item = {
        "token": token,
        "username": username.strip(),
        "status": "pending",
        "created_at": now_iso(),
        "expires_at": (now_utc() + timedelta(hours=24)).isoformat(),
    }
    SQLitePasswordResetsRepository().upsert(item)
    return item


def save_password_reset(item):
    return SQLitePasswordResetsRepository().upsert(item)


def list_resets(status=None):
    items = load_data().get("resets", [])
    if status:
        items = [i for i in items if i.get("status") == status]
    return sorted(items, key=lambda i: i.get("created_at", ""), reverse=True)


def get_reset(token):
    return SQLitePasswordResetsRepository().get(token)


def update_reset(token, **updates):
    return SQLitePasswordResetsRepository().update(token, **updates, updated_at=now_iso())
