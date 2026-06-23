import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
BASELINE = ROOT / "baseline"
if str(BASELINE) not in sys.path:
    sys.path.insert(0, str(BASELINE))

from test_core_api import admin_session, app_modules  # noqa: F401


def test_desktop_catalog_normalizes_cross_platform_devices(app_modules):
    desktop_catalog = app_modules["desktop_catalog"]

    controller = desktop_catalog.normalize_device(
        {
            "name": "MacBook 控制端",
            "role": "controller",
            "platform": "macos",
            "wg_ip": "10.77.0.10",
            "listen_port": "51820",
        },
        existing_devices=[],
    )
    host = desktop_catalog.normalize_device(
        {
            "name": "Windows 主机",
            "role": "host",
            "platform": "windows",
            "desktop_protocol": "rdp",
            "wg_ip": "10.77.0.20",
        },
        existing_devices=[controller],
    )

    assert controller["id"] == "macbook"
    assert controller["hysteria_user"] == "desktop-macbook"
    assert ":" not in controller["hysteria_user"]
    assert controller["wg_cidr"] == "10.77.0.10/32"
    assert controller["remote_host"] == "127.0.0.1"
    assert controller["remote_port"] == 51820
    assert controller["platform"] == "macos"
    assert host["id"] == "windows"
    assert host["platform"] == "windows"
    assert host["desktop_protocol"] == "rdp"
    assert host["desktop_port"] == 3389
    assert host["wg_ip"] == "10.77.0.20"


def test_desktop_catalog_rejects_duplicate_wireguard_identity(app_modules):
    desktop_catalog = app_modules["desktop_catalog"]
    first = desktop_catalog.normalize_device({"id": "mac-mini", "wg_ip": "10.77.0.20"}, existing_devices=[])

    with pytest.raises(RuntimeError, match="WireGuard IP is duplicated"):
        desktop_catalog.normalize_device({"id": "linux-box", "wg_ip": "10.77.0.20"}, existing_devices=[first])


def test_hy2_config_includes_remote_desktop_users_without_changing_outbound(app_modules, monkeypatch):
    desktop_catalog = app_modules["desktop_catalog"]
    hy2_config_builder = app_modules["hy2_config_builder"]

    desktop_catalog.upsert_device(
        {
            "id": "mac-mini",
            "role": "host",
            "platform": "macos",
            "wg_ip": "10.77.0.20",
            "hysteria_password": "desktop-secret",
        }
    )

    monkeypatch.setattr(hy2_config_builder, "active_auth_users", lambda: {"alice": "alice-pass"})
    text = hy2_config_builder.build_config("direct")

    assert "    alice: alice-pass" in text
    assert "    desktop-mac-mini: desktop-secret" in text
    assert "type: direct" in text
    assert "listen: :443" in text


def test_desktop_api_admin_flow_and_bundle(app_modules, monkeypatch):
    api = app_modules["api"]
    desktop_runtime = app_modules["desktop_runtime"]

    applied = {}

    def fake_apply():
        applied["called"] = True
        return {"message": "remote desktop applied", "backup": "backup.yaml", "logs": "running"}

    monkeypatch.setattr(desktop_runtime, "apply_hysteria_desktop_users", fake_apply)
    monkeypatch.setattr(
        desktop_runtime,
        "apply_server_wireguard",
        lambda: {"message": "wireguard applied", "interface": "fake-ui-desktop"},
    )

    status, payload = api.handle_post(
        "/api/desktops/save",
        {
            "id": "mac-mini",
            "name": "Mac mini Host",
            "role": "host",
            "platform": "macos",
            "desktop_protocol": "sunshine",
            "wg_ip": "10.77.0.20",
        },
        admin_session(app_modules),
    )
    assert status == 200, payload
    assert payload["device"]["hysteria_user"] == "desktop-mac-mini"
    assert payload["devices"][0]["connection_target"] == "10.77.0.20"

    status, payload = api.handle_post("/api/desktops/apply", {}, admin_session(app_modules))
    assert status == 200, payload
    assert applied["called"] is True
    assert payload["result"]["message"] == "remote desktop applied"

    status, bundle = api.handle_get("/api/desktops/mac-mini/bundle", admin_session(app_modules))
    assert status == 200
    assert bundle["filename"] == "mac-mini-remote-desktop-agent.zip"
    assert bundle["content_type"] == "application/zip"
    assert isinstance(bundle["content"], bytes)

    status, config = api.handle_get("/api/desktops/mac-mini/wireguard-config", admin_session(app_modules))
    assert status == 200
    assert config["filename"] == "mac-mini-wireguard.conf"
    assert "Address = 10.77.0.20/32" in config["content"]

    status, server_config = api.handle_get("/api/desktops/server-wireguard-config", admin_session(app_modules))
    assert status == 200
    assert server_config["filename"] == "fake-ui-vps-wireguard.conf"
    assert "Address = 10.77.0.1/24" in server_config["content"]

    status, payload = api.handle_post("/api/desktops/apply-wireguard", {}, admin_session(app_modules))
    assert status == 200
    assert payload["result"]["message"] == "wireguard applied"

    status, payload = api.handle_post(
        "/api/desktops/network",
        {"wg_network": "10.99.0.0/24", "server_wg_ip": "10.99.0.1", "server_wg_public_key": "pub"},
        admin_session(app_modules),
    )
    assert status == 200
    assert payload["network"]["wg_network"] == "10.99.0.0/24"


