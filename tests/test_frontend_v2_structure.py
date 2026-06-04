from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "baseline" / "frontend" / "assets"


def read_asset(path):
    return (ASSETS / path).read_text(encoding="utf-8")


def test_frontend_v2_modules_exist_and_index_uses_module_entry():
    index = (ROOT / "baseline" / "frontend" / "index.html").read_text(encoding="utf-8")
    assert 'type="module"' in index
    assert "assets/js/main.js" in index

    for path in [
        "js/main.js",
        "js/api.js",
        "js/state.js",
        "js/router.js",
        "js/components/layout.js",
        "css/tokens.css",
        "css/layout.css",
        "css/components.css",
    ]:
        assert (ASSETS / path).exists(), path


def test_frontend_v2_mobile_shell_tokens_are_present():
    css = read_asset("css/layout.css")
    assert "@media (max-width: 767px)" in css
    assert "bottom-nav" in css
    assert "min-height: 44px" in css


def test_frontend_v2_uses_dashboard_compatibility_layer():
    main = read_asset("js/main.js")
    state = read_asset("js/state.js")
    assert "/api/dashboard" in main
    assert "data: {}" in state
    assert "state.data" in main
    assert "fake-ui:navigate" in main


def test_frontend_v2_user_pages_have_mobile_commercial_flows():
    assets = ASSETS / "js" / "pages" / "user"
    expected = ["dashboard.js", "orders.js", "plans.js", "links.js", "account.js"]
    for name in expected:
        text = (assets / name).read_text(encoding="utf-8")
        assert "mobile-card" in text
        assert "data-action" in text
    orders = (assets / "orders.js").read_text(encoding="utf-8")
    assert "payment-timeline" in orders
    assert "txid" in orders.lower()
    assert "待处理" in orders
    assert "历史订单" in orders
    assert "已取消" in orders
    assert "payment-start" in orders
    assert "paymentMethodOptions" in orders


def test_frontend_v2_admin_pages_use_task_cards_and_bottom_sheets():
    assets = ASSETS / "js" / "pages" / "admin"
    for name in ["overview.js", "users.js", "orders.js", "nodes.js", "settings.js"]:
        text = (assets / name).read_text(encoding="utf-8")
        assert "admin-card" in text
        assert "data-action" in text
    orders = (assets / "orders.js").read_text(encoding="utf-8")
    assert "bottom-sheet" in orders
    nodes = (assets / "nodes.js").read_text(encoding="utf-8")
    assert "exit quality" in nodes.lower()


def test_frontend_v2_spa_wires_commercial_actions():
    main = read_asset("js/main.js")
    for endpoint in [
        "/api/orders/create",
        "/api/orders/action",
        "/api/payments/create",
        "/api/payments/refresh",
        "/api/payments/submit-tx",
        "/api/payment-methods/save",
        "/api/payment-methods/action",
        "/api/cache/clear",
    ]:
        assert endpoint in main
    for action in [
        "buy-plan",
        "payment-start",
        "payment-refresh",
        "payment-submit-txid",
        "order-cancel",
        "payment-method-action",
        "cache-clear",
    ]:
        assert action in main


def test_frontend_v2_admin_payment_settings_are_address_first():
    settings = read_asset("js/pages/admin/settings.js")
    assert 'data-form="payment-method-save"' in settings
    assert 'name="payment_type"' in settings
    assert 'name="address"' in settings
    assert "RPC URL" not in settings
    assert "Token 合约" not in settings
