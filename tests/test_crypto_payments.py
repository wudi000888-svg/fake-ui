import importlib
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
BASELINE = ROOT / "baseline"
if str(BASELINE) not in sys.path:
    sys.path.insert(0, str(BASELINE))


MODULES = [
    "panel_config",
    "json_store",
    "payments_store",
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

    with pytest.raises(RuntimeError, match="token contract"):
        payment_wallets.normalize_method(
            {
                "id": "bad-usdt",
                "asset": "USDT",
                "chain": "ethereum",
                "address": "0x2222222222222222222222222222222222222222",
                "rpc_url": "https://rpc.example",
            }
        )


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

    with pytest.raises(RuntimeError, match="rpc_url required"):
        payment_wallets.normalize_method(
            {
                "id": "missing-rpc",
                "asset": "ETH",
                "chain": "ethereum",
                "address": "0x2222222222222222222222222222222222222222",
            }
        )

    with pytest.raises(RuntimeError, match="btc_api_url required"):
        payment_wallets.normalize_method(
            {
                "id": "missing-btc-api",
                "asset": "BTC",
                "chain": "bitcoin",
                "address": "bc1qqqqqqqqqqqqqqqqqqqq",
            }
        )

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
