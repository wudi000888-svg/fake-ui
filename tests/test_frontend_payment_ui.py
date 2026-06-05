from pathlib import Path


ASSETS = Path(__file__).resolve().parents[1] / "baseline" / "frontend" / "assets"
MAIN_JS = ASSETS / "js" / "main.js"
ACTION_HANDLERS_JS = ASSETS / "js" / "actions" / "handlers.js"
USER_ORDERS_JS = ASSETS / "js" / "pages" / "user" / "orders.js"
USER_PLANS_JS = ASSETS / "js" / "pages" / "user" / "plans.js"
ADMIN_SETTINGS_JS = ASSETS / "js" / "pages" / "admin" / "settings.js"
COMPONENTS_CSS = ASSETS / "css" / "components.css"


def read_action_assets():
    return "\n".join(path.read_text(encoding="utf-8") for path in (ASSETS / "js" / "actions").glob("*.js"))


def test_frontend_exposes_crypto_payment_user_flow():
    actions = read_action_assets()
    orders = USER_ORDERS_JS.read_text(encoding="utf-8")
    plans = USER_PLANS_JS.read_text(encoding="utf-8")

    assert "function paymentForOrder" in orders
    assert 'data-action="payment-start"' in orders
    assert 'data-action="payment-refresh"' in orders
    assert 'data-action="payment-submit-txid"' in orders
    assert "/api/payments/create" in actions
    assert "/api/payments/submit-tx" in actions
    assert "/api/payments/refresh" in actions
    assert "/payqr/" in orders
    assert "api.qrserver.com" not in orders
    assert "交易哈希 / TXID（可选）" in orders
    assert "我已付款，检查到账" in orders
    assert "function orderBuckets" in orders
    assert "需要补 TXID" in orders
    assert "checkout-panel" in plans
    assert "data-payment-method-for-plan" in plans
    assert "/api/orders/create" in actions


def test_frontend_cancelled_orders_do_not_show_active_payment_actions():
    source = USER_ORDERS_JS.read_text(encoding="utf-8")

    cancelled_guard = source.index('order.status === "completed" || order.status === "cancelled"')
    payment_render = source.index('const paymentActions = finalOrder ? "" : payment')
    assert cancelled_guard < payment_render
    assert "订单已取消" in source


def test_frontend_admin_payment_cards_use_admin_actions():
    source = (ASSETS / "js" / "pages" / "admin" / "orders.js").read_text(encoding="utf-8")

    assert "function paymentCard(payment)" in source
    assert "管理员核账" in source
    assert "补录 TXID" in source
    assert "刷新到账" in source
    assert "payment-submit-txid" in source


def test_frontend_payment_records_hide_cancelled_and_final_orders():
    source = USER_ORDERS_JS.read_text(encoding="utf-8")

    assert "function orderForPayment(payment, orders = [])" in source
    assert 'linkedOrder?.status !== "cancelled"' in source
    assert 'linkedOrder?.status !== "completed"' in source
    assert '["awaiting_payment", "detected", "ambiguous"].includes(payment.status)' in source
    assert "activePayments" in source


def test_frontend_exposes_crypto_payment_admin_settings():
    source = ADMIN_SETTINGS_JS.read_text(encoding="utf-8")
    actions = read_action_assets()

    assert "function paymentMethodsSettings" in source
    assert 'data-form="payment-method-save"' in source
    assert 'data-action="payment-method-action"' in source
    assert "/api/payment-methods/save" in actions
    assert "/api/payment-methods/action" in actions
    assert "支付类型" in source
    assert "RPC URL（EVM）" not in source
    assert "Token 合约（USDT / USDC）" not in source


def test_frontend_payment_styles_are_present():
    source = COMPONENTS_CSS.read_text(encoding="utf-8")

    assert ".payment-grid" in source
    assert ".payment-card" in source
    assert ".payment-mini" in source
    assert ".payment-code" in source
    assert ".checkout-panel" in source
    assert ".payment-qr" in source
