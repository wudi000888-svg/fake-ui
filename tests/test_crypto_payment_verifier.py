from payment_test_utils import importlib, json, pytest, payment_modules, pad_topic_address

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

