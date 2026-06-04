import secrets
from copy import deepcopy
from datetime import datetime, timezone

import payment_wallets
from json_store import load_json, save_json
from panel_config import PAYMENTS_FILE


PUBLIC_METHOD_FIELDS = {
    "id",
    "label",
    "asset",
    "chain",
    "address",
    "decimals",
    "confirmations_required",
    "enabled",
    "sort",
    "created_at",
    "updated_at",
}
SECRET_PAYMENT_FIELDS = {"internal_note"}
DEFAULT_PAYMENT_STATUS = "awaiting_payment"


def default_payments():
    return {
        "version": 1,
        "methods": [],
        "payments": [],
        "rates": {"overrides": {}, "cache": {}},
    }


def _ensure_shape(data):
    if not isinstance(data, dict):
        data = default_payments()
    data.setdefault("version", 1)
    data.setdefault("methods", [])
    data.setdefault("payments", [])
    data.setdefault("rates", {"overrides": {}, "cache": {}})
    data["rates"].setdefault("overrides", {})
    data["rates"].setdefault("cache", {})
    return data


def public_method(method, admin=False):
    view = deepcopy(method)
    if not admin:
        view = {k: v for k, v in view.items() if k in PUBLIC_METHOD_FIELDS}
    return view


def public_payment(payment, admin=False):
    view = deepcopy(payment)
    if not admin:
        view = {k: v for k, v in view.items() if k not in SECRET_PAYMENT_FIELDS}
    return view


def _new_payment_id():
    return f"pay_{secrets.token_urlsafe(12)}"


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _find_method(data, method_id):
    for index, method in enumerate(data["methods"]):
        if method.get("id") == method_id:
            return index, method
    return None, None


def _find_payment(data, payment_id):
    for index, payment in enumerate(data["payments"]):
        if payment.get("id") == payment_id:
            return index, payment
    return None, None


def load_payments():
    return _ensure_shape(load_json(PAYMENTS_FILE, default_payments, create=True))


def save_payments(data):
    return save_json(PAYMENTS_FILE, _ensure_shape(data))


def list_methods(admin=False):
    data = load_payments()
    methods = data["methods"]
    if not admin:
        methods = [method for method in methods if method.get("enabled")]
    return [public_method(method, admin=admin) for method in methods]


def get_method(method_id):
    data = load_payments()
    _, method = _find_method(data, method_id)
    if not method:
        return None
    return deepcopy(method)


def upsert_method(method):
    data = load_payments()
    item = payment_wallets.normalize_method(method)

    index, existing = _find_method(data, item["id"])
    if index is None:
        item.setdefault("created_at", _now_iso())
        data["methods"].append(item)
    else:
        if existing.get("created_at"):
            item["created_at"] = existing["created_at"]
        data["methods"][index] = item
    item["updated_at"] = _now_iso()
    save_payments(data)
    return deepcopy(item)


def set_method_enabled(method_id, enabled):
    data = load_payments()
    index, method = _find_method(data, method_id)
    if method is None:
        raise RuntimeError("payment method not found")
    data["methods"][index]["enabled"] = bool(enabled)
    save_payments(data)
    return deepcopy(data["methods"][index])


def delete_method(method_id):
    data = load_payments()
    original_len = len(data["methods"])
    data["methods"] = [method for method in data["methods"] if method.get("id") != method_id]
    if len(data["methods"]) == original_len:
        raise RuntimeError("payment method not found")
    save_payments(data)
    return True


def list_payments(username=None, admin=False, limit=200):
    if not admin and username is None:
        return []
    data = load_payments()
    payments = data["payments"]
    if username is not None:
        payments = [payment for payment in payments if payment.get("username") == username]
    payments = sorted(payments, key=lambda payment: payment.get("created_at", ""), reverse=True)
    if limit is not None:
        payments = payments[: int(limit)]
    return [public_payment(payment, admin=admin) for payment in payments]


def get_payment(payment_id):
    data = load_payments()
    _, payment = _find_payment(data, payment_id)
    return deepcopy(payment) if payment else None


def txid_used(txid, exclude_payment_id=None):
    normalized = str(txid or "").strip().lower()
    if not normalized:
        return False
    data = load_payments()
    for payment in data["payments"]:
        if exclude_payment_id and payment.get("id") == exclude_payment_id:
            continue
        existing = str(payment.get("txid") or "").strip().lower()
        if existing == normalized:
            return True
    return False


def create_payment(payment):
    data = load_payments()
    item = dict(payment)
    item.setdefault("id", _new_payment_id())
    while any(existing.get("id") == item["id"] for existing in data["payments"]):
        item["id"] = _new_payment_id()
    item.setdefault("status", DEFAULT_PAYMENT_STATUS)
    item.setdefault("created_at", _now_iso())
    item.setdefault("updated_at", item["created_at"])
    data["payments"].append(item)
    save_payments(data)
    return deepcopy(item)


def update_payment(payment_id, **updates):
    if "txid" in updates:
        normalized_txid = str(updates.get("txid") or "").strip()
        if not normalized_txid:
            raise RuntimeError("txid required")
        if txid_used(normalized_txid, exclude_payment_id=payment_id):
            raise RuntimeError("txid already used")
        updates["txid"] = normalized_txid

    data = load_payments()
    index, payment = _find_payment(data, payment_id)
    if payment is None:
        raise RuntimeError("payment not found")
    updated = dict(payment)
    updated.update(dict(updates))
    updated["id"] = payment_id
    updated["updated_at"] = _now_iso()
    data["payments"][index] = updated
    save_payments(data)
    return deepcopy(updated)


def attach_txid(payment_id, txid):
    normalized = str(txid or "").strip()
    if not normalized:
        raise RuntimeError("txid required")
    if txid_used(normalized, exclude_payment_id=payment_id):
        raise RuntimeError("txid already used")
    return update_payment(payment_id, txid=normalized)


def load_rates():
    return deepcopy(load_payments()["rates"])


def save_rates(rates):
    data = load_payments()
    data["rates"] = dict(rates or {})
    data["rates"].setdefault("overrides", {})
    data["rates"].setdefault("cache", {})
    save_payments(data)
    return deepcopy(data["rates"])