def test_desktop_wireguard_config_uses_generic_vps_hub(app_modules):
    desktop_catalog = app_modules["desktop_catalog"]
    desktop_config_builder = app_modules["desktop_config_builder"]

    desktop_catalog.update_network(
        {
            "wg_network": "10.88.0.0/24",
            "server_wg_ip": "10.88.0.1",
            "server_wg_private_key": "server-private",
            "server_wg_public_key": "server-public",
            "server_listen_port": "51820",
        }
    )
    device = desktop_catalog.upsert_device(
        {
            "id": "windows-host",
            "platform": "windows",
            "desktop_protocol": "rdp",
            "wg_ip": "10.88.0.20",
            "wg_public_key": "client-public",
            "wg_preshared_key": "shared-secret",
        }
    )

    client_config = desktop_config_builder.wireguard_config(device)
    assert "PublicKey = server-public" in client_config
    assert "PresharedKey = shared-secret" in client_config
    assert "AllowedIPs = 10.88.0.0/24" in client_config
    assert "Endpoint = 127.0.0.1:51820" in client_config

    server_config = desktop_config_builder.server_wireguard_config()
    assert "PrivateKey = server-private" in server_config
    assert "Address = 10.88.0.1/24" in server_config
    assert "PublicKey = client-public" in server_config
    assert "AllowedIPs = 10.88.0.20/32" in server_config


def test_desktop_hysteria_config_separates_connect_host_sni_and_proxy_rules(app_modules, monkeypatch):
    desktop_catalog = app_modules["desktop_catalog"]
    desktop_config_builder = app_modules["desktop_config_builder"]
    proxy_bypass = app_modules["proxy_bypass"]

    monkeypatch.setenv("HY2_CONNECT_HOST", "203.0.113.10")
    monkeypatch.setenv("HY2_SNI", "hy.example.com")
    device = desktop_catalog.upsert_device(
        {
            "id": "windows-host",
            "platform": "windows",
            "desktop_protocol": "rdp",
            "wg_ip": "10.77.0.20",
            "hysteria_password": "desktop-secret",
        }
    )

    config = desktop_config_builder.hysteria_client_config(device)
    guide = proxy_bypass.desktop_proxy_bypass()

    assert "server: 203.0.113.10:443" in config
    assert "sni: hy.example.com" in config
    assert guide["connect_host"] == "203.0.113.10"
    assert guide["sni"] == "hy.example.com"
    assert guide["transport"] == "hysteria2_udp_443"
    assert "Shadowrocket" in guide["templates"]
    assert "DOMAIN,hy.example.com,DIRECT" in guide["templates"]["Shadowrocket"]
    assert "IP-CIDR,203.0.113.10/32,DIRECT,no-resolve" in guide["templates"]["Shadowrocket"]
    assert "Clash / Mihomo" in guide["templates"]
    assert "PROCESS-NAME,hysteria,DIRECT" in guide["templates"]["Clash / Mihomo"]


def test_desktop_api_forbids_user_session(app_modules):
    api = app_modules["api"]
    user_session = {"u": "viewer", "r": "user", "role": "user"}

    status, payload = api.handle_get("/api/desktops", user_session)

    assert status == 403
    assert payload["ok"] is False


def test_admin_dashboard_includes_remote_desktop_devices(app_modules, monkeypatch):
    api = app_modules["api"]
    desktop_catalog = app_modules["desktop_catalog"]
    monkeypatch.setattr(app_modules["dashboard_service"].xray_panel, "current_status", lambda: {"proxy": ""})
    monkeypatch.setattr(app_modules["dashboard_service"].hy2_panel, "hy2_status", lambda: {})

    desktop_catalog.upsert_device({"id": "linux-host", "platform": "linux", "wg_ip": "10.77.0.30"})

    status, payload = api.handle_get("/api/dashboard", admin_session(app_modules))

    assert status == 200
    assert payload["data"]["desktops"][0]["id"] == "linux-host"
    assert payload["data"]["desktop_topology"]["transport"] == "Hysteria2 UDP 443"
