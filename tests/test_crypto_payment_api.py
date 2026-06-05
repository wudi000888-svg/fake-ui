from payment_test_utils import importlib, pytest, payment_modules, create_standard_order_and_method, user_session, admin_session_for_payments

def test_payment_api_user_flow(payment_modules, monkeypatch):
    api = importlib.import_module("api")
    plans_store = importlib.import_module("plans_store")
    payments_store = importlib.import_module("payments_store")
    payment_service = importlib.import_module("payment_service")
    user_admin = importlib.import_module("user_admin")

    monkeypatch.setattr(user_admin, "enforce_users_now", lambda: "ok")
    monkeypatch.setattr(
        payment_service,
        "verify_payment",
        lambda p, m: {"status": "confirmed", "detected_amount": p["crypto_amount"], "confirmations": 12, "error": ""},
    )
    plans_store.upsert_plan({"id": "standard", "name": "Standard", "days": "30", "traffic_gb": "100", "price": "39"})
    payments_store.upsert_method(
        {
            "id": "usdt-eth",
            "asset": "USDT",
            "chain": "ethereum",
            "address": "0x2222222222222222222222222222222222222222",
            "token_contract": "0xdac17f958d2ee523a2206206994597c13d831ec7",
            "rpc_url": "https://rpc.example",
            "confirmations_required": "12",
            "enabled": True,
        }
    )

    status, payload = api.handle_post("/api/orders/create", {"plan_id": "standard", "kind": "renew"}, user_session("alice"))
    assert status == 200
    order_id = payload["order"]["id"]

    status, payload = api.handle_post("/api/payments/create", {"order_id": order_id, "method_id": "usdt-eth"}, user_session("alice"))
    assert status == 200
    payment_id = payload["payment"]["id"]

    status, payload = api.handle_post("/api/payments/submit-tx", {"id": payment_id, "txid": "0xtx"}, user_session("alice"))
    assert status == 200
    assert payload["payment"]["status"] == "confirmed"


def test_payment_api_submit_txid_is_optional(payment_modules, monkeypatch):
    api = importlib.import_module("api")
    plans_store = importlib.import_module("plans_store")
    payments_store = importlib.import_module("payments_store")
    payment_service = importlib.import_module("payment_service")
    user_admin = importlib.import_module("user_admin")

    monkeypatch.setattr(user_admin, "enforce_users_now", lambda: "ok")
    monkeypatch.setattr(
        payment_service,
        "verify_payment",
        lambda p, m: {"status": "confirmed", "detected_amount": p["crypto_amount"], "confirmations": 12, "error": ""},
    )
    plans_store.upsert_plan({"id": "standard", "name": "Standard", "days": "30", "traffic_gb": "100", "price": "39"})
    payments_store.upsert_method(
        {
            "asset": "USDT",
            "chain": "bsc",
            "address": "0x2222222222222222222222222222222222222222",
        }
    )

    status, payload = api.handle_post("/api/orders/create", {"plan_id": "standard"}, user_session("alice"))
    assert status == 200
    order_id = payload["order"]["id"]
    status, payload = api.handle_post("/api/payments/create", {"order_id": order_id, "method_id": "usdt-bsc"}, user_session("alice"))
    assert status == 200

    status, payload = api.handle_post("/api/payments/submit-tx", {"id": payload["payment"]["id"]}, user_session("alice"))
    assert status == 200
    assert payload["payment"]["status"] == "confirmed"


def test_payment_method_admin_api(payment_modules):
    api = importlib.import_module("api")
    status, payload = api.handle_post(
        "/api/payment-methods/save",
        {
            "asset": "BTC",
            "chain": "bitcoin",
            "address": "bc1qqqqqqqqqqqqqqqqqqqq",
        },
        admin_session_for_payments(),
    )
    assert status == 200
    assert payload["method"]["id"] == "btc-main"

    status, payload = api.handle_get("/api/payment-methods", user_session("alice"))
    assert status == 200
    assert payload["methods"][0]["id"] == "btc-main"
    assert "btc_api_url" not in payload["methods"][0]


def test_user_post_admin_actions_stay_forbidden(payment_modules):
    api = importlib.import_module("api")

    status, payload = api.handle_post("/api/users/action", {"username": "alice", "action": "disable"}, user_session("alice"))
    assert status == 403
    assert payload["ok"] is False

    status, payload = api.handle_post("/api/orders/action", {"id": "ord_1", "action": "confirm"}, user_session("alice"))
    assert status == 403
    assert payload["ok"] is False


