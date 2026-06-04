from pathlib import Path


APP_JS = Path(__file__).resolve().parents[1] / "baseline" / "frontend" / "assets" / "app.js"
STYLE_CSS = Path(__file__).resolve().parents[1] / "baseline" / "frontend" / "assets" / "style.css"


def test_frontend_exposes_crypto_payment_user_flow():
    source = APP_JS.read_text(encoding="utf-8")

    assert "function paymentStatusPill" in source
    assert "function paymentForOrder" in source
    assert 'data-action="payment-start"' in source
    assert 'data-action="payment-refresh"' in source
    assert 'data-form="payment-submit"' in source
    assert "/api/payments/create" in source
    assert "/api/payments/submit-tx" in source
    assert "/api/payments/refresh" in source
    assert "/payqr/" in source
    assert "api.qrserver.com" not in source
    assert "交易哈希 / TXID（可选）" in source
    assert "我已付款，检查到账" in source
    assert "function orderBuckets" in source
    assert "需要补 TXID" in source


def test_frontend_cancelled_orders_do_not_show_active_payment_actions():
    source = APP_JS.read_text(encoding="utf-8")

    cancelled_guard = source.index('order.status === "cancelled"')
    payment_render = source.index("if (payment) return")
    assert cancelled_guard < payment_render
    assert "订单已取消" in source


def test_frontend_exposes_crypto_payment_admin_settings():
    source = APP_JS.read_text(encoding="utf-8")

    assert "function paymentMethodsSettings" in source
    assert 'data-form="payment-method-save"' in source
    assert 'data-form="payment-rates-save"' in source
    assert 'data-action="payment-method-action"' in source
    assert "/api/payment-methods/save" in source
    assert "/api/payment-methods/action" in source
    assert "/api/payment-rates/save" in source
    assert "支付类型" in source
    assert "RPC URL（EVM）" not in source
    assert "Token 合约（USDT / USDC）" not in source


def test_frontend_payment_styles_are_present():
    source = STYLE_CSS.read_text(encoding="utf-8")

    assert ".payment-grid" in source
    assert ".payment-card" in source
    assert ".payment-mini" in source
    assert ".payment-code" in source
