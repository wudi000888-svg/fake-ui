import desktop_catalog
import hy2_config_builder
import hy2_runtime
import desktop_config_builder
import tunnel_nginx


SERVER_WG_CONF = "/etc/wireguard/fake-ui-desktop.conf"
SERVER_WG_INTERFACE = "fake-ui-desktop"


def apply_hysteria_desktop_users():
    text = hy2_config_builder.build_config("direct")
    backup, logs = hy2_runtime.restart_with_rollback(text)
    return {
        "message": "远程桌面 Hysteria2 账号已应用",
        "backup": str(backup),
        "logs": logs,
        "devices": desktop_catalog.list_devices(),
    }


def apply_server_wireguard():
    text = desktop_config_builder.server_wireguard_config()
    if "REPLACE_WITH_" in text:
        raise RuntimeError("请先填写 VPS WireGuard 私钥和设备公钥，再应用 VPS WireGuard。")
    tunnel_nginx.write_text(SERVER_WG_CONF, text)
    tunnel_nginx.run_checked(["sh", "-c", "wg-quick down fake-ui-desktop >/dev/null 2>&1 || true"], timeout=30)
    out = tunnel_nginx.run_checked(["wg-quick", "up", "fake-ui-desktop"], timeout=60)
    return {"message": "VPS WireGuard 已应用", "interface": SERVER_WG_INTERFACE, "config": SERVER_WG_CONF, "logs": out}
