from payment_test_utils import importlib, pytest, payment_modules, create_standard_order_and_method, create_btc_order_and_method, pad_topic_address

def test_confirmed_payment_completes_order(payment_modules, monkeypatch):
    orders_store = importlib.import_module("orders_store")
    payments_store = importlib.import_module("payments_store")
    payment_service = importlib.import_module("payment_service")

    order, method = create_standard_order_and_method(monkeypatch)
    payment = payment_service.create_payment_for_order(order["id"], method["id"], "alice")
    assert payment["crypto_amount"] == "39.000000"
    assert orders_store.get_order(order["id"])["payment_status"] == "awaiting_payment"
    assert payments_store.get_payment(payment["id"])["qr_payload"] == method["address"]

    monkeypatch.setattr(
        payment_service,
        "verify_payment",
        lambda p, m: {"status": "confirmed", "detected_amount": p["crypto_amount"], "confirmations": 12, "error": ""},
    )
    done = payment_service.submit_tx_and_verify(payment["id"], "0xtx", "alice")
    assert done["status"] == "confirmed"
    assert orders_store.get_order(order["id"])["status"] == "completed"


def test_create_payment_rejects_non_owner_and_disabled_method(payment_modules, monkeypatch):
    payments_store = importlib.import_module("payments_store")
    payment_service = importlib.import_module("payment_service")

    order, method = create_standard_order_and_method(monkeypatch)
    with pytest.raises(RuntimeError, match="order not found"):
        payment_service.create_payment_for_order(order["id"], method["id"], "bob")

    payments_store.set_method_enabled(method["id"], False)
    with pytest.raises(RuntimeError, match="payment method not available"):
        payment_service.create_payment_for_order(order["id"], method["id"], "alice")


def test_payment_refresh_and_submit_hide_non_owner_payments(payment_modules, monkeypatch):
    payment_service = importlib.import_module("payment_service")

    order, method = create_standard_order_and_method(monkeypatch)
    payment = payment_service.create_payment_for_order(order["id"], method["id"], "alice")

    with pytest.raises(RuntimeError, match="payment not found"):
        payment_service.refresh_payment(payment["id"], "bob")

    with pytest.raises(RuntimeError, match="payment not found"):
        payment_service.submit_tx_and_verify(payment["id"], "0xtx", "bob")


def test_confirmed_payment_refresh_is_idempotent(payment_modules, monkeypatch):
    orders_store = importlib.import_module("orders_store")
    payment_service = importlib.import_module("payment_service")
    user_admin = importlib.import_module("user_admin")

    order, method = create_standard_order_and_method(monkeypatch)
    payment = payment_service.create_payment_for_order(order["id"], method["id"], "alice")
    monkeypatch.setattr(
        payment_service,
        "verify_payment",
        lambda p, m: {"status": "confirmed", "detected_amount": p["crypto_amount"], "confirmations": 12, "error": ""},
    )
    payment_service.submit_tx_and_verify(payment["id"], "0xtx", "alice")

    def fail_confirm(order_id, operator="admin"):
        raise AssertionError("confirm_order should not be called again")

    monkeypatch.setattr(user_admin, "confirm_order", fail_confirm)
    refreshed = payment_service.refresh_payment(payment["id"], "alice")
    assert refreshed["status"] == "confirmed"
    assert orders_store.get_order(order["id"])["status"] == "completed"


def test_detected_payment_keeps_order_pending(payment_modules, monkeypatch):
    orders_store = importlib.import_module("orders_store")
    payment_service = importlib.import_module("payment_service")

    order, method = create_standard_order_and_method(monkeypatch)
    payment = payment_service.create_payment_for_order(order["id"], method["id"], "alice")
    monkeypatch.setattr(
        payment_service,
        "verify_payment",
        lambda p, m: {
            "status": "detected",
            "detected_amount": p["crypto_amount"],
            "confirmations": 3,
            "error": "confirmations below required amount",
        },
    )

    detected = payment_service.submit_tx_and_verify(payment["id"], "0xtx", "alice")
    order_after = orders_store.get_order(order["id"])
    assert detected["status"] == "detected"
    assert order_after["status"] == "pending"
    assert order_after["payment_status"] == "detected"


