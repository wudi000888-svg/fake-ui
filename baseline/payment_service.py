import re
from decimal import Decimal
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
EVM_SCAN_BLOCK_LOOKBACK = 200000
EVM_SCAN_MAX_BLOCK_RANGE = 50000
PAYMENT_TIME_SKEW_SECONDS = 60
PAYMENT_RECOVERY_DAYS = 7


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _expires_at():
    return (datetime.now(timezone.utc) + timedelta(hours=PAYMENT_TTL_HOURS)).isoformat()


def _sanitize_error(error):
    text = str(error or "verification failed").strip() or "verification failed"
    text = SECRET_QUERY_RE.sub(r"\1[redacted]", text)
    return text[:200]


def _parse_time(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _rpc_urls(method):
    urls = []
    preset = payment_wallets.preset_for(
        str(method.get("asset") or "").strip().upper(),
        str(method.get("chain") or "").strip().lower(),
    )
    for value in (method.get("rpc_urls"), method.get("rpc_url"), preset.get("rpc_urls", [])):
        if isinstance(value, (list, tuple)):
            raw_items = value
        else:
            raw_items = [value]
        for item in raw_items:
            url = str(item or "").strip()
            if url and url not in urls:
                urls.append(url)
    return urls or [method.get("rpc_url")]


def _btc_api_urls(method):
    urls = []
    preset = payment_wallets.preset_for(
        str(method.get("asset") or "").strip().upper(),
        str(method.get("chain") or "").strip().lower(),
    )
    for value in (method.get("btc_api_urls"), method.get("btc_api_url"), preset.get("btc_api_urls", [])):
        if isinstance(value, (list, tuple)):
            raw_items = value
        else:
            raw_items = [value]
        for item in raw_items:
            url = str(item or "").strip().rstrip("/")
            if url and url not in urls:
                urls.append(url)
    return urls or [method.get("btc_api_url")]


def _address_topic(address):
    normalized = payment_verifier.normalize_address(address).replace("0x", "")
    return "0x" + ("0" * 24) + normalized


def _block_timestamp(method, block_number):
    block = payment_verifier.rpc_call(_rpc_urls(method), "eth_getBlockByNumber", [hex(block_number), False])
    timestamp = payment_verifier.hex_int(dict(block or {}).get("timestamp"), default=0)
    if timestamp <= 0:
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)


def _created_at_floor(payment):
    created_at = _parse_time(payment.get("created_at"))
    if not created_at:
        return None
    return created_at - timedelta(seconds=PAYMENT_TIME_SKEW_SECONDS)


def _payment_expired(payment):
    expires_at = _parse_time(payment.get("expires_at"))
    return bool(expires_at and datetime.now(timezone.utc) >= expires_at)


def _expire_payment(payment_id):
    updated = payments_store.update_payment(
        payment_id,
        status="expired",
        error="payment expired",
        verified_at=_now_iso(),
    )
    order = orders_store.get_order(updated.get("order_id"))
    if order and order.get("payment_id") == updated.get("id"):
        orders_store.update_order(order["id"], payment_status="expired")
        if order.get("status") == "pending":
            orders_store.update_order(order["id"], status="cancelled", cancelled_at=_now_iso(), cancelled_by="system")
    return updated


def _confirmed_status(amount, required_amount, confirmations, confirmations_required):
    if Decimal(str(amount)) < payment_verifier.parse_required_amount(required_amount):
        return "low"
    if int(confirmations) < payment_verifier.parse_confirmations_required(confirmations_required):
        return "detected"
    return "confirmed"


def _evm_log_query(method, from_block, to_block):
    return {
        "fromBlock": hex(from_block),
        "toBlock": hex(to_block),
        "address": method.get("token_contract"),
        "topics": [
            payment_verifier.ERC20_TRANSFER_TOPIC,
            None,
            _address_topic(method.get("address")),
        ],
    }


def _is_evm_log_range_error(error):
    text = str(error or "").lower()
    return any(
        token in text
        for token in (
            "limit exceeded",
            "block range",
            "range too",
            "too many",
            "query timeout",
            "response size",
            "more than",
        )
    )