def test_user_can_cancel_own_pending_order_but_not_confirm_or_cancel_others(payment_modules, monkeypatch):
    api = importlib.import_module("api")
    orders_store = importlib.import_module("orders_store")
    plans_store = importlib.import_module("plans_store")
    user_admin = importlib.import_module("user_admin")

    monkeypatch.setattr(user_admin, "enforce_users_now", lambda: "ok")
    plan = plans_store.upsert_plan({"id": "standard", "name": "Standard", "days": "30", "traffic_gb": "100", "price": "39"})
    alice_order = orders_store.create_pending_order("alice", "renew", plan, operator="alice")
    bob_order = orders_store.create_pending_order("bob", "renew", plan, operator="bob")

    status, payload = api.handle_post("/api/orders/action", {"id": alice_order["id"], "action": "confirm"}, user_session("alice"))
    assert status == 403
    assert payload["ok"] is False

    status, payload = api.handle_post("/api/orders/action", {"id": bob_order["id"], "action": "cancel"}, user_session("alice"))
    assert status == 404
    assert payload["ok"] is False

    status, payload = api.handle_post("/api/orders/action", {"id": alice_order["id"], "action": "cancel"}, user_session("alice"))
    assert status == 200
    assert orders_store.get_order(alice_order["id"])["status"] == "cancelled"


def test_user_order_create_ignores_body_username(payment_modules, monkeypatch):
    api = importlib.import_module("api")
    plans_store = importlib.import_module("plans_store")
    user_admin = importlib.import_module("user_admin")

    monkeypatch.setattr(user_admin, "enforce_users_now", lambda: "ok")
    plans_store.upsert_plan({"id": "standard", "name": "Standard", "days": "30", "traffic_gb": "100", "price": "39"})

    status, payload = api.handle_post(
        "/api/orders/create",
        {"plan_id": "standard", "kind": "renew", "username": "bob"},
        user_session("alice"),
    )

    assert status == 200
    assert payload["order"]["username"] == "alice"
    assert payload["order"]["kind"] == "create"


def test_user_order_create_auto_renews_existing_user(payment_modules, monkeypatch):
    api = importlib.import_module("api")
    plans_store = importlib.import_module("plans_store")
    user_admin = importlib.import_module("user_admin")
    user_store = importlib.import_module("user_store")

    monkeypatch.setattr(user_admin, "enforce_users_now", lambda: "ok")
    plans_store.upsert_plan({"id": "standard", "name": "Standard", "days": "30", "traffic_gb": "100", "price": "39"})
    user_store.save_users(
        {
            "version": 1,
            "users": {
                "alice": {
                    "enabled": True,
                    "role": "user",
                    "expires_at": "2099-01-01T00:00:00+00:00",
                    "quota_bytes": 0,
                    "used_bytes": 0,
                }
            },
        }
    )

    status, payload = api.handle_post(
        "/api/orders/create",
        {"plan_id": "standard", "kind": "create", "username": "bob"},
        user_session("alice"),
    )

    assert status == 200
    assert payload["order"]["username"] == "alice"
    assert payload["order"]["kind"] == "renew"


def test_user_cannot_save_payment_methods(payment_modules):
    api = importlib.import_module("api")

    status, payload = api.handle_post(
        "/api/payment-methods/save",
        {
            "id": "btc-main",
            "asset": "BTC",
            "chain": "bitcoin",
            "address": "bc1qqqqqqqqqqqqqqqqqqqq",
            "btc_api_url": "https://blockstream.info/api",
        },
        user_session("alice"),
    )

    assert status == 403
    assert payload["ok"] is False


def test_user_cannot_manage_payment_methods_or_rates(payment_modules):
    api = importlib.import_module("api")

    status, payload = api.handle_post(
        "/api/payment-methods/action",
        {"id": "btc-main", "action": "disable"},
        user_session("alice"),
    )
    assert status == 403
    assert payload["ok"] is False

    status, payload = api.handle_post(
        "/api/payment-rates/save",
        {"overrides": {"BTC": "30000"}},
        user_session("alice"),
    )
    assert status == 403
    assert payload["ok"] is False


def test_user_cannot_create_payment_for_another_users_order(payment_modules, monkeypatch):
    api = importlib.import_module("api")

    order, method = create_standard_order_and_method(monkeypatch)

    with pytest.raises(RuntimeError, match="order not found"):
        api.handle_post(
            "/api/payments/create",
            {"order_id": order["id"], "method_id": method["id"]},
            user_session("bob"),
        )


