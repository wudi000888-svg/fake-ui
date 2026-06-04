import importlib
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
BASELINE = ROOT / "baseline"
if str(BASELINE) not in sys.path:
    sys.path.insert(0, str(BASELINE))


MODULES = [
    "auth_store",
    "user_store",
    "node_catalog",
    "plans_store",
    "orders_store",
    "audit_log",
    "admin_profile",
    "operations_service",
    "user_admin",
    "panel_config",
    "json_store",
    "payments_store",
    "payment_rates",
    "payment_wallets",
    "payment_verifier",
    "payment_service",
    "api_payment_routes",
]


@pytest.fixture()
def payment_modules(tmp_path, monkeypatch):
    panel_dir = tmp_path / "panel"
    panel_dir.mkdir()
    monkeypatch.setenv("PANEL_DIR", str(panel_dir))
    for name in MODULES:
        if name in sys.modules:
            importlib.reload(sys.modules[name])
        else:
            importlib.import_module(name)
    return {name: sys.modules[name] for name in MODULES}


def test_payment_method_crud_and_user_visibility(payment_modules):
    store = payment_modules["payments_store"]
    method = store.upsert_method(
        {
            "id": "usdt-eth",
            "asset": "USDT",
            "chain": "ethereum",
            "address": "0x1111111111111111111111111111111111111111",
            "token_contract": "0xdac17f958d2ee523a2206206994597c13d831ec7",
            "decimals": "6",
            "rpc_url": "https://rpc.example",
            "confirmations_required": "12",
            "enabled": True,
        }
    )
    assert method["asset"] == "USDT"
    assert method["chain"] == "ethereum"
    assert method["enabled"] is True
    assert store.get_method("usdt-eth")["rpc_url"] == "https://rpc.example"
    assert store.list_methods(admin=False)[0]["id"] == "usdt-eth"
    assert "rpc_url" not in store.list_methods(admin=False)[0]

    store.set_method_enabled("usdt-eth", False)
    assert store.list_methods(admin=False) == []
    assert store.list_methods(admin=True)[0]["enabled"] is False


def test_minimal_payment_method_uses_builtin_defaults(payment_modules):
    store = payment_modules["payments_store"]
    method = store.upsert_method(
        {
            "asset": "USDT",
            "chain": "bsc",
            "address": "0x2222222222222222222222222222222222222222",
        }
    )

    assert method["id"] == "usdt-bsc"
    assert method["token_contract"] == "0x55d398326f99059ff775485246999027b3197955"
    assert method["decimals"] == 18
    assert method["confirmations_required"] == 12
    assert method["sort"] == 110
    assert method["rpc_url"] == "https://bsc-rpc.publicnode.com"
    assert "https://bsc-dataseed.binance.org" in method["rpc_urls"]

    public = store.list_methods(admin=False)[0]
    assert public["id"] == "usdt-bsc"
    assert "rpc_url" not in public
    assert "rpc_urls" not in public
    assert "token_contract" not in public

    btc = store.upsert_method(
        {
            "asset": "BTC",
            "chain": "bitcoin",
            "address": "bc1qqqqqqqqqqqqqqqqqqqq",
        }
    )
    assert btc["id"] == "btc-main"
    assert btc["decimals"] == 8
    assert btc["confirmations_required"] == 3
    assert btc["btc_api_url"] == "https://blockstream.info/api"
    assert "https://mempool.space/api" in btc["btc_api_urls"]


def test_payment_intent_creation_and_txid_uniqueness(payment_modules):
    store = payment_modules["payments_store"]
    payment = store.create_payment(
        {
            "order_id": "ord_1",
            "username": "alice",
            "method_id": "btc-main",
            "asset": "BTC",
            "chain": "bitcoin",
            "usd_amount": "39.00",
            "crypto_amount": "0.00039000",
            "rate_usd": "100000",
            "address": "bc1qexample",
            "qr_payload": "bitcoin:bc1qexample?amount=0.00039000",
            "expires_at": "2099-01-01T00:00:00+00:00",
        }
    )
    assert payment["id"].startswith("pay_")
    assert payment["status"] == "awaiting_payment"

    updated = store.attach_txid(payment["id"], "tx123")
    assert updated["txid"] == "tx123"
    other = store.create_payment(
        {
            "order_id": "ord_2",
            "username": "bob",
            "method_id": "btc-main",
            "asset": "BTC",
            "chain": "bitcoin",
            "usd_amount": "39.00",
            "crypto_amount": "0.00039000",
            "rate_usd": "100000",
            "address": "bc1qexample",
            "qr_payload": "bitcoin:bc1qexample?amount=0.00039000",
            "expires_at": "2099-01-01T00:00:00+00:00",
        }
    )
    with pytest.raises(RuntimeError, match="txid already used"):
        store.attach_txid(other["id"], "tx123")


