import urllib.parse

import hy2_config_builder
import hy2_env_service
import hy2_runtime
import hy2_status_service
import link_settings
import node_catalog
from process_utils import run
from proxy_utils import normalize_proxy_type, proxy_auth_enabled, test_proxy


read_link_settings = link_settings.read
hy2_read_env = hy2_env_service.read_env
hy2_get_traffic_secret = hy2_env_service.traffic_secret
hy2_active_auth_users = hy2_config_builder.active_auth_users
hy2_backup_config = hy2_runtime.backup_config
hy2_build_config = hy2_config_builder.build_config
hy2_restart_with_rollback = hy2_runtime.restart_with_rollback
hy2_status = hy2_status_service.status
hy2_outbound_mode = hy2_status_service.outbound_mode
hy2_proxy_endpoint = hy2_status_service.proxy_endpoint


def hy2_apply_proxy(addr, port, user, password, proxy_type="http"):
    proxy_type = normalize_proxy_type(proxy_type)
    proxy_ip = test_proxy(addr.strip(), int(port), user.strip(), password, proxy_type)
    new_config = hy2_build_config("http", addr, port, user, password, proxy_type)
    backup, logs = hy2_restart_with_rollback(new_config)
    return {"message": f"Hysteria2 {proxy_type.upper()} 代理已启用。", "proxy_test_ip": proxy_ip, "backup": str(backup), "logs": logs}


def hy2_disable_proxy():
    new_config = hy2_build_config("direct")
    backup, logs = hy2_restart_with_rollback(new_config)
    return {"message": "Hysteria2 HTTP 代理已关闭，恢复 VPS 出口。", "backup": str(backup), "logs": logs}


def build_hy2_link():
    settings = read_link_settings()
    env = hy2_read_env()
    domain = env["HY_DOMAIN"]
    port = env.get("HY_PORT", "443")
    password = env.get("HY_PASSWORD") or env.get("HY_ADMIN_PASSWORD")

    if not password:
        raise RuntimeError("未找到 HY_PASSWORD / HY_ADMIN_PASSWORD，无法生成 Hysteria2 链接。")

    user = urllib.parse.quote("admin", safe="")
    auth = urllib.parse.quote(password, safe="")
    name = urllib.parse.quote(node_catalog.display_name("hy2", str(settings.get("hy2_name", "HY2_clean_" + domain))))
    return f"hy2://{user}:{auth}@{domain}:{port}/?sni={domain}#{name}"
