import importlib
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
BASELINE = ROOT / "baseline"
if str(BASELINE) not in sys.path:
    sys.path.insert(0, str(BASELINE))


MODULES = [
    "auth_store",
    "user_store",
    "node_catalog",
    "plans_store",
    "orders_store",
    "audit_log",
    "admin_profile",
    "operations_service",
    "user_admin",
    "panel_config",
    "json_store",
    "payments_store",
    "payment_rates",
    "payment_wallets",
    "payment_verifier",
    "payment_service",
    "api_payment_routes",
]


@pytest.fixture()
def payment_modules(tmp_path, monkeypatch):
    panel_dir = tmp_path / "panel"
    panel_dir.mkdir()
    monkeypatch.setenv("PANEL_DIR", str(panel_dir))
    for name in MODULES:
        if name in sys.modules:
            importlib.reload(sys.modules[name])
        else:
            importlib.import_module(name)
    return {name: sys.modules[name] for name in MODULES}




def pad_topic_address(addr):
    return "0x" + ("0" * 24) + addr.lower().replace("0x", "")


def create_standard_order_and_method(monkeypatch):
    plans_store = importlib.import_module("plans_store")
    orders_store = importlib.import_module("orders_store")
    payments_store = importlib.import_module("payments_store")
    user_admin = importlib.import_module("user_admin")

    monkeypatch.setattr(user_admin, "enforce_users_now", lambda: "ok")
    plan = plans_store.upsert_plan(
        {"id": "standard", "name": "Standard", "days": "30", "traffic_gb": "100", "price": "39"}
    )
    order = orders_store.create_pending_order("alice", "renew", plan, operator="alice")
    method = payments_store.upsert_method(
        {
            "id": "usdt-eth",
            "asset": "USDT",
            "chain": "ethereum",
            "address": "0x2222222222222222222222222222222222222222",
            "token_contract": "0xdac17f958d2ee523a2206206994597c13d831ec7",
            "decimals": "6",
            "rpc_url": "https://rpc.example",
            "confirmations_required": "12",
            "enabled": True,
        }
    )
    return order, method


def create_btc_order_and_method(monkeypatch):
    plans_store = importlib.import_module("plans_store")
    orders_store = importlib.import_module("orders_store")
    payments_store = importlib.import_module("payments_store")
    user_admin = importlib.import_module("user_admin")
    payment_rates = importlib.import_module("payment_rates")

    monkeypatch.setattr(user_admin, "enforce_users_now", lambda: "ok")
    payment_rates.save_overrides({"BTC": "100000"})
    plan = plans_store.upsert_plan(
        {"id": "standard", "name": "Standard", "days": "30", "traffic_gb": "100", "price": "39"}
    )
    order = orders_store.create_pending_order("alice", "renew", plan, operator="alice")
    method = payments_store.upsert_method(
        {
            "asset": "BTC",
            "chain": "bitcoin",
            "address": "bc1qqqqqqqqqqqqqqqqqqqq",
        }
    )
    return order, method


def user_session(username):
    return {"u": username, "r": "user", "role": "user"}


def admin_session_for_payments():
    return {"u": "admin", "r": "admin", "role": "admin"}
