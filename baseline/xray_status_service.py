from panel_config import INBOUND_TAG, XRAY_STATUS_CMD
from process_utils import run
from sync_utils import run_shell


def current_status(cfg):
    code, xray_state = run_shell(XRAY_STATUS_CMD, timeout=10)
    code2, vps_ip = run(["curl", "-4s", "--max-time", "10", "https://api.ipify.org"], timeout=15)

    inbound = None
    for item in cfg.get("inbounds", []):
        if item.get("tag") == INBOUND_TAG:
            inbound = {
                "listen": item.get("listen"),
                "port": item.get("port"),
                "protocol": item.get("protocol"),
            }
            break

    proxy = "未配置"
    for out in cfg.get("outbounds", []):
        if out.get("tag") == "webshare-out":
            try:
                srv = out["settings"]["servers"][0]
                user = srv.get("users", [{}])[0].get("user", "")
                proxy = f'{srv.get("address")}:{srv.get("port")} / 用户：{user}'
            except Exception:
                proxy = "已配置，但读取失败"

    return {
        "xray": xray_state.strip() if code == 0 else "unknown",
        "vps_ip": vps_ip.strip() if code2 == 0 else "unknown",
        "inbound": inbound or {},
        "proxy": proxy,
    }
