from decimal import Decimal, InvalidOperation, ROUND_UP, getcontext

import payments_store


getcontext().prec = 42
STABLES = {"USDT", "USDC"}


def _asset_text(asset):
    return str(asset or "").strip().upper()


def decimal_text(value):
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, AttributeError):
        raise RuntimeError("invalid decimal amount") from None
    if not amount.is_finite():
        raise RuntimeError("invalid decimal amount")
    return amount


def _rate_text(value):
    rate = decimal_text(value)
    if rate <= 0:
        raise RuntimeError("rate must be positive")
    return format(rate, "f")


def _decimals_value(decimals):
    try:
        text = str(decimals).strip()
        places = int(text)
    except (TypeError, ValueError):
        raise RuntimeError("decimals must be an integer between 0 and 18") from None
    if text != str(places) or places < 0 or places > 18:
        raise RuntimeError("decimals must be an integer between 0 and 18")
    return places


def rate_for_asset(asset):
    normalized_asset = _asset_text(asset)
    if normalized_asset in STABLES:
        return "1"

    rates = payments_store.load_rates()
    overrides = rates.get("overrides", {})
    if normalized_asset in overrides:
        return _rate_text(overrides[normalized_asset])

    cache = rates.get("cache", {})
    cached = cache.get(normalized_asset, {})
    if isinstance(cached, dict) and cached.get("rate_usd") is not None:
        return _rate_text(cached["rate_usd"])

    raise RuntimeError(f"missing USD rate for {normalized_asset}")


def crypto_amount_for_usd(usd_amount, asset, decimals):
    places = _decimals_value(decimals)
    usd = decimal_text(usd_amount)
    if usd <= 0:
        raise RuntimeError("usd amount must be positive")

    rate = Decimal(rate_for_asset(asset))
    quant = Decimal(1).scaleb(-places)
    amount = (usd / rate).quantize(quant, rounding=ROUND_UP)
    return f"{amount:.{places}f}"


def save_overrides(overrides):
    cleaned = {}
    for asset, rate in dict(overrides or {}).items():
        normalized_asset = _asset_text(asset)
        if not normalized_asset:
            raise RuntimeError("asset required")
        cleaned[normalized_asset] = _rate_text(rate)

    rates = payments_store.load_rates()
    rates["overrides"] = cleaned
    rates.setdefault("cache", {})
    return payments_store.save_rates(rates)
