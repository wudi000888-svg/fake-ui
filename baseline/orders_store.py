import secrets
from datetime import datetime, timezone

from panel_config import ORDERS_FILE
from json_store import load_json, save_json


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_orders():
    return load_json(ORDERS_FILE, {"version": 1, "orders": []}, create=True)


def save_orders(data):
    save_json(ORDERS_FILE, data)


def list_orders(username=None, limit=200):
    orders = load_orders().get("orders", [])
    if username:
        orders = [o for o in orders if o.get("username") == username]
    orders = sorted(orders, key=lambda o: o.get("created_at", ""), reverse=True)
    return orders[: int(limit or 200)]


def record_order(username, kind, plan=None, amount=0, status="completed", note="", operator="system"):
    order = {
        "id": "ord_" + secrets.token_hex(8),
        "username": username,
        "kind": kind,
        "plan_id": (plan or {}).get("id", ""),
        "plan_name": (plan or {}).get("name", ""),
        "days": int((plan or {}).get("days", 0) or 0),
        "traffic_gb": float((plan or {}).get("traffic_gb", 0) or 0),
        "amount": float(amount or 0),
        "status": status,
        "note": note,
        "operator": operator,
        "created_at": now_iso(),
    }
    data = load_orders()
    data.setdefault("orders", []).append(order)
    save_orders(data)
    return order


def get_order(order_id):
    for order in load_orders().get("orders", []):
        if order.get("id") == order_id:
            return order
    return None


def create_pending_order(username, kind, plan, note="", operator="user"):
    return record_order(
        username=username,
        kind=kind,
        plan=plan,
        amount=(plan or {}).get("price", 0),
        status="pending",
        note=note,
        operator=operator,
    )


def update_order(order_id, **updates):
    data = load_orders()
    for order in data.get("orders", []):
        if order.get("id") == order_id:
            order.update(updates)
            order["updated_at"] = now_iso()
            save_orders(data)
            return order
    raise RuntimeError("order not found")