def test_refresh_without_txid_scans_erc20_transfer_and_completes_order(payment_modules, monkeypatch):
    orders_store = importlib.import_module("orders_store")
    payment_service = importlib.import_module("payment_service")
    payment_verifier = importlib.import_module("payment_verifier")
    payments_store = importlib.import_module("payments_store")

    order, method = create_standard_order_and_method(monkeypatch)
    payment = payment_service.create_payment_for_order(order["id"], method["id"], "alice")
    block_number = 189
    tx_hash = "0x" + "a" * 64
    amount_units = 39000000
    scanned = []

    def fake_rpc(urls, rpc_method, params):
        scanned.append((rpc_method, params))
        if rpc_method == "eth_blockNumber":
            return "0xc8"
        if rpc_method == "eth_getLogs":
            assert params[0]["topics"][2] == pad_topic_address(method["address"])
            return [
                {
                    "transactionHash": tx_hash,
                    "blockNumber": hex(block_number),
                    "address": method["token_contract"],
                    "topics": [
                        payment_verifier.ERC20_TRANSFER_TOPIC,
                        pad_topic_address("0x1111111111111111111111111111111111111111"),
                        pad_topic_address(method["address"]),
                    ],
                    "data": "0x" + format(amount_units, "064x"),
                }
            ]
        if rpc_method == "eth_getBlockByNumber":
            return {"timestamp": "0x7fffffff"}
        raise AssertionError(rpc_method)

    monkeypatch.setattr(payment_verifier, "rpc_call", fake_rpc)

    refreshed = payment_service.refresh_payment(payment["id"], "alice")

    assert refreshed["status"] == "confirmed"
    assert refreshed["txid"] == tx_hash
    assert refreshed["detected_amount"] == "39.000000"
    assert refreshed["confirmations"] == 12
    assert orders_store.get_order(order["id"])["status"] == "completed"
    assert payments_store.txid_used(tx_hash)
    assert any(item[0] == "eth_getLogs" for item in scanned)


def test_refresh_without_txid_splits_erc20_log_scan_when_public_rpc_limits_range(payment_modules, monkeypatch):
    orders_store = importlib.import_module("orders_store")
    payment_service = importlib.import_module("payment_service")
    payment_verifier = importlib.import_module("payment_verifier")

    order, method = create_standard_order_and_method(monkeypatch)
    payment = payment_service.create_payment_for_order(order["id"], method["id"], "alice")
    block_number = 199900
    tx_hash = "0x" + "b" * 64
    amount_units = 39000000
    log_ranges = []

    def fake_rpc(urls, rpc_method, params):
        if rpc_method == "eth_blockNumber":
            return "0x30d40"
        if rpc_method == "eth_getLogs":
            query = params[0]
            start = int(query["fromBlock"], 16)
            end = int(query["toBlock"], 16)
            log_ranges.append((start, end))
            if end - start > 50000:
                raise RuntimeError("limit exceeded")
            if start <= block_number <= end:
                return [
                    {
                        "transactionHash": tx_hash,
                        "blockNumber": hex(block_number),
                        "address": method["token_contract"],
                        "topics": [
                            payment_verifier.ERC20_TRANSFER_TOPIC,
                            pad_topic_address("0x1111111111111111111111111111111111111111"),
                            pad_topic_address(method["address"]),
                        ],
                        "data": "0x" + format(amount_units, "064x"),
                    }
                ]
            return []
        if rpc_method == "eth_getBlockByNumber":
            return {"timestamp": hex(4102444800)}
        raise AssertionError(rpc_method)

    monkeypatch.setattr(payment_verifier, "rpc_call", fake_rpc)

    refreshed = payment_service.refresh_payment(payment["id"], "alice")

    assert refreshed["status"] == "confirmed"
    assert refreshed["txid"] == tx_hash
    assert orders_store.get_order(order["id"])["status"] == "completed"
    assert log_ranges[0] == (0, 200000)
    assert any(end - start <= 50000 for start, end in log_ranges[1:])


