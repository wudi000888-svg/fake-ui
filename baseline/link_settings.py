from json_store import load_json
from panel_config import DEFAULT_HY2_NAME, DEFAULT_VLESS_ADDRESS, DEFAULT_VLESS_NAME, LINK_SETTINGS_FILE


def defaults():
    return {
        "vless_address": DEFAULT_VLESS_ADDRESS,
        "vless_port": 443,
        "vless_name": DEFAULT_VLESS_NAME,
        "hy2_name": DEFAULT_HY2_NAME,
    }


def read():
    data = defaults()
    data.update(load_json(LINK_SETTINGS_FILE, {}))
    return data