def test_payment_public_helpers_update_kwargs_and_list_limit(payment_modules):
    store = payment_modules["payments_store"]
    method = {
        "id": "btc-main",
        "asset": "BTC",
        "chain": "bitcoin",
        "address": "bc1qqqqqqqqqqqqqqqqqqqq",
        "btc_api_url": "https://btc-api.example",
        "api_key": "example-api-key",
        "enabled": True,
    }
    assert "btc_api_url" in store.public_method(method, admin=True)
    assert "btc_api_url" not in store.public_method(method, admin=False)
    assert "api_key" not in store.public_method(method, admin=False)
    store.upsert_method(method)
    assert "api_key" not in store.list_methods(admin=False)[0]

    first = store.create_payment(
        {
            "order_id": "ord_1",
            "username": "alice",
            "method_id": "btc-main",
            "asset": "BTC",
            "chain": "bitcoin",
            "usd_amount": "39.00",
            "crypto_amount": "0.00039000",
            "rate_usd": "100000",
            "address": "bc1qqqqqqqqqqqqqqqqqqqq",
            "qr_payload": "bitcoin:bc1qqqqqqqqqqqqqqqqqqqq?amount=0.00039000",
            "expires_at": "2099-01-01T00:00:00+00:00",
            "created_at": "2026-01-01T00:00:00+00:00",
        }
    )
    second = store.create_payment(
        {
            "order_id": "ord_2",
            "username": "alice",
            "method_id": "btc-main",
            "asset": "BTC",
            "chain": "bitcoin",
            "usd_amount": "49.00",
            "crypto_amount": "0.00049000",
            "rate_usd": "100000",
            "address": "bc1qqqqqqqqqqqqqqqqqqqq",
            "qr_payload": "bitcoin:bc1qqqqqqqqqqqqqqqqqqqq?amount=0.00049000",
            "expires_at": "2099-01-01T00:00:00+00:00",
            "created_at": "2026-01-02T00:00:00+00:00",
        }
    )

    updated = store.update_payment(
        first["id"],
        status="detected",
        detected_amount="0.00039000",
        internal_note="manual review",
    )
    assert updated["status"] == "detected"
    assert updated["detected_amount"] == "0.00039000"
    assert store.public_payment(updated, admin=True)["internal_note"] == "manual review"
    assert "internal_note" not in store.public_payment(updated, admin=False)
    assert store.list_payments(admin=False, username=None) == []

    public_items = store.list_payments(username="alice", admin=False, limit=1)
    assert len(public_items) == 1
    assert public_items[0]["id"] == second["id"]
    assert "internal_note" not in public_items[0]

    admin_items = store.list_payments(username="alice", admin=True, limit=2)
    assert [item["id"] for item in admin_items] == [second["id"], first["id"]]
    assert admin_items[1]["internal_note"] == "manual review"

    store.update_payment(first["id"], txid="tx123")
    with pytest.raises(RuntimeError, match="txid already used"):
        store.update_payment(second["id"], txid="TX123")