def test_refresh_without_txid_keeps_splitting_erc20_log_scan_until_rpc_accepts(payment_modules, monkeypatch):
    orders_store = importlib.import_module("orders_store")
    payment_service = importlib.import_module("payment_service")
    payment_verifier = importlib.import_module("payment_verifier")

    order, method = create_standard_order_and_method(monkeypatch)
    payment = payment_service.create_payment_for_order(order["id"], method["id"], "alice")
    block_number = 199900
    tx_hash = "0x" + "c" * 64
    amount_units = 39000000
    log_ranges = []

    def fake_rpc(urls, rpc_method, params):
        if rpc_method == "eth_blockNumber":
            return "0x30d40"
        if rpc_method == "eth_getLogs":
            query = params[0]
            start = int(query["fromBlock"], 16)
            end = int(query["toBlock"], 16)
            log_ranges.append((start, end))
            if end - start > 25000:
                raise RuntimeError("limit exceeded")
            if start <= block_number <= end:
                return [
                    {
                        "transactionHash": tx_hash,
                        "blockNumber": hex(block_number),
                        "address": method["token_contract"],
                        "topics": [
                            payment_verifier.ERC20_TRANSFER_TOPIC,
                            pad_topic_address("0x1111111111111111111111111111111111111111"),
                            pad_topic_address(method["address"]),
                        ],
                        "data": "0x" + format(amount_units, "064x"),
                    }
                ]
            return []
        if rpc_method == "eth_getBlockByNumber":
            return {"timestamp": hex(4102444800)}
        raise AssertionError(rpc_method)

    monkeypatch.setattr(payment_verifier, "rpc_call", fake_rpc)

    refreshed = payment_service.refresh_payment(payment["id"], "alice")

    assert refreshed["status"] == "confirmed"
    assert refreshed["txid"] == tx_hash
    assert orders_store.get_order(order["id"])["status"] == "completed"
    assert any(end - start <= 25000 for start, end in log_ranges)


def test_refresh_without_txid_limits_erc20_scan_to_payment_created_time(payment_modules, monkeypatch):
    orders_store = importlib.import_module("orders_store")
    payment_service = importlib.import_module("payment_service")
    payment_verifier = importlib.import_module("payment_verifier")
    payments_store = importlib.import_module("payments_store")

    order, method = create_standard_order_and_method(monkeypatch)
    payment = payment_service.create_payment_for_order(order["id"], method["id"], "alice")
    payment = payments_store.update_payment(payment["id"], created_at="2099-12-31T23:55:00+00:00")
    tx_hash = "0x" + "d" * 64
    tx_block = 199950
    amount_units = 39000000
    log_ranges = []

    def fake_rpc(urls, rpc_method, params):
        if rpc_method == "eth_blockNumber":
            return "0x30d40"
        if rpc_method == "eth_getLogs":
            query = params[0]
            start = int(query["fromBlock"], 16)
            end = int(query["toBlock"], 16)
            log_ranges.append((start, end))
            assert start > 190000
            if start <= tx_block <= end:
                return [
                    {
                        "transactionHash": tx_hash,
                        "blockNumber": hex(tx_block),
                        "address": method["token_contract"],
                        "topics": [
                            payment_verifier.ERC20_TRANSFER_TOPIC,
                            pad_topic_address("0x1111111111111111111111111111111111111111"),
                            pad_topic_address(method["address"]),
                        ],
                        "data": "0x" + format(amount_units, "064x"),
                    }
                ]
            return []
        if rpc_method == "eth_getBlockByNumber":
            return {"timestamp": hex(4102444800)}
        raise AssertionError(rpc_method)

    monkeypatch.setattr(payment_verifier, "rpc_call", fake_rpc)

    refreshed = payment_service.refresh_payment(payment["id"], "alice")

    assert refreshed["status"] == "confirmed"
    assert refreshed["txid"] == tx_hash
    assert orders_store.get_order(order["id"])["status"] == "completed"
    assert log_ranges[0][0] > 190000


