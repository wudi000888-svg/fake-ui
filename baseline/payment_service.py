import re
from datetime import datetime, timedelta, timezone

import orders_store
import payment_rates
import payment_verifier
import payment_wallets
import payments_store
import user_admin


PAYMENT_TTL_HOURS = 2
FINAL_PAYMENT_STATUSES = {"confirmed", "failed", "expired"}
SECRET_QUERY_RE = re.compile(r"(?i)([?&](?:key|token|apikey|api_key)=)([^&\s]+)")


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _expires_at():
    return (datetime.now(timezone.utc) + timedelta(hours=PAYMENT_TTL_HOURS)).isoformat()


def _sanitize_error(error):
    text = str(error or "verification failed").strip() or "verification failed"
    text = SECRET_QUERY_RE.sub(r"\1[redacted]", text)
    return text[:200]


def _owned_payment(payment_id, username, admin=False):
    payment = payments_store.get_payment(payment_id)
    if not payment:
        raise RuntimeError("payment not found")
    if not admin and payment.get("username") != username:
        raise RuntimeError("payment not found")
    return payment


def _method_for_payment(payment):
    method = payments_store.get_method(payment.get("method_id"))
    if not method:
        raise RuntimeError("payment method not found")
    return method


def create_payment_for_order(order_id, method_id, username, admin=False):
    order = orders_store.get_order(order_id)
    if not order:
        raise RuntimeError("order not found")
    if not admin and order.get("username") != username:
        raise RuntimeError("order not found")
    if order.get("status") != "pending":
        raise RuntimeError("order is not pending")

    existing_payment_id = order.get("payment_id")
    if existing_payment_id:
        existing_payment = payments_store.get_payment(existing_payment_id)
        if existing_payment and existing_payment.get("status") not in FINAL_PAYMENT_STATUSES:
            return existing_payment

    method = payments_store.get_method(method_id)
    if not method or not method.get("enabled"):
        raise RuntimeError("payment method not available")

    usd_amount = str(order.get("amount", ""))
    crypto_amount = payment_rates.crypto_amount_for_usd(usd_amount, method.get("asset"), method.get("decimals"))
    rate_usd = payment_rates.rate_for_asset(method.get("asset"))
    qr_payload = payment_wallets.qr_payload(method, crypto_amount)

    payment = payments_store.create_payment(
        {
            "order_id": order["id"],
            "username": order.get("username", username),
            "method_id": method["id"],
            "asset": method.get("asset", ""),
            "chain": method.get("chain", ""),
            "usd_amount": usd_amount,
            "crypto_amount": crypto_amount,
            "rate_usd": rate_usd,
            "address": method.get("address", ""),
            "qr_payload": qr_payload,
            "expires_at": _expires_at(),
        }
    )
    orders_store.update_order(order["id"], payment_id=payment["id"], payment_status=payment["status"])
    return payment


def verify_payment(payment, method):
    txid = str((payment or {}).get("txid") or "").strip()
    if not txid:
        return {
            "status": (payment or {}).get("status", "awaiting_payment"),
            "detected_amount": (payment or {}).get("detected_amount", ""),
            "confirmations": int((payment or {}).get("confirmations", 0) or 0),
            "error": "txid required",
        }

    chain = str(method.get("chain") or "").strip().lower()
    required_amount = payment.get("crypto_amount")
    confirmations_required = method.get("confirmations_required", 1)
    decimals = method.get("decimals", 8)

    if payment_wallets.is_evm_chain(chain):
        current_block = payment_verifier.parse_hex_int(
            payment_verifier.rpc_call(method.get("rpc_url"), "eth_blockNumber", []),
            "blockNumber",
        )
        if method.get("token_contract"):
            receipt = payment_verifier.rpc_call(method.get("rpc_url"), "eth_getTransactionReceipt", [txid])
            return payment_verifier.verify_evm_erc20_receipt(
                receipt,
                current_block=current_block,
                token_contract=method.get("token_contract"),
                to_address=method.get("address"),
                required_amount=required_amount,
                decimals=decimals,
                confirmations_required=confirmations_required,
            )

        tx = payment_verifier.rpc_call(method.get("rpc_url"), "eth_getTransactionByHash", [txid])
        return payment_verifier.verify_evm_native_tx(
            tx,
            current_block=current_block,
            to_address=method.get("address"),
            required_amount=required_amount,
            decimals=decimals,
            confirmations_required=confirmations_required,
        )

    if chain == "bitcoin":
        base_url = str(method.get("btc_api_url") or "").rstrip("/")
        tx = payment_verifier.http_json(f"{base_url}/tx/{txid}")
        tip_height = payment_verifier.http_json(f"{base_url}/blocks/tip/height")
        return payment_verifier.verify_btc_tx(
            tx,
            tip_height=tip_height,
            to_address=method.get("address"),
            required_amount=required_amount,
            confirmations_required=confirmations_required,
        )

    return {"status": "failed", "detected_amount": "", "confirmations": 0, "error": "unsupported payment chain"}


def apply_verification(payment_id, result, operator="system"):
    payment = payments_store.get_payment(payment_id)
    if not payment:
        raise RuntimeError("payment not found")

    verification = dict(result or {})
    status = verification.get("status") or payment.get("status") or "awaiting_payment"
    updates = {
        "status": status,
        "detected_amount": verification.get("detected_amount", payment.get("detected_amount", "")),
        "confirmations": int(verification.get("confirmations", payment.get("confirmations", 0)) or 0),
        "error": _sanitize_error(verification.get("error", "")) if verification.get("error") else "",
        "verified_at": _now_iso(),
    }
    updated = payments_store.update_payment(payment_id, **updates)

    order = orders_store.get_order(updated.get("order_id"))
    if order:
        is_current_order_payment = order.get("payment_id") == updated.get("id")
        if is_current_order_payment:
            orders_store.update_order(order["id"], payment_status=updated["status"])
        if updated["status"] == "confirmed" and is_current_order_payment and order.get("status") == "pending":
            user_admin.confirm_order(order["id"], operator=operator)

    return updated


def refresh_payment(payment_id, username, admin=False):
    payment = _owned_payment(payment_id, username, admin=admin)
    if payment.get("status") in FINAL_PAYMENT_STATUSES:
        return payment
    try:
        method = _method_for_payment(payment)
    except Exception as exc:
        return payments_store.update_payment(payment_id, error=_sanitize_error(exc), verified_at=_now_iso())
    try:
        result = verify_payment(payment, method)
    except Exception as exc:
        return payments_store.update_payment(payment_id, error=_sanitize_error(exc), verified_at=_now_iso())
    return apply_verification(payment_id, result, operator=username or "system")


def submit_tx_and_verify(payment_id, txid, username, admin=False):
    payment = _owned_payment(payment_id, username, admin=admin)
    if payment.get("status") in FINAL_PAYMENT_STATUSES:
        return payment
    payments_store.attach_txid(payment_id, txid)
    return refresh_payment(payment_id, username, admin=admin)