def test_payment_method_validation_and_qr_payloads(payment_modules):
    payment_wallets = importlib.import_module("payment_wallets")

    evm = payment_wallets.normalize_method(
        {
            "id": "eth-main",
            "asset": "ETH",
            "chain": "ethereum",
            "address": "0x2222222222222222222222222222222222222222",
            "rpc_url": "https://rpc.example",
            "confirmations_required": "12",
        }
    )
    assert evm["decimals"] == 18
    assert (
        payment_wallets.qr_payload(evm, "0.010000000000000000")
        == "ethereum:0x2222222222222222222222222222222222222222?value=0.010000000000000000"
    )

    btc = payment_wallets.normalize_method(
        {
            "id": "btc-main",
            "asset": "BTC",
            "chain": "bitcoin",
            "address": "bc1qqqqqqqqqqqqqqqqqqqq",
            "btc_api_url": "https://blockstream.info/api",
            "confirmations_required": "3",
        }
    )
    assert btc["decimals"] == 8
    assert (
        payment_wallets.qr_payload(btc, "0.00039000")
        == "bitcoin:bc1qqqqqqqqqqqqqqqqqqqq?amount=0.00039000"
    )

    bnb = payment_wallets.normalize_method(
        {
            "id": "bnb-main",
            "asset": "BNB",
            "chain": "bsc",
            "address": "0x2222222222222222222222222222222222222222",
            "rpc_url": "https://rpc.example",
        }
    )
    assert payment_wallets.qr_payload(bnb, "0.100000000000000000") == bnb["address"]

    usdt_default = payment_wallets.normalize_method(
        {
            "id": "bad-usdt",
            "asset": "USDT",
            "chain": "ethereum",
            "address": "0x2222222222222222222222222222222222222222",
            "rpc_url": "https://rpc.example",
        }
    )
    assert usdt_default["token_contract"] == "0xdac17f958d2ee523a2206206994597c13d831ec7"


def test_payment_method_validation_rejects_bad_wallet_config(payment_modules):
    payment_wallets = importlib.import_module("payment_wallets")
    store = payment_modules["payments_store"]

    with pytest.raises(RuntimeError, match="unsupported payment asset or chain"):
        payment_wallets.normalize_method(
            {
                "id": "eth-bsc",
                "asset": "ETH",
                "chain": "bsc",
                "address": "0x2222222222222222222222222222222222222222",
                "rpc_url": "https://rpc.example",
            }
        )

    with pytest.raises(RuntimeError, match="EVM address"):
        payment_wallets.normalize_method(
            {
                "id": "bad-address",
                "asset": "ETH",
                "chain": "ethereum",
                "address": "0xnot-an-address",
                "rpc_url": "https://rpc.example",
            }
        )

    eth_default = payment_wallets.normalize_method(
        {
            "id": "missing-rpc",
            "asset": "ETH",
            "chain": "ethereum",
            "address": "0x2222222222222222222222222222222222222222",
        }
    )
    assert eth_default["rpc_url"] == "https://ethereum-rpc.publicnode.com"

    btc_default = payment_wallets.normalize_method(
        {
            "id": "missing-btc-api",
            "asset": "BTC",
            "chain": "bitcoin",
            "address": "bc1qqqqqqqqqqqqqqqqqqqq",
        }
    )
    assert btc_default["btc_api_url"] == "https://blockstream.info/api"

    with pytest.raises(RuntimeError, match="Bitcoin address"):
        payment_wallets.normalize_method(
            {
                "id": "bad-btc-address",
                "asset": "BTC",
                "chain": "bitcoin",
                "address": "not-a-wallet",
                "btc_api_url": "https://btc-api.example",
            }
        )

    with pytest.raises(RuntimeError, match="unsupported payment asset or chain"):
        store.upsert_method(
            {
                "id": "eth-bsc",
                "asset": "ETH",
                "chain": "bsc",
                "address": "0x2222222222222222222222222222222222222222",
                "rpc_url": "https://rpc.example",
            }
        )
    assert store.list_methods(admin=True) == []

    with pytest.raises(RuntimeError, match="Bitcoin address"):
        store.upsert_method(
            {
                "id": "bad-btc-address",
                "asset": "BTC",
                "chain": "bitcoin",
                "address": "not-a-wallet",
                "btc_api_url": "https://btc-api.example",
            }
        )
    assert store.list_methods(admin=True) == []


def test_upsert_method_preserves_existing_created_at(payment_modules):
    store = payment_modules["payments_store"]

    first = store.upsert_method(
        {
            "id": "btc-main",
            "asset": "BTC",
            "chain": "bitcoin",
            "address": "bc1qqqqqqqqqqqqqqqqqqqq",
            "btc_api_url": "https://btc-api.example",
        }
    )
    original_created_at = first["created_at"]

    updated = store.upsert_method(
        {
            "id": "btc-main",
            "asset": "BTC",
            "chain": "bitcoin",
            "address": "bc1qqqqqqqqqqqqqqqqqqqq",
            "btc_api_url": "https://btc-api.example/v2",
            "created_at": "2099-01-01T00:00:00+00:00",
        }
    )

    assert updated["created_at"] == original_created_at
    assert updated["updated_at"]
    assert store.get_method("btc-main")["created_at"] == original_created_at