def test_refresh_without_txid_keeps_minimum_bsc_scan_window(payment_modules, monkeypatch):
    orders_store = importlib.import_module("orders_store")
    payment_service = importlib.import_module("payment_service")
    payment_verifier = importlib.import_module("payment_verifier")
    payments_store = importlib.import_module("payments_store")

    order, method = create_standard_order_and_method(monkeypatch)
    method = payments_store.upsert_method(
        {
            "id": "usdt-bsc",
            "asset": "USDT",
            "chain": "bsc",
            "address": "0x2222222222222222222222222222222222222222",
            "token_contract": "0x55d398326f99059ff775485246999027b3197955",
            "decimals": "18",
            "rpc_url": "https://rpc.example",
            "confirmations_required": "12",
            "enabled": True,
        }
    )
    payment = payment_service.create_payment_for_order(order["id"], method["id"], "alice")
    payment = payments_store.update_payment(payment["id"], created_at="2099-12-31T23:59:30+00:00")
    tx_hash = "0x" + "e" * 64
    tx_block = 194500
    amount_units = 39000000000000000000
    log_ranges = []

    def fake_rpc(urls, rpc_method, params):
        if rpc_method == "eth_blockNumber":
            return "0x30d40"
        if rpc_method == "eth_getLogs":
            query = params[0]
            start = int(query["fromBlock"], 16)
            end = int(query["toBlock"], 16)
            log_ranges.append((start, end))
            assert start <= 194000
            if start <= tx_block <= end:
                return [
                    {
                        "transactionHash": tx_hash,
                        "blockNumber": hex(tx_block),
                        "address": method["token_contract"],
                        "topics": [
                            payment_verifier.ERC20_TRANSFER_TOPIC,
                            pad_topic_address("0x1111111111111111111111111111111111111111"),
                            pad_topic_address(method["address"]),
                        ],
                        "data": "0x" + format(amount_units, "064x"),
                    }
                ]
            return []
        if rpc_method == "eth_getBlockByNumber":
            return {"timestamp": hex(4102444800)}
        raise AssertionError(rpc_method)

    monkeypatch.setattr(payment_verifier, "rpc_call", fake_rpc)

    refreshed = payment_service.refresh_payment(payment["id"], "alice")

    assert refreshed["status"] == "confirmed"
    assert refreshed["txid"] == tx_hash
    assert orders_store.get_order(order["id"])["status"] == "completed"
    assert log_ranges[0][0] <= 194000


def test_refresh_without_txid_marks_ambiguous_when_multiple_matching_transfers(payment_modules, monkeypatch):
    orders_store = importlib.import_module("orders_store")
    payment_service = importlib.import_module("payment_service")
    payment_verifier = importlib.import_module("payment_verifier")

    order, method = create_standard_order_and_method(monkeypatch)
    payment = payment_service.create_payment_for_order(order["id"], method["id"], "alice")

    def log_for(tx_char):
        return {
            "transactionHash": "0x" + tx_char * 64,
            "blockNumber": "0xbd",
            "address": method["token_contract"],
            "topics": [
                payment_verifier.ERC20_TRANSFER_TOPIC,
                pad_topic_address("0x1111111111111111111111111111111111111111"),
                pad_topic_address(method["address"]),
            ],
            "data": "0x" + format(39000000, "064x"),
        }

    def fake_rpc(urls, rpc_method, params):
        if rpc_method == "eth_blockNumber":
            return "0xc8"
        if rpc_method == "eth_getLogs":
            return [log_for("a"), log_for("b")]
        if rpc_method == "eth_getBlockByNumber":
            return {"timestamp": "0x7fffffff"}
        raise AssertionError(rpc_method)

    monkeypatch.setattr(payment_verifier, "rpc_call", fake_rpc)

    refreshed = payment_service.refresh_payment(payment["id"], "alice")

    assert refreshed["status"] == "ambiguous"
    assert "txid required" in refreshed["error"]
    assert "ambiguous_at" in refreshed
    order_after = orders_store.get_order(order["id"])
    assert order_after["status"] == "pending"
    assert order_after["payment_status"] == "ambiguous"


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


