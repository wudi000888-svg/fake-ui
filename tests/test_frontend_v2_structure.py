import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "baseline" / "frontend" / "assets"


def read_asset(path):
    return (ASSETS / path).read_text(encoding="utf-8")


def read_action_assets():
    return "\n".join(path.read_text(encoding="utf-8") for path in (ASSETS / "js" / "actions").glob("*.js"))


def test_frontend_v2_modules_exist_and_index_uses_module_entry():
    index = (ROOT / "baseline" / "frontend" / "index.html").read_text(encoding="utf-8")
    assert 'type="module"' in index
    assert "assets/js/main.js" in index

    for path in [
        "js/main.js",
        "js/api.js",
        "js/state.js",
        "js/router.js",
        "js/dom.js",
        "js/actions/forms.js",
        "js/actions/handlers.js",
        "js/actions/admin.js",
        "js/actions/orders.js",
        "js/actions/payments.js",
        "js/actions/users_nodes.js",
        "js/components/layout.js",
        "js/components/login.js",
        "js/pages/registry.js",
        "js/pages/admin/backups.js",
        "js/pages/admin/simple.js",
        "css/tokens.css",
        "css/layout.css",
        "css/components.css",
    ]:
        assert (ASSETS / path).exists(), path


def test_frontend_v2_main_is_modular_entrypoint():
    main = read_asset("js/main.js")
    assert len(main.splitlines()) < 180
    assert "bindAppActions" in main
    assert 'app.addEventListener("click"' not in main
    assert 'app.addEventListener("submit"' not in main


def test_frontend_exposes_self_registration_and_admin_toggle():
    login = read_asset("js/components/login.js")
    handlers = read_asset("js/actions/handlers.js")
    settings = read_asset("js/pages/admin/settings.js")
    admin_actions = read_asset("js/actions/admin.js")

    assert 'href="/register"' in login
    assert 'data-form="register"' in login
    assert 'state.publicSettings?.registration_enabled' in login
    assert 'post("/api/register"' in handlers
    assert 'navigate("login")' in handlers
    assert 'name="registration_enabled"' in settings
    assert 'data-form="public-settings-save"' in settings
    assert 'post("/api/public-settings"' in admin_actions


def test_frontend_exposes_password_reset_email_and_logout_controls():
    login = read_asset("js/components/login.js")
    handlers = read_asset("js/actions/handlers.js")
    settings = read_asset("js/pages/admin/settings.js")
    account = read_asset("js/pages/user/account.js")
    layout = read_asset("js/components/layout.js")

    assert 'href="/forgot"' in login
    assert 'data-form="password-reset-send"' in login
    assert 'data-form="password-reset-confirm"' in login
    assert 'post("/api/password-reset/send-code"' in handlers
    assert 'post("/api/password-reset/confirm"' in handlers
    assert 'data-form="self-email"' in account
    assert 'post("/api/self/email"' in handlers
    assert 'data-form="email-settings-save"' in settings
    assert 'post("/api/email-settings"' in read_asset("js/actions/admin.js")
    assert 'data-action="logout"' in layout


def test_frontend_v2_actions_are_split_by_domain():
    handlers = read_asset("js/actions/handlers.js")
    assert len(handlers.splitlines()) < 180
    assert "handleAdminAction" in handlers
    assert "handleOrderAction" in handlers
    assert "handlePaymentAction" in handlers
    assert "handleUserNodeAction" in handlers


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
    users = (assets / "users.js").read_text(encoding="utf-8")
    assert 'data-node-picker="user-edit"' in users
    assert 'type="checkbox"' in users
    assert 'name="node_ids"' in users
    assert "节点 ID" not in users
    backups = (assets / "backups.js").read_text(encoding="utf-8")
    assert 'data-action="backup-create"' in backups
    assert 'data-action="backup-download"' in backups
    assert 'data-form="backup-import"' in backups


def test_frontend_v2_admin_hy2_page_has_real_controls():
    registry = read_asset("js/pages/registry.js")
    assert "renderAdminHy2" in registry
    assert 'state.route === "hy2"' in registry

    hy2 = read_asset("js/pages/admin/hy2.js")
    assert 'data-form="hy2-save"' in hy2
    assert 'data-action="hy2-disable"' in hy2
    assert 'name="proxy_type"' in hy2
    assert "Hysteria2 出口" in hy2
    assert "运行状态" in hy2
    assert "currentProxy" in hy2
    assert "addrFromProxy" in hy2
    assert "hy2-status-head" in hy2


def test_frontend_v2_node_actions_update_state_from_api_response():
    user_node_actions = read_asset("js/actions/users_nodes.js")
    assert "export function applyNodePayload" in user_node_actions
    assert "out.nodes" in user_node_actions
    assert "out.node" in user_node_actions
    assert "state.data.nodes" in user_node_actions
    assert "节点已保存，出口信息已同步" in user_node_actions


def test_frontend_v2_hy2_actions_are_admin_owned_and_sync_nodes():
    admin_actions = read_asset("js/actions/admin.js")
    user_node_actions = read_asset("js/actions/users_nodes.js")

    assert "/api/hy2/apply" in admin_actions
    assert "/api/hy2/disable" in admin_actions
    assert "applyNodePayload" in admin_actions
    assert "hy2-save" not in user_node_actions
    assert "hy2-disable" not in user_node_actions


def test_frontend_v2_get_api_failures_show_server_errors_not_fetch_only():
    api_js = read_asset("js/api.js")
    assert "GET" in api_js
    assert "response.json" in api_js
    assert "data.error" in api_js
    assert "无法连接面板 API" in api_js


def test_frontend_v2_spa_wires_commercial_actions():
    action_source = read_action_assets()
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
        "/api/users/update",
        "/api/backups/create",
        "/api/backups/upload",
        "/api/cache/clear",
    ]:
        assert endpoint in action_source
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
        "backup-create",
        "backup-download",
        "payment-method-action",
        "cache-clear",
    ]:
        assert action in action_source


def test_frontend_v2_page_actions_are_wired_in_main_dispatcher():
    action_source = read_action_assets()
    pages_dir = ASSETS / "js" / "pages"
    action_pattern = re.compile(r'data-action="([^"]+)"')
    ignored = {"${esc(action)}"}
    actions = set()
    for path in pages_dir.rglob("*.js"):
        actions.update(action for action in action_pattern.findall(path.read_text(encoding="utf-8")) if action not in ignored)

    for action in sorted(actions):
        assert (
            f'button.dataset.action === "{action}"' in action_source
            or f'action === "{action}"' in action_source
            or f'actionName === "{action}"' in action_source
        ), action


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
    assert "[...primaryItems, ...secondaryItems]" in layout_js
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
    assert ".hy2-status-head" in components_css
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
