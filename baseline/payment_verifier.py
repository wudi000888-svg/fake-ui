import json
import urllib.request
from decimal import Decimal, InvalidOperation, getcontext


getcontext().prec = 78

ERC20_TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"


def normalize_address(value):
    text = str(value or "").strip().lower()
    if text.startswith("0x"):
        return text
    return "0x" + text


def parse_hex_int(value, field):
    if isinstance(value, int):
        if value < 0:
            raise RuntimeError(f"{field} must be a non-negative integer")
        return value
    text = str(value or "").strip()
    if not text:
        raise RuntimeError(f"{field} required")
    try:
        number = int(text, 16 if text.lower().startswith("0x") else 10)
    except (TypeError, ValueError):
        raise RuntimeError(f"{field} must be valid hex") from None
    if number < 0:
        raise RuntimeError(f"{field} must be a non-negative integer")
    return number


def hex_int(value, default=0):
    if value is None:
        return default
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return default
    try:
        return int(text, 16 if text.lower().startswith("0x") else 10)
    except (TypeError, ValueError):
        return default


def topic_to_address(topic):
    text = normalize_address(topic)
    if len(text) < 42:
        return text
    return "0x" + text[-40:]


def amount_from_units(units, decimals):
    places = parse_decimals(decimals)
    amount = Decimal(int(units)) / (Decimal(10) ** places)
    return f"{amount:.{places}f}"


def parse_required_amount(value):
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, AttributeError):
        raise RuntimeError("required_amount must be a positive decimal") from None
    if not amount.is_finite() or amount <= 0:
        raise RuntimeError("required_amount must be a positive decimal")
    return amount


def parse_decimals(value):
    try:
        text = str(value).strip()
        places = int(text)
    except (TypeError, ValueError):
        raise RuntimeError("decimals must be an integer between 0 and 18") from None
    if text != str(places) or places < 0 or places > 18:
        raise RuntimeError("decimals must be an integer between 0 and 18")
    return places


def parse_confirmations_required(value):
    try:
        text = str(value).strip()
        confirmations = int(text)
    except (TypeError, ValueError):
        raise RuntimeError("confirmations_required must be > 0") from None
    if text != str(confirmations) or confirmations <= 0:
        raise RuntimeError("confirmations_required must be > 0")
    return confirmations


def _confirmations(block_number, current_height):
    block = parse_hex_int(block_number, "blockNumber")
    try:
        tip = int(str(current_height).strip())
    except (TypeError, ValueError):
        raise RuntimeError("current block must be a non-negative integer") from None
    if tip < 0:
        raise RuntimeError("current block must be a non-negative integer")
    if block <= 0 or tip < block:
        return 0
    return tip - block + 1


def status_for_amount_and_confirmations(amount, required_amount, confirmations, confirmations_required):
    detected = Decimal(str(amount).strip())
    required = parse_required_amount(required_amount)
    confirmations_needed = parse_confirmations_required(confirmations_required)
    if detected < required:
        return "failed"
    if int(confirmations) < confirmations_needed:
        return "detected"
    return "confirmed"


def _result(status, detected_amount, confirmations, error=""):
    return {
        "status": status,
        "detected_amount": detected_amount,
        "confirmations": confirmations,
        "error": error,
    }


def _failed(error, decimals=0, confirmations=0):
    try:
        detected_amount = amount_from_units(0, decimals)
    except RuntimeError:
        detected_amount = "0"
    return _result("failed", detected_amount, confirmations, str(error) or "verification failed")


def _receipt_status_failed(receipt):
    item = dict(receipt or {})
    if "status" not in item:
        return False
    return item.get("status") not in ("0x1", "1", 1, True)