def test_user_cannot_refresh_or_submit_another_users_payment(payment_modules, monkeypatch):
    api = importlib.import_module("api")
    payment_service = importlib.import_module("payment_service")

    order, method = create_standard_order_and_method(monkeypatch)
    payment = payment_service.create_payment_for_order(order["id"], method["id"], "alice")

    for path, data in (
        ("/api/payments/refresh", {"id": payment["id"]}),
        ("/api/payments/submit-tx", {"id": payment["id"], "txid": "0xtx"}),
    ):
        with pytest.raises(RuntimeError, match="payment not found"):
            api.handle_post(path, data, user_session("bob"))


def test_dashboard_includes_payment_data_and_backup_includes_payments(payment_modules):
    dashboard_service = importlib.import_module("dashboard_service")
    backup_manager = importlib.import_module("backup_manager")
    payments_store = importlib.import_module("payments_store")

    payments_store.upsert_method(
        {
            "id": "btc-main",
            "asset": "BTC",
            "chain": "bitcoin",
            "address": "bc1qqqqqqqqqqqqqqqqqqqq",
            "btc_api_url": "https://blockstream.info/api",
            "confirmations_required": "3",
        }
    )
    user_payload = dashboard_service.dashboard({"u": "alice", "r": "user", "role": "user"})
    assert "payment_methods" in user_payload
    assert user_payload["payment_methods"][0]["id"] == "btc-main"
    assert "payments" in user_payload
    assert "payments.json" in backup_manager.BACKUP_FILES


def test_admin_dashboard_includes_payment_methods_payments_and_rates(payment_modules, monkeypatch):
    dashboard_service = importlib.import_module("dashboard_service")
    payments_store = importlib.import_module("payments_store")

    monkeypatch.setattr(dashboard_service.xray_panel, "current_status", lambda: {"proxy": "127.0.0.1:1080"})
    monkeypatch.setattr(dashboard_service.hy2_panel, "hy2_status", lambda: {})
    monkeypatch.setattr(dashboard_service, "admin_links", lambda: {})
    payments_store.upsert_method(
        {
            "id": "btc-main",
            "asset": "BTC",
            "chain": "bitcoin",
            "address": "bc1qqqqqqqqqqqqqqqqqqqq",
            "btc_api_url": "https://blockstream.info/api",
            "confirmations_required": "3",
        }
    )
    payments_store.save_rates({"overrides": {"BTC": "30000"}, "cache": {}})

    admin_payload = dashboard_service.dashboard({"u": "admin", "r": "admin", "role": "admin"})

    assert admin_payload["payment_methods"][0]["id"] == "btc-main"
    assert "payments" in admin_payload
    assert admin_payload["payment_rates"]["overrides"]["BTC"] == "30000"


def test_user_dashboard_payment_methods_do_not_leak_btc_api_url(payment_modules):
    dashboard_service = importlib.import_module("dashboard_service")
    payments_store = importlib.import_module("payments_store")

    payments_store.upsert_method(
        {
            "id": "btc-main",
            "asset": "BTC",
            "chain": "bitcoin",
            "address": "bc1qqqqqqqqqqqqqqqqqqqq",
            "btc_api_url": "https://blockstream.info/api",
            "confirmations_required": "3",
        }
    )

    user_payload = dashboard_service.dashboard({"u": "alice", "r": "user", "role": "user"})

    assert "btc_api_url" not in user_payload["payment_methods"][0]


def test_payment_qr_route_checks_ownership(payment_modules):
    http_qr_routes = importlib.import_module("http_qr_routes")
    payments_store = importlib.import_module("payments_store")

    payment = payments_store.create_payment(
        {
            "order_id": "ord_1",
            "username": "alice",
            "method_id": "btc-main",
            "asset": "BTC",
            "chain": "bitcoin",
            "crypto_amount": "0.00039000",
            "address": "bc1qqqqqqqqqqqqqqqqqqqq",
            "qr_payload": "bitcoin:bc1qqqqqqqqqqqqqqqqqqqq?amount=0.00039000",
        }
    )

    class Handler:
        path = f"/payqr/{payment['id']}"
        status = None
        content_type = None
        body = None

        def __init__(self, username, role="user"):
            self.username = username
            self.role = role

        def current_role(self):
            return self.role

        def current_username(self):
            return self.username

        def forbidden(self):
            self.status = 403

        def respond_bytes(self, body, content_type):
            self.status = 200
            self.body = body
            self.content_type = content_type

        def respond_text(self, text, status=200):
            self.status = status
            self.body = text

    owner = Handler("alice")
    http_qr_routes.handle_payment_qr(owner)
    assert owner.status == 200
    assert owner.content_type == "image/png"
    assert owner.body.startswith(b"\x89PNG\r\n\x1a\n")

    other = Handler("bob")
    http_qr_routes.handle_payment_qr(other)
    assert other.status == 403