def test_payment_rates_lock_amounts_with_overrides(payment_modules):
    payment_rates = importlib.import_module("payment_rates")
    payments_store = payment_modules["payments_store"]

    payments_store.save_rates({"overrides": {"ETH": "3000"}, "cache": {"BTC": {"rate_usd": "100000", "updated_at": "now"}}})

    assert payment_rates.rate_for_asset("USDT") == "1"
    assert payment_rates.rate_for_asset("ETH") == "3000"
    assert payment_rates.rate_for_asset("BTC") == "100000"
    assert payment_rates.crypto_amount_for_usd("39", "ETH", 18) == "0.013000000000000000"
    assert payment_rates.crypto_amount_for_usd("39", "BTC", 8) == "0.00039000"


def test_payment_rates_validate_overrides(payment_modules):
    payment_rates = importlib.import_module("payment_rates")
    payments_store = payment_modules["payments_store"]

    payments_store.save_rates({"overrides": {}, "cache": {"BTC": {"rate_usd": "30000", "updated_at": "now"}}})

    with pytest.raises(RuntimeError, match="rate must be positive"):
        payment_rates.save_overrides({"ETH": "0"})

    saved = payment_rates.save_overrides({"ETH": "3000"})
    assert saved["overrides"] == {"ETH": "3000"}
    assert saved["cache"] == {"BTC": {"rate_usd": "30000", "updated_at": "now"}}


def test_payment_rates_require_missing_volatile_rates(payment_modules):
    payment_rates = importlib.import_module("payment_rates")

    with pytest.raises(RuntimeError, match="missing USD rate for ETH"):
        payment_rates.rate_for_asset("ETH")


def test_payment_rates_round_up_and_support_usdc(payment_modules):
    payment_rates = importlib.import_module("payment_rates")
    payments_store = payment_modules["payments_store"]

    payments_store.save_rates({"overrides": {"BTC": "30000"}, "cache": {}})

    assert payment_rates.rate_for_asset("USDC") == "1"
    assert payment_rates.crypto_amount_for_usd("1", "BTC", 8) == "0.00003334"


def test_payment_rates_reject_invalid_amounts_and_decimals(payment_modules):
    payment_rates = importlib.import_module("payment_rates")
    payments_store = payment_modules["payments_store"]

    payments_store.save_rates({"overrides": {"BTC": "30000"}, "cache": {}})

    with pytest.raises(RuntimeError, match="usd amount must be positive"):
        payment_rates.crypto_amount_for_usd("-1", "BTC", 8)

    with pytest.raises(RuntimeError, match="usd amount must be positive"):
        payment_rates.crypto_amount_for_usd("0", "BTC", 8)

    with pytest.raises(RuntimeError, match="decimals"):
        payment_rates.crypto_amount_for_usd("1", "BTC", "8.5")

    with pytest.raises(RuntimeError, match="decimals"):
        payment_rates.crypto_amount_for_usd("1", "BTC", 19)


def pad_topic_address(addr):
    return "0x" + ("0" * 24) + addr.lower().replace("0x", "")


def test_evm_erc20_and_native_verification_parsers(payment_modules):
    verifier = importlib.import_module("payment_verifier")
    receiver = "0x2222222222222222222222222222222222222222"
    sender = "0x1111111111111111111111111111111111111111"
    contract = "0xdac17f958d2ee523a2206206994597c13d831ec7"
    transfer_topic = verifier.ERC20_TRANSFER_TOPIC
    receipt = {
        "blockNumber": "0x64",
        "logs": [
            {
                "address": contract,
                "topics": [transfer_topic, pad_topic_address(sender), pad_topic_address(receiver)],
                "data": "0x" + format(39000000, "064x"),
            }
        ],
    }
    result = verifier.verify_evm_erc20_receipt(
        receipt,
        current_block=120,
        token_contract=contract,
        to_address=receiver,
        required_amount="39.000000",
        decimals=6,
        confirmations_required=12,
    )
    assert result["status"] == "confirmed"
    assert result["detected_amount"] == "39.000000"
    assert result["confirmations"] == 21

    tx = {"to": receiver, "value": "0x" + format(13000000000000000, "x"), "blockNumber": "0x64"}
    native = verifier.verify_evm_native_tx(
        tx,
        current_block=120,
        to_address=receiver,
        required_amount="0.013000000000000000",
        decimals=18,
        confirmations_required=12,
    )
    assert native["status"] == "confirmed"


