import secrets
from datetime import datetime, timezone

from panel_config import PLANS_FILE
from json_store import load_json, save_json


def now_iso():
    return datetime.now(timezone.utc).isoformat()


DEFAULT_PLANS = [
    {
        "id": "starter",
        "name": "Starter",
        "days": 30,
        "traffic_gb": 100,
        "price": 0,
        "node_groups": ["default"],
        "enabled": True,
        "sort": 10,
    },
    {
        "id": "standard",
        "name": "Standard",
        "days": 30,
        "traffic_gb": 300,
        "price": 0,
        "node_groups": ["default"],
        "enabled": True,
        "sort": 20,
    },
]


def default_data():
    return {"version": 1, "plans": DEFAULT_PLANS}


def load_plans():
    return load_json(PLANS_FILE, default_data, create=True)


def save_plans(data):
    save_json(PLANS_FILE, data)


def list_plans(include_disabled=True):
    plans = load_plans().get("plans", [])
    if not include_disabled:
        plans = [p for p in plans if p.get("enabled", True)]
    return sorted(plans, key=lambda p: (int(p.get("sort", 0) or 0), p.get("id", "")))


def get_plan(plan_id):
    for plan in load_plans().get("plans", []):
        if plan.get("id") == plan_id:
            return plan
    return None


def normalize_plan(data):
    plan_id = (data.get("id") or data.get("name") or secrets.token_hex(4)).strip()
    plan_id = "".join(ch for ch in plan_id.lower().replace(" ", "-") if ch.isalnum() or ch in "-_")
    if not plan_id:
        plan_id = secrets.token_hex(4)
    days = int(data.get("days", 30))
    traffic_gb = float(data.get("traffic_gb", 0) or 0)
    price = float(data.get("price", 0) or 0)
    if days <= 0:
        raise RuntimeError("plan days must be greater than 0")
    if traffic_gb < 0:
        raise RuntimeError("plan traffic cannot be negative")
    groups = data.get("node_groups", ["default"])
    if isinstance(groups, str):
        groups = [g.strip() for g in groups.split(",") if g.strip()]
    return {
        "id": plan_id,
        "name": (data.get("name") or plan_id).strip(),
        "days": days,
        "traffic_gb": traffic_gb,
        "price": price,
        "node_groups": groups or ["default"],
        "enabled": bool(data.get("enabled", True)),
        "sort": int(data.get("sort", 100) or 100),
        "updated_at": now_iso(),
    }


def upsert_plan(data):
    plan = normalize_plan(data)
    store = load_plans()
    plans = store.setdefault("plans", [])
    for idx, item in enumerate(plans):
        if item.get("id") == plan["id"]:
            old_created = item.get("created_at")
            plans[idx] = {**item, **plan}
            if old_created:
                plans[idx]["created_at"] = old_created
            break
    else:
        plan["created_at"] = now_iso()
        plans.append(plan)
    save_plans(store)
    return plan


def set_plan_enabled(plan_id, enabled):
    store = load_plans()
    for plan in store.get("plans", []):
        if plan.get("id") == plan_id:
            plan["enabled"] = bool(enabled)
            plan["updated_at"] = now_iso()
            save_plans(store)
            return plan
    raise RuntimeError("plan not found")


def delete_plan(plan_id):
    store = load_plans()
    old = len(store.get("plans", []))
    store["plans"] = [p for p in store.get("plans", []) if p.get("id") != plan_id]
    if len(store["plans"]) == old:
        raise RuntimeError("plan not found")
    save_plans(store)
    return True
