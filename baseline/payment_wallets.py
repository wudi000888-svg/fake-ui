import re
from copy import deepcopy


STABLE_ASSETS = {"USDT", "USDC"}
SUPPORTED = {
    ("USDT", "ethereum"),
    ("USDC", "ethereum"),
    ("USDT", "bsc"),
    ("USDC", "bsc"),
    ("ETH", "ethereum"),
    ("BNB", "bsc"),
    ("BTC", "bitcoin"),
}
EVM_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


def is_evm_chain(chain):
    return chain in ("ethereum", "bsc")


def normalize_bool(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on", "enabled"}:
        return True
    if text in {"0", "false", "no", "n", "off", "disabled", ""}:
        return False
    raise RuntimeError("invalid boolean value")


def clean_id(value):
    method_id = str(value or "").strip()
    if not method_id:
        raise RuntimeError("payment method id required")
    return method_id


def validate_evm_address(value, field="EVM address"):
    address = str(value or "").strip()
    if not EVM_ADDRESS_RE.match(address):
        raise RuntimeError(f"{field} invalid")
    return address.lower()


def _positive_int(value, field):
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        raise RuntimeError(f"{field} must be > 0")
    if number <= 0:
        raise RuntimeError(f"{field} must be > 0")
    return number


def _default_decimals(asset):
    if asset == "BTC":
        return 8
    if asset in {"ETH", "BNB"}:
        return 18
    return 6


def normalize_method(method):
    item = deepcopy(dict(method or {}))
    item["id"] = clean_id(item.get("id"))
    item["asset"] = str(item.get("asset") or "").strip().upper()
    item["chain"] = str(item.get("chain") or "").strip().lower()

    if (item["asset"], item["chain"]) not in SUPPORTED:
        raise RuntimeError("unsupported payment asset or chain")

    address = str(item.get("address") or "").strip()
    if not address:
        raise RuntimeError("payment address required")

    if is_evm_chain(item["chain"]):
        item["address"] = validate_evm_address(address)
        if not str(item.get("rpc_url") or "").strip():
            raise RuntimeError("rpc_url required")
        item["rpc_url"] = str(item["rpc_url"]).strip()
    elif item["chain"] == "bitcoin":
        item["address"] = address
        if not str(item.get("btc_api_url") or "").strip():
            raise RuntimeError("btc_api_url required")
        item["btc_api_url"] = str(item["btc_api_url"]).strip()

    if item["asset"] in STABLE_ASSETS:
        token_contract = item.get("token_contract")
        if not str(token_contract or "").strip():
            raise RuntimeError("token contract required")
        item["token_contract"] = validate_evm_address(token_contract, field="token contract")

    if "confirmations_required" in item:
        item["confirmations_required"] = _positive_int(
            item["confirmations_required"], "confirmations_required"
        )
    else:
        item["confirmations_required"] = 1

    if "decimals" in item:
        item["decimals"] = _positive_int(item["decimals"], "decimals")
    else:
        item["decimals"] = _default_decimals(item["asset"])

    if "enabled" in item:
        item["enabled"] = normalize_bool(item["enabled"])
    else:
        item["enabled"] = True

    return item


def qr_payload(method, amount):
    asset = str(method.get("asset") or "").strip().upper()
    chain = str(method.get("chain") or "").strip().lower()
    address = str(method.get("address") or "").strip()
    value = str(amount)
    if asset == "BTC" and chain == "bitcoin":
        return f"bitcoin:{address}?amount={value}"
    if asset in {"ETH", "BNB"} and is_evm_chain(chain):
        return f"ethereum:{address}?value={value}"
    if asset in STABLE_ASSETS:
        return address
    raise RuntimeError("unsupported payment asset or chain")