def verify_evm_erc20_receipt(
    receipt,
    current_block,
    token_contract,
    to_address,
    required_amount,
    decimals,
    confirmations_required,
):
    try:
        places = parse_decimals(decimals)
        parse_required_amount(required_amount)
        confirmations_needed = parse_confirmations_required(confirmations_required)
        item = dict(receipt or {})
        confirmations = _confirmations(item.get("blockNumber"), current_block)
        zero_amount = amount_from_units(0, places)
        if _receipt_status_failed(item):
            return _result("failed", zero_amount, confirmations, "transaction failed")

        wanted_contract = normalize_address(token_contract)
        wanted_to = normalize_address(to_address)
        total_units = 0

        for log in item.get("logs", []) or []:
            log = dict(log or {})
            topics = list(log.get("topics", []) or [])
            if normalize_address(log.get("address")) != wanted_contract:
                continue
            if len(topics) < 3 or str(topics[0]).lower() != ERC20_TRANSFER_TOPIC:
                continue
            if topic_to_address(topics[2]) != wanted_to:
                continue
            total_units += parse_hex_int(log.get("data"), "log data")

        detected_amount = amount_from_units(total_units, places)
        status = status_for_amount_and_confirmations(
            detected_amount, required_amount, confirmations, confirmations_needed
        )
        error = ""
        if total_units == 0:
            error = "matching ERC20 transfer not found"
        elif status == "failed":
            error = "detected amount below required amount"
        elif status == "detected":
            error = "confirmations below required amount"
        return _result(status, detected_amount, confirmations, error)
    except RuntimeError as exc:
        return _failed(exc, decimals)


def verify_evm_native_tx(tx, current_block, to_address, required_amount, decimals, confirmations_required):
    try:
        places = parse_decimals(decimals)
        parse_required_amount(required_amount)
        confirmations_needed = parse_confirmations_required(confirmations_required)
        item = dict(tx or {})
        confirmations = _confirmations(item.get("blockNumber"), current_block)
        detected_amount = amount_from_units(parse_hex_int(item.get("value"), "value"), places)

        if normalize_address(item.get("to")) != normalize_address(to_address):
            return _result("failed", amount_from_units(0, places), confirmations, "destination address mismatch")

        status = status_for_amount_and_confirmations(
            detected_amount, required_amount, confirmations, confirmations_needed
        )
        error = ""
        if status == "failed":
            error = "detected amount below required amount"
        elif status == "detected":
            error = "confirmations below required amount"
        return _result(status, detected_amount, confirmations, error)
    except RuntimeError as exc:
        return _failed(exc, decimals)


def verify_btc_tx(tx, tip_height, to_address, required_amount, confirmations_required):
    try:
        parse_required_amount(required_amount)
        confirmations_needed = parse_confirmations_required(confirmations_required)
        item = dict(tx or {})
        status = dict(item.get("status") or {})
        block_height = int(status.get("block_height") or 0)
        confirmations = 0
        if status.get("confirmed") and block_height > 0 and int(tip_height or 0) >= block_height:
            confirmations = int(tip_height) - block_height + 1

        total_sats = 0
        for output in item.get("vout", []) or []:
            output = dict(output or {})
            if str(output.get("scriptpubkey_address") or "") == str(to_address or ""):
                total_sats += int(output.get("value") or 0)

        detected_amount = amount_from_units(total_sats, 8)
        parsed_status = status_for_amount_and_confirmations(
            detected_amount, required_amount, confirmations, confirmations_needed
        )
        error = ""
        if total_sats == 0:
            error = "matching Bitcoin output not found"
        elif parsed_status == "failed":
            error = "detected amount below required amount"
        elif parsed_status == "detected":
            error = "confirmations below required amount"
        return _result(parsed_status, detected_amount, confirmations, error)
    except (RuntimeError, TypeError, ValueError) as exc:
        return _failed(exc, 8)


def rpc_call(rpc_url, method, params):
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode("utf-8")
    request = urllib.request.Request(
        str(rpc_url),
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        data = json.loads(response.read().decode("utf-8"))
    if data.get("error"):
        error = data["error"]
        message = error.get("message") if isinstance(error, dict) else None
        raise RuntimeError(str(message or "rpc error")[:200])
    return data.get("result")


def http_json(url):
    request = urllib.request.Request(str(url), headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))