def test_btc_verification_parser(payment_modules):
    verifier = importlib.import_module("payment_verifier")
    tx = {
        "status": {"confirmed": True, "block_height": 100},
        "vout": [
            {"scriptpubkey_address": "bc1qexample", "value": 39000},
            {"scriptpubkey_address": "bc1qother", "value": 1000},
        ],
    }
    result = verifier.verify_btc_tx(
        tx,
        tip_height=103,
        to_address="bc1qexample",
        required_amount="0.00039000",
        confirmations_required=3,
    )
    assert result["status"] == "confirmed"
    assert result["detected_amount"] == "0.00039000"
    assert result["confirmations"] == 4


def test_evm_verification_parser_edge_cases(payment_modules):
    verifier = importlib.import_module("payment_verifier")
    receiver = "0x2222222222222222222222222222222222222222"
    sender = "0x1111111111111111111111111111111111111111"
    contract = "0xdac17f958d2ee523a2206206994597c13d831ec7"
    other_contract = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
    receipt = {
        "blockNumber": "0x64",
        "logs": [
            {
                "address": contract,
                "topics": [verifier.ERC20_TRANSFER_TOPIC, pad_topic_address(sender), pad_topic_address(receiver)],
                "data": "0x" + format(39000000, "064x"),
            }
        ],
    }

    wrong_token = verifier.verify_evm_erc20_receipt(
        receipt,
        current_block=120,
        token_contract=other_contract,
        to_address=receiver,
        required_amount="39.000000",
        decimals=6,
        confirmations_required=12,
    )
    assert wrong_token["status"] == "failed"
    assert wrong_token["detected_amount"] == "0.000000"
    assert wrong_token["error"]

    not_enough_confirmations = verifier.verify_evm_erc20_receipt(
        receipt,
        current_block=105,
        token_contract=contract,
        to_address=receiver,
        required_amount="39.000000",
        decimals=6,
        confirmations_required=12,
    )
    assert not_enough_confirmations["status"] == "detected"
    assert not_enough_confirmations["confirmations"] == 6

    wrong_native_to = verifier.verify_evm_native_tx(
        {"to": sender, "value": "0x" + format(13000000000000000, "x"), "blockNumber": "0x64"},
        current_block=120,
        to_address=receiver,
        required_amount="0.013000000000000000",
        decimals=18,
        confirmations_required=12,
    )
    assert wrong_native_to["status"] == "failed"
    assert wrong_native_to["error"]


def test_btc_verification_parser_edge_cases(payment_modules):
    verifier = importlib.import_module("payment_verifier")
    tx = {
        "status": {"confirmed": True, "block_height": 100},
        "vout": [{"scriptpubkey_address": "bc1qexample", "value": 39000}],
    }

    not_enough_confirmations = verifier.verify_btc_tx(
        tx,
        tip_height=101,
        to_address="bc1qexample",
        required_amount="0.00039000",
        confirmations_required=3,
    )
    assert not_enough_confirmations["status"] == "detected"
    assert not_enough_confirmations["confirmations"] == 2

    low_amount = verifier.verify_btc_tx(
        tx,
        tip_height=103,
        to_address="bc1qexample",
        required_amount="0.00040000",
        confirmations_required=3,
    )
    assert low_amount["status"] == "failed"
    assert low_amount["detected_amount"] == "0.00039000"