def _scan_evm_logs(method, from_block, to_block):
    urls = _rpc_urls(method)

    def fetch_range(start, end):
        try:
            return payment_verifier.rpc_call(urls, "eth_getLogs", [_evm_log_query(method, start, end)])
        except Exception as exc:
            if not _is_evm_log_range_error(exc) or start >= end:
                raise
            middle = start + ((end - start) // 2)
            left = fetch_range(start, middle)
            right = fetch_range(middle + 1, end)
            return list(left or []) + list(right or [])

    try:
        return fetch_range(from_block, to_block)
    except Exception as exc:
        if not _is_evm_log_range_error(exc) or to_block - from_block <= EVM_SCAN_MAX_BLOCK_RANGE:
            raise
        logs = []
        start = from_block
        while start <= to_block:
            end = min(to_block, start + EVM_SCAN_MAX_BLOCK_RANGE)
            chunk = fetch_range(start, end)
            logs.extend(chunk or [])
            start = end + 1
        return logs


def _scan_evm_erc20_payment(payment, method):
    required_amount = payment.get("crypto_amount")
    decimals = method.get("decimals", 8)
    confirmations_required = method.get("confirmations_required", 1)
    current_block = payment_verifier.parse_hex_int(
        payment_verifier.rpc_call(_rpc_urls(method), "eth_blockNumber", []),
        "blockNumber",
    )
    lookback = int(method.get("scan_block_lookback") or EVM_SCAN_BLOCK_LOOKBACK)
    from_block = max(0, current_block - lookback)
    logs = _scan_evm_logs(method, from_block, current_block)
    floor = _created_at_floor(payment)
    grouped = {}
    for raw_log in logs or []:
        log = dict(raw_log or {})
        topics = list(log.get("topics", []) or [])
        if payment_verifier.normalize_address(log.get("address")) != payment_verifier.normalize_address(
            method.get("token_contract")
        ):
            continue
        if len(topics) < 3 or str(topics[0]).lower() != payment_verifier.ERC20_TRANSFER_TOPIC:
            continue
        if payment_verifier.topic_to_address(topics[2]) != payment_verifier.normalize_address(method.get("address")):
            continue
        txid = str(log.get("transactionHash") or "").strip()
        if not txid or payments_store.txid_used(txid, exclude_payment_id=payment.get("id")):
            continue
        block_number = payment_verifier.parse_hex_int(log.get("blockNumber"), "blockNumber")
        if floor:
            block_time = _block_timestamp(method, block_number)
            if block_time and block_time < floor:
                continue
        item = grouped.setdefault(txid, {"txid": txid, "units": 0, "block_number": block_number})
        item["units"] += payment_verifier.parse_hex_int(log.get("data"), "log data")
        item["block_number"] = min(item["block_number"], block_number)

    candidates = []
    insufficient = []
    for item in grouped.values():
        amount = payment_verifier.amount_from_units(item["units"], decimals)
        confirmations = current_block - item["block_number"] + 1 if item["block_number"] > 0 else 0
        status = _confirmed_status(amount, required_amount, confirmations, confirmations_required)
        candidate = {
            "txid": item["txid"],
            "detected_amount": amount,
            "confirmations": confirmations,
        }
        if status == "confirmed":
            candidates.append(candidate)
        elif status == "detected":
            insufficient.append({**candidate, "status": "detected", "error": "confirmations below required amount"})
        else:
            insufficient.append({**candidate, "status": "detected", "error": "detected amount below required amount"})

    if len(candidates) == 1:
        return {"status": "confirmed", "error": "", **candidates[0]}
    if len(candidates) > 1:
        best = max(candidates, key=lambda item: (item.get("confirmations", 0), item.get("txid", "")))
        return {
            "status": "ambiguous",
            "detected_amount": best.get("detected_amount", ""),
            "confirmations": best.get("confirmations", 0),
            "error": "multiple matching transfers found, txid required",
        }
    if insufficient:
        best = max(insufficient, key=lambda item: (item.get("confirmations", 0), item.get("txid", "")))
        return {
            "status": "detected",
            "detected_amount": best.get("detected_amount", ""),
            "confirmations": best.get("confirmations", 0),
            "error": best.get("error", ""),
        }
    return {
        "status": "awaiting_payment",
        "detected_amount": payment.get("detected_amount", ""),
        "confirmations": int(payment.get("confirmations", 0) or 0),
        "error": "",
    }


def _btc_tx_time(tx):
    status = dict((tx or {}).get("status") or {})
    block_time = int(status.get("block_time") or 0)
    if block_time > 0:
        return datetime.fromtimestamp(block_time, tz=timezone.utc)
    return None


def _scan_btc_payment(payment, method):
    required_amount = payment.get("crypto_amount")
    confirmations_required = method.get("confirmations_required", 1)
    last_error = None
    for base_url in _btc_api_urls(method):
        try:
            txs = payment_verifier.http_json(f"{base_url}/address/{method.get('address')}/txs")
            tip_height = payment_verifier.http_json(f"{base_url}/blocks/tip/height")
            break
        except Exception as exc:
            last_error = exc
    else:
        raise RuntimeError(last_error or "btc api error")

    floor = _created_at_floor(payment)
    candidates = []
    insufficient = []
    for tx in txs or []:
        tx = dict(tx or {})
        txid = str(tx.get("txid") or "").strip()
        if not txid or payments_store.txid_used(txid, exclude_payment_id=payment.get("id")):
            continue
        tx_time = _btc_tx_time(tx)
        if floor and tx_time and tx_time < floor:
            continue
        result = payment_verifier.verify_btc_tx(
            tx,
            tip_height=tip_height,
            to_address=method.get("address"),
            required_amount=required_amount,
            confirmations_required=confirmations_required,
        )
        candidate = {
            "txid": txid,
            "detected_amount": result.get("detected_amount", ""),
            "confirmations": result.get("confirmations", 0),
            "error": result.get("error", ""),
        }
        if result.get("status") == "confirmed":
            candidates.append(candidate)
        elif result.get("status") == "detected":
            insufficient.append(candidate)

    if len(candidates) == 1:
        return {"status": "confirmed", "error": "", **candidates[0]}
    if len(candidates) > 1:
        best = max(candidates, key=lambda item: (item.get("confirmations", 0), item.get("txid", "")))
        return {
            "status": "ambiguous",
            "detected_amount": best.get("detected_amount", ""),
            "confirmations": best.get("confirmations", 0),
            "error": "multiple matching transfers found, txid required",
        }
    if insufficient:
        best = max(insufficient, key=lambda item: (item.get("confirmations", 0), item.get("txid", "")))
        return {
            "status": "detected",
            "detected_amount": best.get("detected_amount", ""),
            "confirmations": best.get("confirmations", 0),
            "error": best.get("error", ""),
        }
    return {
        "status": "awaiting_payment",
        "detected_amount": payment.get("detected_amount", ""),
        "confirmations": int(payment.get("confirmations", 0) or 0),
        "error": "",
    }


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
    chain = str(method.get("chain") or "").strip().lower()
    required_amount = payment.get("crypto_amount")
    confirmations_required = method.get("confirmations_required", 1)
    decimals = method.get("decimals", 8)

    if not txid:
        if payment_wallets.is_evm_chain(chain) and method.get("token_contract"):
            return _scan_evm_erc20_payment(payment, method)
        if chain == "bitcoin":
            return _scan_btc_payment(payment, method)
        return {
            "status": (payment or {}).get("status", "awaiting_payment"),
            "detected_amount": (payment or {}).get("detected_amount", ""),
            "confirmations": int((payment or {}).get("confirmations", 0) or 0),
            "error": "txid required",
        }

    if payment_wallets.is_evm_chain(chain):
        current_block = payment_verifier.parse_hex_int(
            payment_verifier.rpc_call(_rpc_urls(method), "eth_blockNumber", []),
            "blockNumber",
        )
        if method.get("token_contract"):
            receipt = payment_verifier.rpc_call(_rpc_urls(method), "eth_getTransactionReceipt", [txid])
            return payment_verifier.verify_evm_erc20_receipt(
                receipt,
                current_block=current_block,
                token_contract=method.get("token_contract"),
                to_address=method.get("address"),
                required_amount=required_amount,
                decimals=decimals,
                confirmations_required=confirmations_required,
            )

        tx = payment_verifier.rpc_call(_rpc_urls(method), "eth_getTransactionByHash", [txid])
        return payment_verifier.verify_evm_native_tx(
            tx,
            current_block=current_block,
            to_address=method.get("address"),
            required_amount=required_amount,
            decimals=decimals,
            confirmations_required=confirmations_required,
        )

    if chain == "bitcoin":
        last_error = None
        for base_url in _btc_api_urls(method):
            try:
                tx = payment_verifier.http_json(f"{base_url}/tx/{txid}")
                tip_height = payment_verifier.http_json(f"{base_url}/blocks/tip/height")
                break
            except Exception as exc:
                last_error = exc
        else:
            raise RuntimeError(last_error or "btc api error")
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
    txid = str(verification.get("txid") or "").strip()
    if txid:
        updates["txid"] = txid
    if status == "ambiguous" and not payment.get("ambiguous_at"):
        updates["ambiguous_at"] = _now_iso()
    elif status != "ambiguous" and payment.get("ambiguous_at"):
        updates["ambiguous_at"] = ""
    updated = payments_store.update_payment(payment_id, **updates)

    order = orders_store.get_order(updated.get("order_id"))
    if order:
        is_current_order_payment = order.get("payment_id") == updated.get("id")
        if is_current_order_payment:
            orders_store.update_order(order["id"], payment_status=updated["status"])
        if updated["status"] == "confirmed" and is_current_order_payment and order.get("status") == "cancelled":
            cancelled_at = _parse_time(order.get("cancelled_at"))
            if not cancelled_at or datetime.now(timezone.utc) - cancelled_at <= timedelta(days=PAYMENT_RECOVERY_DAYS):
                order = orders_store.update_order(order["id"], status="pending", recovered_at=_now_iso())
        if updated["status"] == "confirmed" and is_current_order_payment and order.get("status") == "pending":
            user_admin.confirm_order(order["id"], operator=operator)

    return updated


def refresh_payment(payment_id, username, admin=False):
    payment = _owned_payment(payment_id, username, admin=admin)
    if payment.get("status") in FINAL_PAYMENT_STATUSES:
        return payment
    if _payment_expired(payment):
        return _expire_payment(payment_id)
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
    if str(txid or "").strip():
        payments_store.attach_txid(payment_id, txid)
    return refresh_payment(payment_id, username, admin=admin)
