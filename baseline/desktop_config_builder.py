import textwrap

import desktop_catalog
import hy2_env_service
import proxy_bypass


def desktop_auth_users():
    return desktop_catalog.active_auth_users()


def topology():
    try:
        env = hy2_env_service.read_env()
    except RuntimeError:
        env = {}
    network = desktop_catalog.get_network()
    endpoint = proxy_bypass.desktop_endpoint()
    return {
        "transport": "Hysteria2 UDP 443",
        "overlay": "WireGuard",
        "desktop": "Sunshine / Moonlight / RDP / VNC",
        "server": endpoint.get("connect_host") or env.get("HY_DOMAIN", ""),
        "sni": endpoint.get("sni") or env.get("HY_DOMAIN", ""),
        "udp_port": int(env.get("HY_PORT", "443") or 443),
        "wireguard_network": network.get("wg_network", ""),
        "server_wg_ip": network.get("server_wg_ip", ""),
        "tcp_443": "Nginx / Xray / fake-ui",
        "udp_443": "Hysteria2 remote desktop acceleration",
    }


def hysteria_client_config(device):
    network = desktop_catalog.get_network()
    endpoint = proxy_bypass.desktop_endpoint()
    server = endpoint.get("connect_host") or "YOUR_VPS_DOMAIN_OR_IP"
    sni = endpoint.get("sni") or server
    port = int(endpoint.get("port") or 443)
    remote_port = int(device.get("remote_port") or network.get("server_listen_port") or 51820)
    listen_port = int(device.get("listen_port") or 51820)
    user = device.get("hysteria_user", "")
    password = device.get("hysteria_password", "")
    return textwrap.dedent(
        f"""\
        server: {server}:{port}
        auth: {user}:{password}
        tls:
          sni: {sni}
          insecure: false
        fastOpen: true
        udpForwarding:
          - listen: 127.0.0.1:{listen_port}
            remote: 127.0.0.1:{remote_port}
        """
    )


def wireguard_config(device):
    network = desktop_catalog.get_network()
    private_key = device.get("wg_private_key") or "REPLACE_WITH_THIS_DEVICE_PRIVATE_KEY"
    server_public_key = network.get("server_wg_public_key") or "REPLACE_WITH_VPS_WIREGUARD_PUBLIC_KEY"
    listen_port = int(device.get("listen_port") or 51820)
    lines = [
        "[Interface]",
        f"Address = {device.get('wg_cidr') or (str(device.get('wg_ip', '')) + '/32')}",
        f"PrivateKey = {private_key}",
        f"ListenPort = {listen_port}",
        "",
        "[Peer]",
        f"PublicKey = {server_public_key}",
    ]
    if device.get("wg_preshared_key"):
        lines.append(f"PresharedKey = {device.get('wg_preshared_key')}")
    lines += [
        f"AllowedIPs = {network.get('wg_network') or '10.77.0.0/24'}",
        f"Endpoint = 127.0.0.1:{listen_port}",
        "PersistentKeepalive = 25",
        "",
    ]
    return "\n".join(lines)


def server_wireguard_config():
    network = desktop_catalog.get_network()
    private_key = network.get("server_wg_private_key") or "REPLACE_WITH_VPS_WIREGUARD_PRIVATE_KEY"
    lines = [
        "[Interface]",
        f"Address = {network.get('server_wg_cidr')}",
        f"ListenPort = {network.get('server_listen_port')}",
        f"PrivateKey = {private_key}",
        "",
    ]
    for peer in desktop_catalog.list_devices(include_disabled=False):
        public_key = peer.get("wg_public_key") or f"REPLACE_WITH_{str(peer.get('id', 'PEER')).upper().replace('-', '_')}_PUBLIC_KEY"
        lines += [
            "[Peer]",
            f"PublicKey = {public_key}",
        ]
        if peer.get("wg_preshared_key"):
            lines.append(f"PresharedKey = {peer.get('wg_preshared_key')}")
        lines += [
            f"AllowedIPs = {peer.get('wg_cidr') or (str(peer.get('wg_ip', '')) + '/32')}",
            "",
        ]
    return "\n".join(lines)


def usage_notes(device):
    return textwrap.dedent(
        f"""\
        # fake-ui 远程桌面加速客户端

        设备：{device.get('name') or device.get('id')}
        平台：{device.get('platform')}
        传输：Hysteria2 UDP 443
        虚拟内网：WireGuard
        远程桌面端口：{device.get('desktop_protocol')} / {device.get('desktop_port')}

        1. 在 VPS 面板点击“应用远程桌面配置”，让 Hysteria2 识别本设备账号。
        2. 在本机安装 Hysteria2 和 WireGuard。
        3. 先启动 Hysteria2：hysteria-desktop.yaml 会把本机 127.0.0.1:51820 通过 UDP 443 转发到 VPS。
        4. 再导入 wireguard.conf，设备会获得 {device.get('wg_ip')} 这个虚拟内网地址。
        5. 主控端用 Moonlight、RDP、VNC 或 SSH 访问对端 WireGuard IP。

        这个包不绑定任何固定域名或个人机器；服务器地址来自当前 fake-ui VPS 的 Hysteria2 环境配置。
        """
    )
