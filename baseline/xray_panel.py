import urllib.parse

import link_settings
import xray_config_builder
import xray_runtime
import xray_status_service
from panel_config import XRAY_BIN
from process_utils import run
from proxy_utils import normalize_proxy_type, proxy_auth_enabled, test_proxy


load_config = xray_runtime.load_config
backup_xray_config = xray_runtime.backup_xray_config
write_and_restart_xray = xray_runtime.write_and_restart_xray
ensure_xray_inbound = xray_config_builder.ensure_xray_inbound


def apply_proxy(addr, port, user, password, proxy_type="http"):
    addr = addr.strip()
    user = user.strip()
    password = password.strip()
    port_int = int(port)
    proxy_type = normalize_proxy_type(proxy_type)
    proxy_ip = test_proxy(addr, port_int, user, password, proxy_type)
    cfg = xray_config_builder.build_proxy_config(load_config(), addr, port_int, user, password, proxy_type)
    backup = write_and_restart_xray(cfg)
    return {"message": f"Reality {proxy_type.upper()} proxy enabled.", "proxy_test_ip": proxy_ip, "backup": str(backup)}


def disable_proxy():
    cfg = xray_config_builder.build_direct_config(load_config())
    backup = write_and_restart_xray(cfg)
    return {"message": "Reality HTTP 代理已关闭，恢复 VPS 出口。", "backup": str(backup)}


def current_status():
    return xray_status_service.current_status(load_config())


def read_link_settings():
    return link_settings.read()


def reality_public_key_from_private(private_key):
    code, out = run([XRAY_BIN, "x25519", "-i", private_key], timeout=20)
    if code != 0:
        raise RuntimeError("无法计算 Reality PublicKey：\n" + out)
    for line in out.splitlines():
        if "public" in line.lower() and ":" in line:
            value = line.split(":", 1)[1].strip()
            if value:
                return value
    raise RuntimeError("xray x25519 输出中没有找到 PublicKey：\n" + out)


def build_vless_link():
    settings = read_link_settings()
    cfg = load_config()
    inbound = ensure_xray_inbound(cfg)

    clients = inbound.get("settings", {}).get("clients", [])
    if not clients:
        raise RuntimeError("未找到 VLESS client UUID")
    client = clients[0]

    uuid = client.get("id", "")
    flow = client.get("flow", "")

    reality = inbound.get("streamSettings", {}).get("realitySettings", {})
    sni = (reality.get("serverNames") or [""])[0]
    sid = (reality.get("shortIds") or [""])[0]
    private_key = reality.get("privateKey", "")

    if not uuid or not sni or not private_key:
        raise RuntimeError("VLESS Reality 参数不完整。")

    pbk = reality_public_key_from_private(private_key)
    params = {
        "encryption": "none",
        "security": "reality",
        "sni": sni,
        "fp": "chrome",
        "pbk": pbk,
        "type": "tcp",
        "headerType": "none",
    }
    if flow:
        params["flow"] = flow
    if sid:
        params["sid"] = sid

    address = str(settings["vless_address"])
    port = str(settings["vless_port"])
    name = urllib.parse.quote(str(settings["vless_name"]))
    query = urllib.parse.urlencode(params, safe="-_.~")
    return f"vless://{uuid}@{address}:{port}?{query}#{name}"