def test_refresh_without_txid_scans_btc_address_txs_and_completes_order(payment_modules, monkeypatch):
    orders_store = importlib.import_module("orders_store")
    payment_service = importlib.import_module("payment_service")
    payment_verifier = importlib.import_module("payment_verifier")
    payments_store = importlib.import_module("payments_store")

    order, method = create_btc_order_and_method(monkeypatch)
    payment = payment_service.create_payment_for_order(order["id"], method["id"], "alice")

    def fake_http_json(url):
        if url.endswith("/address/bc1qqqqqqqqqqqqqqqqqqqq/txs"):
            return [
                {
                    "txid": "btc_tx_1",
                    "status": {"confirmed": True, "block_height": 100, "block_time": 2147483647},
                    "vout": [{"scriptpubkey_address": method["address"], "value": 39000}],
                }
            ]
        if url.endswith("/blocks/tip/height"):
            return 103
        raise AssertionError(url)

    monkeypatch.setattr(payment_verifier, "http_json", fake_http_json)

    refreshed = payment_service.refresh_payment(payment["id"], "alice")

    assert refreshed["status"] == "confirmed"
    assert refreshed["txid"] == "btc_tx_1"
    assert refreshed["detected_amount"] == "0.00039000"
    assert refreshed["confirmations"] == 4
    assert orders_store.get_order(order["id"])["status"] == "completed"
    assert payments_store.txid_used("btc_tx_1")


def test_refresh_without_txid_marks_btc_ambiguous_for_multiple_matches(payment_modules, monkeypatch):
    orders_store = importlib.import_module("orders_store")
    payment_service = importlib.import_module("payment_service")
    payment_verifier = importlib.import_module("payment_verifier")

    order, method = create_btc_order_and_method(monkeypatch)
    payment = payment_service.create_payment_for_order(order["id"], method["id"], "alice")

    def tx(txid):
        return {
            "txid": txid,
            "status": {"confirmed": True, "block_height": 100, "block_time": 2147483647},
            "vout": [{"scriptpubkey_address": method["address"], "value": 39000}],
        }

    def fake_http_json(url):
        if url.endswith("/address/bc1qqqqqqqqqqqqqqqqqqqq/txs"):
            return [tx("btc_tx_1"), tx("btc_tx_2")]
        if url.endswith("/blocks/tip/height"):
            return 103
        raise AssertionError(url)

    monkeypatch.setattr(payment_verifier, "http_json", fake_http_json)

    refreshed = payment_service.refresh_payment(payment["id"], "alice")

    assert refreshed["status"] == "ambiguous"
    assert "txid required" in refreshed["error"]
    order_after = orders_store.get_order(order["id"])
    assert order_after["status"] == "pending"
    assert order_after["payment_status"] == "ambiguous"


def test_optional_txid_can_recover_cancelled_order_after_payment(payment_modules, monkeypatch):
    orders_store = importlib.import_module("orders_store")
    payment_service = importlib.import_module("payment_service")
    user_admin = importlib.import_module("user_admin")

    order, method = create_standard_order_and_method(monkeypatch)
    payment = payment_service.create_payment_for_order(order["id"], method["id"], "alice")
    user_admin.cancel_order(order["id"], operator="alice")
    monkeypatch.setattr(
        payment_service,
        "verify_payment",
        lambda p, m: {
            "status": "confirmed",
            "detected_amount": p["crypto_amount"],
            "confirmations": 12,
            "txid": p.get("txid", "0xtx"),
            "error": "",
        },
    )

    done = payment_service.submit_tx_and_verify(payment["id"], "0xtx", "alice")

    assert done["status"] == "confirmed"
    order_after = orders_store.get_order(order["id"])
    assert order_after["status"] == "completed"
    assert order_after["payment_status"] == "confirmed"


def test_refresh_expired_payment_cancels_pending_order(payment_modules, monkeypatch):
    orders_store = importlib.import_module("orders_store")
    payments_store = importlib.import_module("payments_store")
    payment_service = importlib.import_module("payment_service")

    order, method = create_standard_order_and_method(monkeypatch)
    payment = payment_service.create_payment_for_order(order["id"], method["id"], "alice")
    payments_store.update_payment(payment["id"], expires_at="2000-01-01T00:00:00+00:00")

    expired = payment_service.refresh_payment(payment["id"], "alice")

    assert expired["status"] == "expired"
    order_after = orders_store.get_order(order["id"])
    assert order_after["status"] == "cancelled"
    assert order_after["payment_status"] == "expired"
    assert order_after["cancelled_by"] == "system"