def test_evm_erc20_verification_accumulates_matching_logs(payment_modules):
    verifier = importlib.import_module("payment_verifier")
    receiver = "0x2222222222222222222222222222222222222222"
    sender = "0x1111111111111111111111111111111111111111"
    contract = "0xdac17f958d2ee523a2206206994597c13d831ec7"
    receipt = {
        "status": "0x1",
        "blockNumber": "0x64",
        "logs": [
            {
                "address": contract,
                "topics": [verifier.ERC20_TRANSFER_TOPIC, pad_topic_address(sender), pad_topic_address(receiver)],
                "data": "0x" + format(20000000, "064x"),
            },
            {
                "address": contract,
                "topics": [verifier.ERC20_TRANSFER_TOPIC, pad_topic_address(sender), pad_topic_address(receiver)],
                "data": "0x" + format(19000000, "064x"),
            },
        ],
    }

    result = verifier.verify_evm_erc20_receipt(
        receipt,
        current_block=120,
        token_contract=contract,
        to_address=receiver,
        required_amount="39.000000",
        decimals=6,
        confirmations_required=12,
    )

    assert result["status"] == "confirmed"
    assert result["detected_amount"] == "39.000000"
    assert result["confirmations"] == 21


def test_evm_erc20_verification_rejects_failed_receipt_status(payment_modules):
    verifier = importlib.import_module("payment_verifier")
    receiver = "0x2222222222222222222222222222222222222222"
    sender = "0x1111111111111111111111111111111111111111"
    contract = "0xdac17f958d2ee523a2206206994597c13d831ec7"
    receipt = {
        "status": "0x0",
        "blockNumber": "0x64",
        "logs": [
            {
                "address": contract,
                "topics": [verifier.ERC20_TRANSFER_TOPIC, pad_topic_address(sender), pad_topic_address(receiver)],
                "data": "0x" + format(39000000, "064x"),
            }
        ],
    }

    result = verifier.verify_evm_erc20_receipt(
        receipt,
        current_block=120,
        token_contract=contract,
        to_address=receiver,
        required_amount="39.000000",
        decimals=6,
        confirmations_required=12,
    )

    assert result["status"] == "failed"
    assert result["error"]


def test_verifiers_fail_closed_for_malformed_inputs(payment_modules):
    verifier = importlib.import_module("payment_verifier")
    receiver = "0x2222222222222222222222222222222222222222"
    sender = "0x1111111111111111111111111111111111111111"
    contract = "0xdac17f958d2ee523a2206206994597c13d831ec7"
    valid_receipt = {
        "status": "0x1",
        "blockNumber": "0x64",
        "logs": [
            {
                "address": contract,
                "topics": [verifier.ERC20_TRANSFER_TOPIC, pad_topic_address(sender), pad_topic_address(receiver)],
                "data": "0x" + format(39000000, "064x"),
            }
        ],
    }

    bad_data = dict(valid_receipt)
    bad_data["logs"] = [dict(valid_receipt["logs"][0], data="0xnot-hex")]
    erc20_bad_data = verifier.verify_evm_erc20_receipt(
        bad_data,
        current_block=120,
        token_contract=contract,
        to_address=receiver,
        required_amount="39.000000",
        decimals=6,
        confirmations_required=12,
    )
    assert erc20_bad_data["status"] == "failed"
    assert erc20_bad_data["error"]

    native_bad_value = verifier.verify_evm_native_tx(
        {"to": receiver, "value": "0xnot-hex", "blockNumber": "0x64"},
        current_block=120,
        to_address=receiver,
        required_amount="0.013000000000000000",
        decimals=18,
        confirmations_required=12,
    )
    assert native_bad_value["status"] == "failed"
    assert native_bad_value["error"]

    invalid_required = verifier.verify_evm_erc20_receipt(
        valid_receipt,
        current_block=120,
        token_contract=contract,
        to_address=receiver,
        required_amount="NaN",
        decimals=6,
        confirmations_required=12,
    )
    assert invalid_required["status"] == "failed"
    assert invalid_required["error"]

    invalid_decimals = verifier.verify_evm_erc20_receipt(
        valid_receipt,
        current_block=120,
        token_contract=contract,
        to_address=receiver,
        required_amount="39.000000",
        decimals=19,
        confirmations_required=12,
    )
    assert invalid_decimals["status"] == "failed"
    assert invalid_decimals["error"]

    invalid_confirmations = verifier.verify_evm_erc20_receipt(
        valid_receipt,
        current_block=120,
        token_contract=contract,
        to_address=receiver,
        required_amount="39.000000",
        decimals=6,
        confirmations_required=0,
    )
    assert invalid_confirmations["status"] == "failed"
    assert invalid_confirmations["error"]


