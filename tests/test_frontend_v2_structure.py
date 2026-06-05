import re
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


def test_frontend_v2_removes_legacy_single_file_assets():
    assert not (ASSETS / "app.js").exists()
    assert not (ASSETS / "style.css").exists()


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
    assert "/payqr/" in orders
    assert "payment-qr" in orders
    plans = (assets / "plans.js").read_text(encoding="utf-8")
    assert "checkout-panel" in plans
    assert "data-payment-method-for-plan" in plans
    assert 'data-action="checkout-open"' in plans
    assert 'data-action="checkout-start"' in plans
    assert 'data-action="checkout-close"' in plans


def test_frontend_v2_admin_pages_use_task_cards_and_bottom_sheets():
    assets = ASSETS / "js" / "pages" / "admin"
    for name in ["overview.js", "users.js", "orders.js", "nodes.js", "plans.js", "settings.js"]:
        text = (assets / name).read_text(encoding="utf-8")
        assert "admin-card" in text
        assert "data-action" in text
    orders = (assets / "orders.js").read_text(encoding="utf-8")
    assert "bottom-sheet" in orders
    nodes = (assets / "nodes.js").read_text(encoding="utf-8")
    assert "exit quality" in nodes.lower()
    plans = (assets / "plans.js").read_text(encoding="utf-8")
    assert 'data-form="plan-save"' in plans
    assert 'data-action="plan-edit"' in plans
    assert 'data-action="plan-action"' in plans


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
        "/api/plans/save",
        "/api/plans/action",
        "/api/cache/clear",
    ]:
        assert endpoint in main
    for action in [
        "checkout-open",
        "checkout-close",
        "checkout-start",
        "payment-start",
        "payment-refresh",
        "payment-submit-txid",
        "order-cancel",
        "plan-create-sheet",
        "plan-edit",
        "plan-action",
        "payment-method-action",
        "cache-clear",
    ]:
        assert action in main


def test_frontend_v2_page_actions_are_wired_in_main_dispatcher():
    main = read_asset("js/main.js")
    pages_dir = ASSETS / "js" / "pages"
    action_pattern = re.compile(r'data-action="([^"]+)"')
    ignored = {"${esc(action)}"}
    actions = set()
    for path in pages_dir.rglob("*.js"):
        actions.update(action for action in action_pattern.findall(path.read_text(encoding="utf-8")) if action not in ignored)

    for action in sorted(actions):
        assert f'button.dataset.action === "{action}"' in main or f'action === "{action}"' in main, action


def test_frontend_v2_layout_prevents_dashboard_overflow():
    layout_js = read_asset("js/components/layout.js")
    layout_css = read_asset("css/layout.css")
    components_css = read_asset("css/components.css")

    assert "version-chip" in layout_js
    assert "state.shell?.version" in layout_js
    assert "side-nav-scroll" in layout_js
    assert "side-nav-footer" in layout_js
    assert "nav-stack secondary" not in layout_js
    assert "nav-stack-secondary" in layout_js
    assert "overflow-x: hidden" in layout_css
    assert "overflow-y: auto" in layout_css
    assert "grid-template-rows: auto minmax(0, 1fr) auto" in layout_css
    assert ".side-nav-scroll" in layout_css
    assert ".side-nav-footer" in layout_css
    assert ".nav-stack.secondary" not in layout_css
    assert ".nav-stack-secondary" in layout_css
    assert "margin-top: auto" not in layout_css
    assert ".version-chip" in layout_css
    assert "max-width:" in layout_css
    assert ".workspace-v2" in layout_css
    assert ".side-nav .nav-item" in components_css
    assert "min-height: 40px" in components_css
    assert "minmax(0, 1fr)" in components_css
    assert "overflow-wrap: anywhere" in components_css


def test_frontend_v2_admin_payment_settings_are_address_first():
    settings = read_asset("js/pages/admin/settings.js")
    assert 'data-form="payment-method-save"' in settings
    assert 'name="payment_type"' in settings
    assert 'name="address"' in settings
    assert "RPC URL" not in settings
    assert "Token 合约" not in settings