def test_create_payment_for_order_reuses_existing_active_payment(payment_modules, monkeypatch):
    payments_store = importlib.import_module("payments_store")
    payment_service = importlib.import_module("payment_service")

    order, method = create_standard_order_and_method(monkeypatch)
    first = payment_service.create_payment_for_order(order["id"], method["id"], "alice")
    second = payment_service.create_payment_for_order(order["id"], method["id"], "alice")

    assert second["id"] == first["id"]
    assert len(payments_store.list_payments(username="alice", admin=True)) == 1


def test_old_confirmed_payment_does_not_complete_order(payment_modules, monkeypatch):
    orders_store = importlib.import_module("orders_store")
    payments_store = importlib.import_module("payments_store")
    payment_service = importlib.import_module("payment_service")
    user_admin = importlib.import_module("user_admin")

    order, method = create_standard_order_and_method(monkeypatch)
    current = payment_service.create_payment_for_order(order["id"], method["id"], "alice")
    old = payments_store.create_payment(
        {
            "order_id": order["id"],
            "username": "alice",
            "method_id": method["id"],
            "asset": method["asset"],
            "chain": method["chain"],
            "usd_amount": "39.0",
            "crypto_amount": "39.000000",
            "rate_usd": "1",
            "address": method["address"],
            "qr_payload": method["address"],
            "expires_at": "2099-01-01T00:00:00+00:00",
        }
    )
    payments_store.attach_txid(old["id"], "0xold")

    def fail_confirm(order_id, operator="admin"):
        raise AssertionError("old payment must not complete order")

    monkeypatch.setattr(user_admin, "confirm_order", fail_confirm)
    monkeypatch.setattr(
        payment_service,
        "verify_payment",
        lambda p, m: {"status": "confirmed", "detected_amount": p["crypto_amount"], "confirmations": 12, "error": ""},
    )
    verified_old = payment_service.refresh_payment(old["id"], "alice")
    assert verified_old["status"] == "confirmed"
    assert orders_store.get_order(order["id"])["status"] == "pending"
    assert orders_store.get_order(order["id"])["payment_id"] == current["id"]


def test_failed_payment_refresh_does_not_call_verifier_or_change_status(payment_modules, monkeypatch):
    payments_store = importlib.import_module("payments_store")
    payment_service = importlib.import_module("payment_service")

    order, method = create_standard_order_and_method(monkeypatch)
    payment = payment_service.create_payment_for_order(order["id"], method["id"], "alice")
    payments_store.update_payment(payment["id"], status="failed", txid="0xfailed", error="amount too low")

    def fail_verify(payment, method):
        raise AssertionError("final payment must not be verified again")

    monkeypatch.setattr(payment_service, "verify_payment", fail_verify)
    refreshed = payment_service.refresh_payment(payment["id"], "alice")
    submitted = payment_service.submit_tx_and_verify(payment["id"], "0xnew", "alice")

    assert refreshed["status"] == "failed"
    assert submitted["status"] == "failed"
    assert submitted["txid"] == "0xfailed"
    assert submitted["error"] == "amount too low"


def test_refresh_deleted_method_keeps_status_and_writes_error(payment_modules, monkeypatch):
    payments_store = importlib.import_module("payments_store")
    payment_service = importlib.import_module("payment_service")

    order, method = create_standard_order_and_method(monkeypatch)
    payment = payment_service.create_payment_for_order(order["id"], method["id"], "alice")
    payments_store.delete_method(method["id"])

    refreshed = payment_service.refresh_payment(payment["id"], "alice")

    assert refreshed["status"] == "awaiting_payment"
    assert "payment method not found" in refreshed["error"]


def test_payment_service_sanitizes_api_tokens_in_errors(payment_modules):
    payment_service = importlib.import_module("payment_service")

    error = payment_service._sanitize_error(
        "GET https://rpc.example/path?apikey=secret&token=another&keep=value&api_key=third failed"
    )

    assert "secret" not in error
    assert "another" not in error
    assert "third" not in error
    assert "apikey=[redacted]" in error
    assert "token=[redacted]" in error
    assert "api_key=[redacted]" in error

