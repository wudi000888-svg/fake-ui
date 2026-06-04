import payment_rates
import payment_service
import payments_store
from api_common import ok
from http_utils import api_error


def is_admin(session):
    return bool(session) and (session.get("role") or session.get("r")) == "admin"


def _username(session):
    return (session or {}).get("u", "")


def handle_payment_get(clean, session):
    admin = is_admin(session)

    if clean == "/api/payment-methods":
        payload = {"methods": payments_store.list_methods(admin=admin)}
        if admin:
            payload["rates"] = payments_store.load_rates()
        return ok(**payload)

    if clean == "/api/payments":
        username = None if admin else _username(session)
        return ok(payments=payments_store.list_payments(username=username, admin=admin, limit=200))

    return None


def handle_payment_post(clean, data, session):
    admin = is_admin(session)
    username = _username(session)

    if clean == "/api/payment-methods/save":
        if not admin:
            return api_error("forbidden", 403)
        method = payments_store.upsert_method(data)
        return ok(method=method, methods=payments_store.list_methods(admin=True))

    if clean == "/api/payment-methods/action":
        if not admin:
            return api_error("forbidden", 403)
        action = data.get("action", "")
        method_id = data.get("id", "")
        if action == "enable":
            method = payments_store.set_method_enabled(method_id, True)
        elif action == "disable":
            method = payments_store.set_method_enabled(method_id, False)
        elif action == "delete":
            payments_store.delete_method(method_id)
            method = {"id": method_id}
        else:
            raise RuntimeError("unknown payment method action")
        return ok(method=method, methods=payments_store.list_methods(admin=True))

    if clean == "/api/payment-rates/save":
        if not admin:
            return api_error("forbidden", 403)
        rates = payment_rates.save_overrides(data.get("overrides", data))
        return ok(rates=rates)

    if clean == "/api/payments/create":
        payment = payment_service.create_payment_for_order(
            data.get("order_id", ""),
            data.get("method_id", ""),
            username,
            admin=admin,
        )
        return ok(payment=payments_store.public_payment(payment, admin=admin))

    if clean == "/api/payments/submit-tx":
        payment = payment_service.submit_tx_and_verify(
            data.get("id", ""),
            data.get("txid", ""),
            username,
            admin=admin,
        )
        return ok(payment=payments_store.public_payment(payment, admin=admin))

    if clean == "/api/payments/refresh":
        payment = payment_service.refresh_payment(data.get("id", ""), username, admin=admin)
        return ok(payment=payments_store.public_payment(payment, admin=admin))

    return None