def test_rpc_call_sanitizes_json_rpc_error(monkeypatch, payment_modules):
    verifier = importlib.import_module("payment_verifier")
    long_message = "bad rpc " + ("x" * 250)

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return json.dumps({"error": {"message": long_message, "secret": "do-not-leak"}}).encode("utf-8")

    monkeypatch.setattr(verifier.urllib.request, "urlopen", lambda request, timeout: FakeResponse())

    with pytest.raises(RuntimeError) as excinfo:
        verifier.rpc_call("https://rpc.example", "eth_getTransactionReceipt", ["0xabc"])

    error = str(excinfo.value)
    assert error == long_message[:200]
    assert "secret" not in error


def test_rpc_and_http_json_send_user_agent(monkeypatch, payment_modules):
    verifier = importlib.import_module("payment_verifier")
    seen = []

    class FakeResponse:
        def __init__(self, body):
            self.body = body

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return self.body

    def fake_urlopen(request, timeout):
        seen.append(dict(request.header_items()))
        if request.full_url.endswith("/rpc"):
            return FakeResponse(json.dumps({"result": "0x1"}).encode("utf-8"))
        return FakeResponse(json.dumps({"ok": True}).encode("utf-8"))

    monkeypatch.setattr(verifier.urllib.request, "urlopen", fake_urlopen)

    assert verifier.rpc_call("https://example.test/rpc", "eth_blockNumber", []) == "0x1"
    assert verifier.http_json("https://example.test/api") == {"ok": True}

    assert seen[0]["User-agent"].startswith("fake-ui/")
    assert seen[1]["User-agent"].startswith("fake-ui/")


def test_rpc_call_falls_back_to_next_public_endpoint(monkeypatch, payment_modules):
    verifier = importlib.import_module("payment_verifier")
    seen_urls = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return json.dumps({"result": "0x2a"}).encode("utf-8")

    def fake_urlopen(request, timeout):
        seen_urls.append(request.full_url)
        if len(seen_urls) == 1:
            raise RuntimeError("HTTP Error 403: Forbidden")
        return FakeResponse()

    monkeypatch.setattr(verifier.urllib.request, "urlopen", fake_urlopen)

    assert verifier.rpc_call(["https://blocked.example", "https://ok.example"], "eth_blockNumber", []) == "0x2a"
    assert seen_urls == ["https://blocked.example", "https://ok.example"]


def test_rpc_call_falls_back_on_public_limit_json_rpc_error(monkeypatch, payment_modules):
    verifier = importlib.import_module("payment_verifier")
    seen_urls = []

    class FakeResponse:
        def __init__(self, body):
            self.body = body

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return self.body

    def fake_urlopen(request, timeout):
        seen_urls.append(request.full_url)
        if len(seen_urls) == 1:
            return FakeResponse(json.dumps({"error": {"message": "limit exceeded"}}).encode("utf-8"))
        return FakeResponse(json.dumps({"result": "0x2b"}).encode("utf-8"))

    monkeypatch.setattr(verifier.urllib.request, "urlopen", fake_urlopen)

    assert verifier.rpc_call(["https://limited.example", "https://ok.example"], "eth_getLogs", []) == "0x2b"
    assert seen_urls == ["https://limited.example", "https://ok.example"]


def create_standard_order_and_method(monkeypatch):
    plans_store = importlib.import_module("plans_store")
    orders_store = importlib.import_module("orders_store")
    payments_store = importlib.import_module("payments_store")
    user_admin = importlib.import_module("user_admin")

    monkeypatch.setattr(user_admin, "enforce_users_now", lambda: "ok")
    plan = plans_store.upsert_plan(
        {"id": "standard", "name": "Standard", "days": "30", "traffic_gb": "100", "price": "39"}
    )
    order = orders_store.create_pending_order("alice", "renew", plan, operator="alice")
    method = payments_store.upsert_method(
        {
            "id": "usdt-eth",
            "asset": "USDT",
            "chain": "ethereum",
            "address": "0x2222222222222222222222222222222222222222",
            "token_contract": "0xdac17f958d2ee523a2206206994597c13d831ec7",
            "decimals": "6",
            "rpc_url": "https://rpc.example",
            "confirmations_required": "12",
            "enabled": True,
        }
    )
    return order, method


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


def user_session(username):
    return {"u": username, "r": "user", "role": "user"}


def admin_session_for_payments():
    return {"u": "admin", "r": "admin", "role": "admin"}


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
