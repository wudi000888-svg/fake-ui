import json
import importlib.util
import socket
import subprocess
import sys
import tarfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "baseline"
if str(BASELINE) not in sys.path:
    sys.path.insert(0, str(BASELINE))


def sample_public_tunnel(**overrides):
    tunnel = {
        "id": "office-api",
        "kind": "public_https",
        "name": "Office API",
        "public_domain": "api.example.com",
        "portal_port": 18082,
        "target_host": "127.0.0.1",
        "target_port": 5000,
        "client_id": "11111111-1111-4111-8111-111111111111",
        "flow": "xtls-rprx-vision",
        "bridge_mode": "dedicated",
        "bridge_id": "office-api",
        "bridge_platform": "linux",
    }
    tunnel.update(overrides)
    return tunnel


def sample_reality_profile():
    return {
        "server_name": "www.cloudflare.com",
        "address": "vless.example.com",
        "port": 443,
        "public_key": "server-public-key",
        "short_id": "0123456789abcdef",
    }


def read_tar_texts(content):
    with tarfile.open(fileobj=BytesIO(content), mode="r:gz") as tar:
        texts = {}
        for member in tar.getmembers():
            if member.isfile():
                texts[member.name] = tar.extractfile(member).read().decode("utf-8")
    return texts


def fake_pairing(token="raw-pairing-token"):
    return {
        "pairing_token": token,
        "record": {
            "token_id": "pair_test_token",
            "bridge_id": "office-api",
            "bundle_kind": "dedicated",
            "platform": "linux",
            "agent_id": "agent_test",
            "capabilities": ["bootstrap", "local_status"],
        },
    }


def test_normalize_tunnel_auto_allocates_public_domain_fields():
    import tunnel_catalog

    existing = [
        {
            "id": "old-service",
            "portal_port": 18081,
            "client_id": "11111111-1111-4111-8111-111111111111",
            "public_domain": "old.example.com",
        }
    ]
    data = {
        "public_domain": "New.Example.COM ",
        "name": "New service",
        "target_port": "3000",
    }

    item = tunnel_catalog.normalize_tunnel(data, existing_tunnels=existing)

    assert item["id"] == "new-example-com"
    assert item["public_domain"] == "new.example.com"
    assert item["portal_port"] == 18082
    assert item["target_host"] == "127.0.0.1"
    assert item["target_port"] == 3000
    assert item["server_address"] == "new.example.com"
    assert item["server_port"] == 443
    assert item["reality_sni"] == "www.cloudflare.com"
    assert item["email"] == "tunnel:new-example-com"
    assert item["portal_tag"] == "tunnel-portal-new-example-com"
    assert item["reverse_tag"] == "tunnel-reverse-new-example-com"
    assert item["bridge_mode"] == "dedicated"
    assert item["bridge_id"] == "new-example-com"
    assert item["bridge_platform"] == "macos"


def test_normalize_tunnel_accepts_shared_bridge_agent_metadata():
    import tunnel_catalog

    item = tunnel_catalog.normalize_tunnel(
        {
            "public_domain": "api.example.com",
            "name": "Shared API",
            "target_port": "3000",
            "bridge_mode": "shared",
            "bridge_id": "office-linux",
            "bridge_platform": "linux",
        },
        existing_tunnels=[],
    )

    assert item["bridge_mode"] == "shared"
    assert item["bridge_id"] == "office-linux"
    assert item["bridge_platform"] == "linux"


def test_normalize_tunnel_rejects_unknown_bridge_mode_and_platform():
    import tunnel_catalog

    with pytest.raises(RuntimeError, match="bridge mode"):
        tunnel_catalog.normalize_tunnel(
            {
                "public_domain": "api.example.com",
                "target_port": "3000",
                "bridge_mode": "clustered",
            },
            existing_tunnels=[],
        )

    with pytest.raises(RuntimeError, match="bridge platform"):
        tunnel_catalog.normalize_tunnel(
            {
                "public_domain": "web.example.com",
                "target_port": "3000",
                "bridge_platform": "freebsd",
            },
            existing_tunnels=[],
        )


def test_normalize_tunnel_rejects_duplicate_uuid_and_portal_port():
    import tunnel_catalog

    existing = [
        {
            "id": "old",
            "portal_port": 18081,
            "client_id": "11111111-1111-4111-8111-111111111111",
            "public_domain": "old.example.com",
        }
    ]

    with pytest.raises(RuntimeError, match="portal"):
        tunnel_catalog.normalize_tunnel(
            {"public_domain": "a.example.com", "target_port": "3000", "portal_port": "18081"},
            existing_tunnels=existing,
        )

    with pytest.raises(RuntimeError, match="UUID"):
        tunnel_catalog.normalize_tunnel(
            {
                "public_domain": "b.example.com",
                "target_port": "3001",
                "client_id": "11111111-1111-4111-8111-111111111111",
            },
            existing_tunnels=existing,
        )


def test_normalize_private_tcp_tunnel_does_not_require_public_domain():
    import tunnel_catalog

    item = tunnel_catalog.normalize_tunnel(
        {
            "kind": "private_tcp",
            "id": "macbook-ssh",
            "name": "MacBook SSH",
            "target_host": "127.0.0.1",
            "target_port": "22",
            "server_address": "vless.example.com",
        },
        existing_tunnels=[],
    )

    assert item["kind"] == "private_tcp"
    assert item["id"] == "macbook-ssh"
    assert item["public_domain"] == ""
    assert item["portal_port"] == 18081
    assert item["server_address"] == "vless.example.com"
    assert item["target_port"] == 22
    assert item["email"] == "tunnel:macbook-ssh"


def test_nginx_config_builder_creates_generic_domain_https_and_acme_blocks():
    import tunnel_nginx

    tunnel = {
        "id": "new-example-com",
        "public_domain": "new.example.com",
        "portal_port": 18082,
    }

    http_conf = tunnel_nginx.render_http_server(tunnel, "/opt/fake-ui/data/acme")
    https_conf = tunnel_nginx.render_https_server(tunnel, "/etc/letsencrypt/live")

    assert "server_name new.example.com;" in http_conf
    assert "root /opt/fake-ui/data/acme;" in http_conf
    assert "proxy_pass http://127.0.0.1:18082;" in http_conf
    assert "listen 127.0.0.1:10000 ssl http2;" in https_conf
    assert "/etc/letsencrypt/live/new.example.com/fullchain.pem" in https_conf
    assert "proxy_set_header X-Forwarded-Proto https;" in https_conf
    assert "hardcoded.example" not in http_conf + https_conf


def test_nginx_config_skips_private_tcp_tunnels_without_domains():
    import tunnel_nginx

    conf = tunnel_nginx.combined_config(
        [
            {"id": "macbook-ssh", "kind": "private_tcp", "portal_port": 18083, "target_port": 22},
            {"id": "web", "public_domain": "web.example.com", "portal_port": 18084},
        ]
    )

    assert "server_name web.example.com;" in conf
    assert "18084" in conf
    assert "macbook-ssh" not in conf
    assert "18083" not in conf


def test_apply_native_nginx_disables_legacy_single_tunnel_confs(tmp_path, monkeypatch):
    import tunnel_nginx

    conf_dir = tmp_path / "nginx" / "conf.d"
    conf_dir.mkdir(parents=True)
    managed = conf_dir / "fake-ui-tunnels.conf"
    legacy = conf_dir / "fake-ui-tunnel-old.conf"
    legacy.write_text(
        """
server {
    listen 127.0.0.1:10000 ssl http2;
    server_name mac.example.com;
    location / { proxy_pass http://127.0.0.1:18081; }
}
""".strip(),
        encoding="utf-8",
    )
    (conf_dir / "other.conf").write_text("server {}", encoding="utf-8")
    monkeypatch.setattr(tunnel_nginx, "run_checked", lambda *args, **kwargs: "")
    monkeypatch.setattr(tunnel_nginx, "cert_exists", lambda *args, **kwargs: True)

    result = tunnel_nginx.apply_native_nginx(
        [
            {
                "id": "mac",
                "enabled": True,
                "public_domain": "mac.example.com",
                "portal_port": 18084,
            }
        ],
        conf_path=managed,
        acme_root=tmp_path / "acme",
        letsencrypt_live=tmp_path / "live",
    )

    assert result["legacy_disabled"] == [str(legacy.with_suffix(".conf.disabled"))]
    assert not legacy.exists()
    assert legacy.with_suffix(".conf.disabled").exists()
    assert managed.exists()
    assert "proxy_pass http://127.0.0.1:18084;" in managed.read_text(encoding="utf-8")


def test_nginx_host_command_uses_docker_nsenter_when_enabled(monkeypatch):
    import tunnel_nginx

    monkeypatch.setenv("FAKE_UI_HOST_COMMAND_MODE", "docker-nsenter")
    monkeypatch.setenv("FAKE_UI_HOST_HELPER_IMAGE", "xray-proxy-panel:local")

    cmd = tunnel_nginx.host_command(["nginx", "-t"])

    assert cmd[:6] == ["docker", "run", "--rm", "--privileged", "--pid=host", "--network=host"]
    assert "nsenter" in cmd
    assert cmd[-2:] == ["nginx", "-t"]


def test_bridge_bundle_contains_macos_launchd_scripts_and_config():
    import tunnel_bridge_bundle
    import tunnel_config_builder

    tunnel = {
        "id": "new-example-com",
        "name": "New service",
        "public_domain": "new.example.com",
        "portal_port": 18082,
        "target_host": "127.0.0.1",
        "target_port": 3000,
        "client_id": "11111111-1111-4111-8111-111111111111",
        "flow": "xtls-rprx-vision",
    }
    profile = {
        "server_name": "www.cloudflare.com",
        "address": "new.example.com",
        "port": 443,
        "public_key": "server-public-key",
        "short_id": "0123456789abcdef",
    }
    bridge_cfg = tunnel_config_builder.build_bridge_config(tunnel, profile)

    content = tunnel_bridge_bundle.build_macos_bundle(tunnel, bridge_cfg)

    with tarfile.open(fileobj=BytesIO(content), mode="r:gz") as tar:
        names = set(tar.getnames())
        assert "new-example-com/xray-bridge.json" in names
        assert "new-example-com/install-macos.sh" in names
        assert "new-example-com/uninstall-macos.sh" in names
        assert "new-example-com/status-macos.sh" in names
        assert "new-example-com/com.fakeui.tunnel.new-example-com.plist" in names
        install = tar.extractfile("new-example-com/install-macos.sh").read().decode("utf-8")
        status = tar.extractfile("new-example-com/status-macos.sh").read().decode("utf-8")
        cfg = json.loads(tar.extractfile("new-example-com/xray-bridge.json").read().decode("utf-8"))

    assert "launchctl bootstrap" in install
    assert "com.fakeui.tunnel.new-example-com" in install
    assert "run -test -c" in install
    assert "curl -fsS http://127.0.0.1:3000/" in status
    assert "https://new.example.com/" in status
    reverse = next(item for item in cfg["outbounds"] if item["tag"] == "tunnel-reverse-out")
    assert reverse["settings"]["address"] == "new.example.com"


def test_private_tcp_bridge_bundle_status_omits_public_https_check():
    import tunnel_bridge_bundle
    import tunnel_config_builder

    tunnel = {
        "id": "macbook-ssh",
        "kind": "private_tcp",
        "name": "MacBook SSH",
        "portal_port": 18083,
        "target_host": "127.0.0.1",
        "target_port": 22,
        "client_id": "11111111-1111-4111-8111-111111111111",
        "flow": "xtls-rprx-vision",
    }
    profile = {
        "server_name": "www.cloudflare.com",
        "address": "vless.example.com",
        "port": 443,
        "public_key": "server-public-key",
        "short_id": "0123456789abcdef",
    }
    bridge_cfg = tunnel_config_builder.build_bridge_config(tunnel, profile)

    content = tunnel_bridge_bundle.build_macos_bundle(tunnel, bridge_cfg)

    with tarfile.open(fileobj=BytesIO(content), mode="r:gz") as tar:
        status = tar.extractfile("macbook-ssh/status-macos.sh").read().decode("utf-8")
        readme = tar.extractfile("macbook-ssh/README.md").read().decode("utf-8")

    assert "curl -fsS http://127.0.0.1:22/" not in status
    assert "public https" not in status
    assert "ssh -J" in readme


def test_dedicated_bridge_bundle_contains_linux_and_windows_installers():
    import tunnel_bridge_bundle
    import tunnel_config_builder

    tunnel = {
        "id": "office-api",
        "kind": "public_https",
        "name": "Office API",
        "public_domain": "api.example.com",
        "portal_port": 18082,
        "target_host": "127.0.0.1",
        "target_port": 5000,
        "client_id": "11111111-1111-4111-8111-111111111111",
        "flow": "xtls-rprx-vision",
    }
    profile = {
        "server_name": "www.cloudflare.com",
        "address": "vless.example.com",
        "port": 443,
        "public_key": "server-public-key",
        "short_id": "0123456789abcdef",
    }
    bridge_cfg = tunnel_config_builder.build_bridge_config(tunnel, profile)

    linux_content = tunnel_bridge_bundle.build_bundle(tunnel, bridge_cfg, "linux")
    windows_content = tunnel_bridge_bundle.build_bundle(tunnel, bridge_cfg, "windows")

    with tarfile.open(fileobj=BytesIO(linux_content), mode="r:gz") as tar:
        names = set(tar.getnames())
        assert "office-api-linux-bridge/xray-bridge.json" in names
        assert "office-api-linux-bridge/install-linux.sh" in names
        assert "office-api-linux-bridge/uninstall-linux.sh" in names
        install = tar.extractfile("office-api-linux-bridge/install-linux.sh").read().decode("utf-8")
        status = tar.extractfile("office-api-linux-bridge/status-linux.sh").read().decode("utf-8")

    assert "fake-ui-tunnel-office-api" in install
    assert "run -test -c" in install
    assert "curl -fsS http://127.0.0.1:5000/" in status

    with tarfile.open(fileobj=BytesIO(windows_content), mode="r:gz") as tar:
        names = set(tar.getnames())
        assert "office-api-windows-bridge/install-windows.ps1" in names
        install = tar.extractfile("office-api-windows-bridge/install-windows.ps1").read().decode("utf-8")

    assert "FakeUITunnel-office-api" in install
    assert "run -test -c" in install


def test_dedicated_bridge_bundle_includes_local_dashboard_assets():
    import tunnel_bridge_bundle
    import tunnel_config_builder

    tunnel = {
        "id": "office-api",
        "kind": "public_https",
        "name": "Office API",
        "public_domain": "api.example.com",
        "portal_port": 18082,
        "target_host": "127.0.0.1",
        "target_port": 5000,
        "client_id": "11111111-1111-4111-8111-111111111111",
        "flow": "xtls-rprx-vision",
    }
    profile = {
        "server_name": "www.cloudflare.com",
        "address": "vless.example.com",
        "port": 443,
        "public_key": "server-public-key",
        "short_id": "0123456789abcdef",
    }
    bridge_cfg = tunnel_config_builder.build_bridge_config(tunnel, profile)

    bundles = {
        "macos": ("office-api", tunnel_bridge_bundle.build_bundle(tunnel, bridge_cfg, "macos"), "open-dashboard.sh"),
        "linux": ("office-api-linux-bridge", tunnel_bridge_bundle.build_bundle(tunnel, bridge_cfg, "linux"), "open-dashboard.sh"),
        "windows": ("office-api-windows-bridge", tunnel_bridge_bundle.build_bundle(tunnel, bridge_cfg, "windows"), "open-dashboard.ps1"),
    }

    for platform, (root, content, open_script) in bundles.items():
        with tarfile.open(fileobj=BytesIO(content), mode="r:gz") as tar:
            names = set(tar.getnames())
            assert f"{root}/bridge-dashboard.py" in names
            assert f"{root}/bridge-dashboard.json" in names
            assert f"{root}/{open_script}" in names
            metadata = json.loads(tar.extractfile(f"{root}/bridge-dashboard.json").read().decode("utf-8"))
            dashboard = tar.extractfile(f"{root}/bridge-dashboard.py").read().decode("utf-8")
            readme = tar.extractfile(f"{root}/README.md").read().decode("utf-8")

        assert metadata["bundle_kind"] == "dedicated"
        assert metadata["platform"] == platform
        assert metadata["dashboard"]["host"] == "127.0.0.1"
        assert metadata["dashboard"]["port"] == 19090
        assert metadata["runtime"]["restart_command"]
        assert metadata["logs"]
        assert metadata["services"][0]["id"] == "office-api"
        assert metadata["services"][0]["public_url"] == "https://api.example.com/"
        assert metadata["services"][0]["local"] == "127.0.0.1:5000"
        assert "DEFAULT_HOST = \"127.0.0.1\"" in dashboard
        assert "http://127.0.0.1:19090/" in readme
        assert "0.0.0.0" not in dashboard
        platform_title = {"macos": "macOS", "linux": "Linux", "windows": "Windows"}[platform]
        assert f"fake-ui {platform_title} Bridge" in readme
        if platform == "windows":
            assert "install-windows.ps1" in readme
            assert "open-dashboard.ps1" in readme
            assert "bash open-dashboard.sh" not in readme
        else:
            assert f"install-{platform}.sh" in readme
            assert "open-dashboard.sh" in readme


def test_shared_bridge_agent_bundle_contains_linux_and_windows_installers():
    import tunnel_bridge_bundle
    import tunnel_config_builder

    tunnels = [
        {
            "id": "web",
            "kind": "public_https",
            "name": "Web",
            "public_domain": "web.example.com",
            "portal_port": 18082,
            "target_host": "127.0.0.1",
            "target_port": 3000,
            "client_id": "11111111-1111-4111-8111-111111111111",
            "flow": "xtls-rprx-vision",
            "bridge_mode": "shared",
            "bridge_id": "office-linux",
            "bridge_platform": "linux",
        },
        {
            "id": "api",
            "kind": "public_https",
            "name": "API",
            "public_domain": "api.example.com",
            "portal_port": 18083,
            "target_host": "127.0.0.1",
            "target_port": 5000,
            "client_id": "33333333-3333-4333-8333-333333333333",
            "flow": "xtls-rprx-vision",
            "bridge_mode": "shared",
            "bridge_id": "office-linux",
            "bridge_platform": "linux",
        },
    ]
    profile = {
        "server_name": "www.cloudflare.com",
        "address": "vless.example.com",
        "port": 443,
        "public_key": "server-public-key",
        "short_id": "0123456789abcdef",
    }
    bridge_cfg = tunnel_config_builder.build_shared_bridge_config(tunnels, profile)

    linux_content = tunnel_bridge_bundle.build_agent_bundle("office-linux", tunnels, bridge_cfg, "linux")
    windows_content = tunnel_bridge_bundle.build_agent_bundle("office-linux", tunnels, bridge_cfg, "windows")

    with tarfile.open(fileobj=BytesIO(linux_content), mode="r:gz") as tar:
        names = set(tar.getnames())
        root = "office-linux-linux-bridge"
        assert f"{root}/xray-bridge.json" in names
        assert f"{root}/install-linux.sh" in names
        assert f"{root}/uninstall-linux.sh" in names
        install = tar.extractfile(f"{root}/install-linux.sh").read().decode("utf-8")
        status = tar.extractfile(f"{root}/status-linux.sh").read().decode("utf-8")
        cfg = json.loads(tar.extractfile(f"{root}/xray-bridge.json").read().decode("utf-8"))

    assert "systemctl" in install
    assert "fake-ui-bridge-office-linux" in install
    assert "run -test -c" in install
    assert "curl -fsS http://127.0.0.1:3000/" in status
    assert "curl -fsS http://127.0.0.1:5000/" in status
    assert "tunnel-reverse-out-web" in [item["tag"] for item in cfg["outbounds"]]
    assert "tunnel-reverse-out-api" in [item["tag"] for item in cfg["outbounds"]]

    with tarfile.open(fileobj=BytesIO(windows_content), mode="r:gz") as tar:
        names = set(tar.getnames())
        root = "office-linux-windows-bridge"
        assert f"{root}/install-windows.ps1" in names
        install = tar.extractfile(f"{root}/install-windows.ps1").read().decode("utf-8")
        readme = tar.extractfile(f"{root}/README.md").read().decode("utf-8")

    assert "Register-ScheduledTask" in install
    assert "FakeUIBridge-office-linux" in install
    assert "run -test -c" in install
    assert "PowerShell" in readme
    assert "open-dashboard.ps1" in readme
    assert "bash open-dashboard.sh" not in readme


def test_shared_bridge_agent_bundle_dashboard_lists_all_services():
    import tunnel_bridge_bundle
    import tunnel_config_builder

    tunnels = [
        {
            "id": "web",
            "kind": "public_https",
            "name": "Web",
            "public_domain": "web.example.com",
            "portal_port": 18082,
            "target_host": "127.0.0.1",
            "target_port": 3000,
            "client_id": "11111111-1111-4111-8111-111111111111",
            "flow": "xtls-rprx-vision",
            "bridge_mode": "shared",
            "bridge_id": "office-linux",
            "bridge_platform": "linux",
        },
        {
            "id": "api",
            "kind": "public_https",
            "name": "API",
            "public_domain": "api.example.com",
            "portal_port": 18083,
            "target_host": "127.0.0.1",
            "target_port": 5000,
            "client_id": "33333333-3333-4333-8333-333333333333",
            "flow": "xtls-rprx-vision",
            "bridge_mode": "shared",
            "bridge_id": "office-linux",
            "bridge_platform": "linux",
        },
    ]
    profile = {
        "server_name": "www.cloudflare.com",
        "address": "vless.example.com",
        "port": 443,
        "public_key": "server-public-key",
        "short_id": "0123456789abcdef",
    }
    bridge_cfg = tunnel_config_builder.build_shared_bridge_config(tunnels, profile)

    content = tunnel_bridge_bundle.build_agent_bundle("office-linux", tunnels, bridge_cfg, "macos")

    with tarfile.open(fileobj=BytesIO(content), mode="r:gz") as tar:
        root = "office-linux-macos-bridge"
        names = set(tar.getnames())
        assert f"{root}/bridge-dashboard.py" in names
        assert f"{root}/bridge-dashboard.json" in names
        assert f"{root}/open-dashboard.sh" in names
        metadata = json.loads(tar.extractfile(f"{root}/bridge-dashboard.json").read().decode("utf-8"))
        dashboard = tar.extractfile(f"{root}/bridge-dashboard.py").read().decode("utf-8")

    assert metadata["bundle_kind"] == "shared"
    assert metadata["bridge_id"] == "office-linux"
    assert metadata["dashboard"] == {"host": "127.0.0.1", "port": 19090}
    assert metadata["runtime"]["restart_command"] == 'launchctl kickstart -k "gui/$(id -u)/com.fakeui.bridge.office-linux"'
    assert metadata["logs"] == [
        "~/.fake-ui/bridges/office-linux/bridge.out.log",
        "~/.fake-ui/bridges/office-linux/bridge.err.log",
        "bridge-dashboard.out.log",
        "bridge-dashboard.err.log",
    ]
    assert [service["id"] for service in metadata["services"]] == ["web", "api"]
    assert metadata["services"][0]["public_url"] == "https://web.example.com/"
    assert metadata["services"][1]["local"] == "127.0.0.1:5000"
    assert "def render_dashboard" in dashboard
    assert "GET /status.json" in dashboard


def test_static_bundles_do_not_include_agent_pairing_bootstrap_assets():
    import tunnel_bridge_bundle
    import tunnel_config_builder

    tunnel = sample_public_tunnel()
    bridge_cfg = tunnel_config_builder.build_bridge_config(tunnel, sample_reality_profile())

    dedicated_texts = read_tar_texts(tunnel_bridge_bundle.build_bundle(tunnel, bridge_cfg, "linux"))
    shared_texts = read_tar_texts(
        tunnel_bridge_bundle.build_agent_bundle(
            "office-linux",
            [sample_public_tunnel(bridge_mode="shared", bridge_id="office-linux")],
            tunnel_config_builder.build_shared_bridge_config(
                [sample_public_tunnel(bridge_mode="shared", bridge_id="office-linux")],
                sample_reality_profile(),
            ),
            "linux",
        )
    )

    assert not any(name.endswith("/agent-profile.json") for name in dedicated_texts)
    assert not any(name.endswith("/bootstrap-agent.py") for name in dedicated_texts)
    assert not any(name.endswith("/agent-profile.json") for name in shared_texts)
    assert not any(name.endswith("/bootstrap-agent.py") for name in shared_texts)
    assert "agent-profile.json" in dedicated_texts["office-api-linux-bridge/install-linux.sh"]
    assert "bootstrap-agent.py" in dedicated_texts["office-api-linux-bridge/install-linux.sh"]
    assert "agent-profile.json" in shared_texts["office-linux-linux-bridge/install-linux.sh"]
    assert "bootstrap-agent.py" in shared_texts["office-linux-linux-bridge/install-linux.sh"]


def test_paired_dedicated_agent_bundle_contains_profile_bootstrap_and_no_extra_raw_token():
    import tunnel_bridge_bundle

    tunnel = sample_public_tunnel()
    pairing = fake_pairing("secret-token-dedicated")

    content = tunnel_bridge_bundle.build_paired_bundle(
        tunnel,
        pairing,
        "https://panel.example.test",
        "linux",
    )
    texts = read_tar_texts(content)
    root = "office-api-linux-bridge"

    assert f"{root}/agent-profile.json" in texts
    assert f"{root}/bootstrap-agent.py" in texts
    assert f"{root}/bridge-dashboard.py" in texts
    assert f"{root}/bridge-dashboard.json" in texts
    assert f"{root}/xray-bridge.json" not in texts
    profile = json.loads(texts[f"{root}/agent-profile.json"])

    assert profile["schema"] == 1
    assert profile["panel_url"] == "https://panel.example.test"
    assert profile["token_id"] == "pair_test_token"
    assert profile["pairing_token"] == "secret-token-dedicated"
    assert profile["bridge_id"] == "office-api"
    assert profile["bundle_kind"] == "dedicated"
    assert profile["platform"] == "linux"
    assert profile["agent_name"] == "Office API"
    assert profile["dashboard"] == {"host": "127.0.0.1", "port": 19090}
    assert profile["agent_id"] == "agent_test"
    assert profile["capabilities"] == ["bootstrap", "local_status"]
    assert profile["reserved"] == {"agent_id": "agent_test", "capabilities": ["bootstrap", "local_status"]}

    bootstrap = texts[f"{root}/bootstrap-agent.py"]
    install = texts[f"{root}/install-linux.sh"]
    assert "/api/agents/bootstrap" in bootstrap
    assert "agent-state.json" in bootstrap
    assert "xray-bridge.json" in bootstrap
    assert "bridge-dashboard.json" in bootstrap
    assert "pairing_token" in bootstrap
    assert "bootstrap-agent.py" in install
    assert "agent-profile.json" in install
    token_hits = [name for name, text in texts.items() if "secret-token-dedicated" in text]
    assert token_hits == [f"{root}/agent-profile.json"]


def test_paired_shared_agent_bundle_contains_shared_profile_and_installer_bootstrap():
    import tunnel_bridge_bundle

    tunnels = [
        sample_public_tunnel(
            id="web",
            name="Web",
            public_domain="web.example.com",
            target_port=3000,
            bridge_mode="shared",
            bridge_id="office-linux",
        ),
        sample_public_tunnel(
            id="api",
            name="API",
            public_domain="api.example.com",
            portal_port=18083,
            target_port=5000,
            client_id="33333333-3333-4333-8333-333333333333",
            bridge_mode="shared",
            bridge_id="office-linux",
        ),
    ]
    pairing = fake_pairing("secret-token-shared")
    pairing["record"].update({"bridge_id": "office-linux", "bundle_kind": "shared", "platform": "windows"})

    content = tunnel_bridge_bundle.build_paired_agent_bundle(
        "office-linux",
        tunnels,
        pairing,
        "https://panel.example.test/",
        "windows",
    )
    texts = read_tar_texts(content)
    root = "office-linux-windows-bridge"

    assert f"{root}/agent-profile.json" in texts
    assert f"{root}/bootstrap-agent.py" in texts
    assert f"{root}/bridge-dashboard.py" in texts
    assert f"{root}/bridge-dashboard.json" in texts
    assert f"{root}/xray-bridge.json" not in texts
    profile = json.loads(texts[f"{root}/agent-profile.json"])

    assert profile["panel_url"] == "https://panel.example.test/"
    assert profile["bridge_id"] == "office-linux"
    assert profile["bundle_kind"] == "shared"
    assert profile["platform"] == "windows"
    assert profile["agent_name"] == "office-linux"
    assert profile["pairing_token"] == "secret-token-shared"
    assert profile["reserved"] == {"agent_id": "agent_test", "capabilities": ["bootstrap", "local_status"]}
    assert "bootstrap-agent.py" in texts[f"{root}/install-windows.ps1"]
    assert "agent-profile.json" in texts[f"{root}/install-windows.ps1"]
    token_hits = [name for name, text in texts.items() if "secret-token-shared" in text]
    assert token_hits == [f"{root}/agent-profile.json"]


def test_bootstrap_agent_script_posts_profile_and_writes_local_state(tmp_path):
    import tunnel_bridge_bundle

    profile = {
        "schema": 1,
        "panel_url": "",
        "token_id": "pair_script",
        "pairing_token": "secret-script-token",
        "bridge_id": "office-api",
        "bundle_kind": "dedicated",
        "platform": "linux",
        "agent_name": "Office API",
        "dashboard": {"host": "127.0.0.1", "port": 19090},
        "agent_id": "",
        "capabilities": [],
    }
    captured = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            return

        def do_POST(self):
            length = int(self.headers["Content-Length"])
            captured["path"] = self.path
            captured["body"] = json.loads(self.rfile.read(length).decode("utf-8"))
            payload = {
                "ok": True,
                "agent": {"agent_id": "agent_script", "capabilities": ["bootstrap"]},
                "xray_config": {"outbounds": [{"tag": "tunnel-reverse-out"}]},
                "dashboard_metadata": {"bundle_kind": "dedicated", "bridge_id": "office-api"},
                "install": {"service_name": "fake-ui-tunnel-office-api.service"},
            }
            raw = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        profile["panel_url"] = f"http://127.0.0.1:{server.server_port}"
        (tmp_path / "agent-profile.json").write_text(json.dumps(profile), encoding="utf-8")
        script = tmp_path / "bootstrap-agent.py"
        script.write_text(tunnel_bridge_bundle.bootstrap_agent_script(), encoding="utf-8")

        subprocess.run([sys.executable, str(script)], cwd=tmp_path, check=True, text=True, capture_output=True)
    finally:
        server.shutdown()
        thread.join(timeout=5)

    assert captured["path"] == "/api/agents/bootstrap"
    assert captured["body"]["token_id"] == "pair_script"
    assert captured["body"]["pairing_token"] == "secret-script-token"
    assert json.loads((tmp_path / "xray-bridge.json").read_text(encoding="utf-8"))["outbounds"][0]["tag"] == "tunnel-reverse-out"
    assert json.loads((tmp_path / "bridge-dashboard.json").read_text(encoding="utf-8"))["bridge_id"] == "office-api"
    assert json.loads((tmp_path / "agent-state.json").read_text(encoding="utf-8"))["agent"]["agent_id"] == "agent_script"
    sanitized = json.loads((tmp_path / "agent-profile.json").read_text(encoding="utf-8"))
    assert sanitized.get("pairing_token", "") == ""

    subprocess.run([sys.executable, str(script)], cwd=tmp_path, check=True, text=True, capture_output=True)


def test_bootstrap_agent_script_accepts_complete_local_state_with_stale_token(tmp_path):
    import tunnel_bridge_bundle

    profile = {
        "schema": 1,
        "panel_url": "http://127.0.0.1:9",
        "token_id": "pair_stale",
        "pairing_token": "already-used-token",
        "bridge_id": "office-api",
        "bundle_kind": "dedicated",
        "platform": "linux",
        "agent_name": "Office API",
        "dashboard": {"host": "127.0.0.1", "port": 19090},
        "reserved": {"agent_id": "agent_stale", "capabilities": ["bootstrap"]},
    }
    (tmp_path / "agent-profile.json").write_text(json.dumps(profile), encoding="utf-8")
    (tmp_path / "xray-bridge.json").write_text("{}", encoding="utf-8")
    (tmp_path / "bridge-dashboard.json").write_text("{}", encoding="utf-8")
    (tmp_path / "agent-state.json").write_text("{}", encoding="utf-8")
    script = tmp_path / "bootstrap-agent.py"
    script.write_text(tunnel_bridge_bundle.bootstrap_agent_script(), encoding="utf-8")

    subprocess.run([sys.executable, str(script)], cwd=tmp_path, check=True, text=True, capture_output=True)

    sanitized = json.loads((tmp_path / "agent-profile.json").read_text(encoding="utf-8"))
    assert sanitized["pairing_token"] == ""


def test_paired_agent_bundle_routes_create_pairing_and_use_public_base_url(monkeypatch):
    import api_tunnel_routes

    tunnel = sample_public_tunnel()
    shared_tunnels = [sample_public_tunnel(id="web", bridge_mode="shared", bridge_id="office-linux")]
    created = []

    monkeypatch.setenv("PUBLIC_BASE_URL", "https://panel.example.test")
    monkeypatch.setattr(api_tunnel_routes.tunnel_catalog, "get_tunnel", lambda node_id: tunnel)
    monkeypatch.setattr(api_tunnel_routes.tunnel_catalog, "reality_profile_for_tunnel", lambda item: sample_reality_profile())
    monkeypatch.setattr(api_tunnel_routes.tunnel_catalog, "list_tunnels", lambda include_disabled=False: shared_tunnels)

    def create_pairing(bundle_kind, bridge_id, platform, created_by="admin"):
        created.append((bundle_kind, bridge_id, platform, created_by))
        result = fake_pairing(f"secret-token-{bundle_kind}")
        result["record"].update({"bundle_kind": bundle_kind, "bridge_id": bridge_id, "platform": platform})
        return result

    monkeypatch.setattr(api_tunnel_routes.agent_pairing, "create_pairing", create_pairing)

    status, dedicated = api_tunnel_routes.handle_tunnel_get(
        "/api/tunnels/office-api/linux-agent-bundle",
        {"u": "alice", "role": "admin"},
    )
    status2, shared = api_tunnel_routes.handle_tunnel_get(
        "/api/tunnels/bridges/office-linux/windows-agent-bundle",
        {"u": "bob", "role": "admin"},
    )

    assert status == 200
    assert status2 == 200
    assert dedicated["filename"] == "office-api-linux-agent-bridge.tgz"
    assert shared["filename"] == "office-linux-windows-agent-bridge.tgz"
    assert created == [
        ("dedicated", "office-api", "linux", "alice"),
        ("shared", "office-linux", "windows", "bob"),
    ]
    dedicated_profile = json.loads(read_tar_texts(dedicated["content"])["office-api-linux-bridge/agent-profile.json"])
    shared_profile = json.loads(read_tar_texts(shared["content"])["office-linux-windows-bridge/agent-profile.json"])
    assert dedicated_profile["panel_url"] == "https://panel.example.test"
    assert dedicated_profile["bundle_kind"] == "dedicated"
    assert shared_profile["panel_url"] == "https://panel.example.test"
    assert shared_profile["bundle_kind"] == "shared"


def test_shared_paired_agent_bundle_route_does_not_build_unused_xray_config(monkeypatch):
    import api_tunnel_routes

    shared_tunnels = [sample_public_tunnel(id="web", bridge_mode="shared", bridge_id="office-linux")]
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://panel.example.test")
    monkeypatch.setattr(api_tunnel_routes.tunnel_catalog, "list_tunnels", lambda include_disabled=False: shared_tunnels)
    monkeypatch.setattr(api_tunnel_routes.tunnel_catalog, "reality_profile_for_tunnel", lambda item: sample_reality_profile())
    monkeypatch.setattr(api_tunnel_routes.agent_pairing, "create_pairing", lambda *args, **kwargs: fake_pairing("route-token"))

    def fail_build_shared_bridge_config(*args, **kwargs):
        raise AssertionError("paired agent bundle should bootstrap config later")

    monkeypatch.setattr(api_tunnel_routes.tunnel_config_builder, "build_shared_bridge_config", fail_build_shared_bridge_config)

    status, payload = api_tunnel_routes.handle_tunnel_get(
        "/api/tunnels/bridges/office-linux/linux-agent-bundle",
        {"u": "alice", "role": "admin"},
    )

    assert status == 200
    assert payload["filename"] == "office-linux-linux-agent-bridge.tgz"


def test_dedicated_paired_agent_bundle_route_rejects_shared_tunnel(monkeypatch):
    import api_tunnel_routes

    tunnel = sample_public_tunnel(bridge_mode="shared", bridge_id="office-linux")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://panel.example.test")
    monkeypatch.setattr(api_tunnel_routes.tunnel_catalog, "get_tunnel", lambda node_id: tunnel)

    def fail_create_pairing(*args, **kwargs):
        raise AssertionError("shared tunnels must use the shared paired agent endpoint")

    monkeypatch.setattr(api_tunnel_routes.agent_pairing, "create_pairing", fail_create_pairing)

    status, payload = api_tunnel_routes.handle_tunnel_get(
        "/api/tunnels/office-api/linux-agent-bundle",
        {"u": "alice", "role": "admin"},
    )

    assert status == 400
    assert payload["ok"] is False
    assert "shared" in payload["error"]


def test_standalone_bridge_client_assets_include_safe_bootstrap_templates():
    spec = importlib.util.spec_from_file_location("package_bridge_client", ROOT / "scripts" / "package-bridge-client.py")
    package_bridge_client = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(package_bridge_client)

    files = package_bridge_client.files_for_platform("linux", "3.0.2")
    profile = json.loads(files["agent-profile.example.json"])
    raw = "\n".join(files.values())

    assert "bootstrap-agent.py" in files
    assert "agent-profile.example.json" in files
    assert profile["schema"] == 1
    assert profile["panel_url"] == "https://your-panel.example.com"
    assert profile["token_id"] == "pair_example_token_id"
    assert profile["pairing_token"] == "replace-with-one-time-pairing-token"
    assert profile["reserved"] == {"agent_id": "", "capabilities": []}
    assert "/api/agents/bootstrap" in files["bootstrap-agent.py"]
    assert "agent-state.json" in files["bootstrap-agent.py"]
    assert "profile.get(\"reserved\")" in files["bootstrap-agent.py"]
    assert "secret-token" not in raw
    assert "api.example.com" not in raw
    assert "11111111-1111-4111-8111-111111111111" not in raw
    assert "your-panel.example.com" in raw


def test_bridge_dashboard_serves_local_status_json(tmp_path):
    import tunnel_bridge_bundle

    metadata = tunnel_bridge_bundle.dashboard_metadata(
        "dedicated",
        "office-api",
        "linux",
        [
            {
                "id": "office-api",
                "kind": "public_https",
                "name": "Office API",
                "public_domain": "api.example.com",
                "portal_port": 18082,
                "target_host": "127.0.0.1",
                "target_port": 9,
            }
        ],
    )
    (tmp_path / "bridge-dashboard.json").write_text(json.dumps(metadata), encoding="utf-8")
    (tmp_path / "xray-bridge.json").write_text("{}", encoding="utf-8")
    script = tmp_path / "bridge-dashboard.py"
    script.write_text(tunnel_bridge_bundle.dashboard_script(), encoding="utf-8")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    proc = subprocess.Popen(
        [sys.executable, str(script), "--host", "127.0.0.1", "--port", str(port)],
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        for _ in range(40):
            try:
                with opener.open(f"http://127.0.0.1:{port}/status.json", timeout=1) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                    break
            except OSError:
                time.sleep(0.05)
        else:
            raise AssertionError("dashboard did not start")
    finally:
        proc.terminate()
        proc.wait(timeout=5)

    assert payload["metadata"]["dashboard"] == {"host": "127.0.0.1", "port": 19090}
    assert payload["metadata"]["runtime"]["restart_command"] == "sudo systemctl restart fake-ui-tunnel-office-api.service"
    assert payload["metadata"]["runtime"]["log_command"] == "journalctl -u fake-ui-tunnel-office-api.service -n 80 --no-pager"
    assert payload["logs"][0]["path"].endswith("bridge-dashboard.out.log")
    assert "config_preview" not in payload
    assert payload["xray_config"]["ok"] is True
    assert payload["services"][0]["id"] == "office-api"
    assert payload["services"][0]["local_reachable"]["ok"] is False


def test_bridge_dashboard_rejects_non_local_host_header(tmp_path):
    import tunnel_bridge_bundle

    metadata = tunnel_bridge_bundle.dashboard_metadata(
        "dedicated",
        "office-api",
        "linux",
        [
            {
                "id": "office-api",
                "kind": "public_https",
                "name": "Office API",
                "public_domain": "api.example.com",
                "portal_port": 18082,
                "target_host": "127.0.0.1",
                "target_port": 9,
            }
        ],
    )
    (tmp_path / "bridge-dashboard.json").write_text(json.dumps(metadata), encoding="utf-8")
    (tmp_path / "xray-bridge.json").write_text("{}", encoding="utf-8")
    script = tmp_path / "bridge-dashboard.py"
    script.write_text(tunnel_bridge_bundle.dashboard_script(), encoding="utf-8")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    proc = subprocess.Popen(
        [sys.executable, str(script), "--host", "127.0.0.1", "--port", str(port)],
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        for _ in range(40):
            try:
                with opener.open(f"http://127.0.0.1:{port}/status.json", timeout=1):
                    break
            except OSError:
                time.sleep(0.05)
        else:
            raise AssertionError("dashboard did not start")
        request = urllib.request.Request(f"http://127.0.0.1:{port}/status.json", headers={"Host": "evil.example"})
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            opener.open(request, timeout=1)
    finally:
        proc.terminate()
        proc.wait(timeout=5)

    assert excinfo.value.code == 403


def test_bridge_dashboard_imports_local_json_files(tmp_path):
    import tunnel_bridge_bundle

    metadata = tunnel_bridge_bundle.dashboard_metadata(
        "dedicated",
        "office-api",
        "linux",
        [
            {
                "id": "office-api",
                "kind": "public_https",
                "name": "Office API",
                "public_domain": "api.example.com",
                "portal_port": 18082,
                "target_host": "127.0.0.1",
                "target_port": 9,
            }
        ],
    )
    (tmp_path / "bridge-dashboard.json").write_text(json.dumps(metadata), encoding="utf-8")
    (tmp_path / "xray-bridge.json").write_text("{}", encoding="utf-8")
    script = tmp_path / "bridge-dashboard.py"
    script.write_text(tunnel_bridge_bundle.dashboard_script(), encoding="utf-8")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    proc = subprocess.Popen(
        [sys.executable, str(script), "--host", "127.0.0.1", "--port", str(port)],
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        for _ in range(40):
            try:
                with opener.open(f"http://127.0.0.1:{port}/status.json", timeout=1):
                    break
            except OSError:
                time.sleep(0.05)
        else:
            raise AssertionError("dashboard did not start")

        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/import",
            data=json.dumps({"filename": "xray-bridge.json", "content": {"log": {"loglevel": "warning"}}}).encode("utf-8"),
            headers={"Content-Type": "application/json", "Host": f"127.0.0.1:{port}"},
            method="POST",
        )
        with opener.open(request, timeout=1) as response:
            payload = json.loads(response.read().decode("utf-8"))

        bad_request = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/import",
            data=json.dumps({"filename": "../escape.json", "content": {}}).encode("utf-8"),
            headers={"Content-Type": "application/json", "Host": f"127.0.0.1:{port}"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            opener.open(bad_request, timeout=1)
    finally:
        proc.terminate()
        proc.wait(timeout=5)

    assert payload == {"ok": True, "filename": "xray-bridge.json"}
    assert json.loads((tmp_path / "xray-bridge.json").read_text(encoding="utf-8")) == {"log": {"loglevel": "warning"}}
    assert excinfo.value.code == 400


def test_bridge_dashboard_importing_xray_config_updates_service_metadata(tmp_path):
    import tunnel_bridge_bundle
    import tunnel_config_builder

    old_metadata = tunnel_bridge_bundle.dashboard_metadata(
        "dedicated",
        "old-api",
        "linux",
        [
            {
                "id": "old-api",
                "kind": "public_https",
                "name": "old.example.com",
                "public_domain": "old.example.com",
                "portal_port": 18082,
                "target_host": "127.0.0.1",
                "target_port": 18080,
            }
        ],
    )
    node = {
        "id": "new-guangyuego-top",
        "name": "new.guangyuego.top",
        "kind": "public_https",
        "public_domain": "new.guangyuego.top",
        "client_id": "11111111-1111-4111-8111-111111111111",
        "target_host": "127.0.0.1",
        "target_port": 8888,
        "portal_port": 18088,
        "flow": "xtls-rprx-vision",
    }
    cfg = tunnel_config_builder.build_bridge_config(
        node,
        {
            "address": "new.guangyuego.top",
            "port": 443,
            "server_name": "www.cloudflare.com",
            "public_key": "public-key",
            "short_id": "abcd1234",
            "fingerprint": "chrome",
        },
    )
    (tmp_path / "bridge-dashboard.json").write_text(json.dumps(old_metadata), encoding="utf-8")
    (tmp_path / "xray-bridge.json").write_text("{}", encoding="utf-8")
    script = tmp_path / "bridge-dashboard.py"
    script.write_text(tunnel_bridge_bundle.dashboard_script(), encoding="utf-8")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    proc = subprocess.Popen(
        [sys.executable, str(script), "--host", "127.0.0.1", "--port", str(port)],
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        for _ in range(40):
            try:
                with opener.open(f"http://127.0.0.1:{port}/status.json", timeout=1):
                    break
            except OSError:
                time.sleep(0.05)
        else:
            raise AssertionError("dashboard did not start")

        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/import",
            data=json.dumps({"filename": "xray-bridge.json", "content": cfg}).encode("utf-8"),
            headers={"Content-Type": "application/json", "Host": f"127.0.0.1:{port}"},
            method="POST",
        )
        with opener.open(request, timeout=1) as response:
            import_payload = json.loads(response.read().decode("utf-8"))

        with opener.open(f"http://127.0.0.1:{port}/status.json", timeout=1) as response:
            status = json.loads(response.read().decode("utf-8"))
    finally:
        proc.terminate()
        proc.wait(timeout=5)

    services = status["metadata"]["services"]
    assert import_payload["ok"] is True
    assert import_payload["filename"] == "xray-bridge.json"
    assert import_payload["metadata_updated"] is True
    assert [(item["public_domain"], item["local"]) for item in services] == [("new.guangyuego.top", "127.0.0.1:8888")]
    assert json.loads((tmp_path / "bridge-dashboard.json").read_text(encoding="utf-8"))["services"][0]["public_domain"] == "new.guangyuego.top"


def test_bridge_dashboard_importing_ip_xray_config_preserves_public_domain(tmp_path):
    import tunnel_bridge_bundle
    import tunnel_config_builder

    metadata = tunnel_bridge_bundle.dashboard_metadata(
        "dedicated",
        "new-guangyuego-top",
        "linux",
        [
            {
                "id": "new-guangyuego-top",
                "kind": "public_https",
                "name": "new.guangyuego.top",
                "public_domain": "new.guangyuego.top",
                "portal_port": 18085,
                "target_host": "127.0.0.1",
                "target_port": 8888,
            }
        ],
    )
    node = {
        "id": "new-guangyuego-top",
        "name": "new.guangyuego.top",
        "kind": "public_https",
        "public_domain": "new.guangyuego.top",
        "client_id": "11111111-1111-4111-8111-111111111111",
        "target_host": "127.0.0.1",
        "target_port": 8888,
        "portal_port": 18085,
        "flow": "xtls-rprx-vision",
    }
    cfg = tunnel_config_builder.build_bridge_config(
        node,
        {
            "address": "203.0.113.10",
            "port": 443,
            "server_name": "www.cloudflare.com",
            "public_key": "public-key",
            "short_id": "abcd1234",
            "fingerprint": "chrome",
        },
    )
    (tmp_path / "bridge-dashboard.json").write_text(json.dumps(metadata), encoding="utf-8")
    (tmp_path / "xray-bridge.json").write_text("{}", encoding="utf-8")
    script = tmp_path / "bridge-dashboard.py"
    script.write_text(tunnel_bridge_bundle.dashboard_script(), encoding="utf-8")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    proc = subprocess.Popen(
        [sys.executable, str(script), "--host", "127.0.0.1", "--port", str(port)],
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        for _ in range(40):
            try:
                with opener.open(f"http://127.0.0.1:{port}/status.json", timeout=1):
                    break
            except OSError:
                time.sleep(0.05)
        else:
            raise AssertionError("dashboard did not start")

        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/import",
            data=json.dumps(
                {
                    "filename": "xray-bridge.json",
                    "source_filename": "new-guangyuego-top-xray-bridge.json",
                    "content": cfg,
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json", "Host": f"127.0.0.1:{port}"},
            method="POST",
        )
        with opener.open(request, timeout=1) as response:
            import_payload = json.loads(response.read().decode("utf-8"))

        with opener.open(f"http://127.0.0.1:{port}/status.json", timeout=1) as response:
            status = json.loads(response.read().decode("utf-8"))
    finally:
        proc.terminate()
        proc.wait(timeout=5)

    assert import_payload["ok"] is True
    assert status["metadata"]["services"][0]["id"] == "new-guangyuego-top"
    assert status["metadata"]["services"][0]["public_domain"] == "new.guangyuego.top"
    assert status["metadata"]["services"][0]["public_url"] == "https://new.guangyuego.top/"


def test_bridge_dashboard_import_preserves_local_network_overrides(tmp_path):
    import tunnel_bridge_bundle
    import tunnel_config_builder

    metadata = tunnel_bridge_bundle.dashboard_metadata(
        "dedicated",
        "new-guangyuego-top",
        "linux",
        [
            {
                "id": "new-guangyuego-top",
                "kind": "public_https",
                "name": "new.guangyuego.top",
                "public_domain": "new.guangyuego.top",
                "portal_port": 18085,
                "target_host": "127.0.0.1",
                "target_port": 8888,
            }
        ],
    )
    node = {
        "id": "new-guangyuego-top",
        "name": "new.guangyuego.top",
        "kind": "public_https",
        "public_domain": "new.guangyuego.top",
        "client_id": "11111111-1111-4111-8111-111111111111",
        "target_host": "127.0.0.1",
        "target_port": 8888,
        "portal_port": 18085,
        "flow": "xtls-rprx-vision",
    }
    imported_cfg = tunnel_config_builder.build_bridge_config(
        node,
        {
            "address": "new.guangyuego.top",
            "port": 443,
            "server_name": "www.cloudflare.com",
            "public_key": "public-key",
            "short_id": "abcd1234",
            "fingerprint": "chrome",
        },
    )
    existing_cfg = json.loads(json.dumps(imported_cfg))
    reverse = next(item for item in existing_cfg["outbounds"] if item["tag"] == "tunnel-reverse-out")
    reverse["settings"]["address"] = "203.0.113.10"
    reverse["streamSettings"]["sockopt"] = {"interface": "en0"}

    (tmp_path / "bridge-dashboard.json").write_text(json.dumps(metadata), encoding="utf-8")
    (tmp_path / "xray-bridge.json").write_text(json.dumps(existing_cfg), encoding="utf-8")
    script = tmp_path / "bridge-dashboard.py"
    script.write_text(tunnel_bridge_bundle.dashboard_script(), encoding="utf-8")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    proc = subprocess.Popen(
        [sys.executable, str(script), "--host", "127.0.0.1", "--port", str(port)],
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        for _ in range(40):
            try:
                with opener.open(f"http://127.0.0.1:{port}/status.json", timeout=1):
                    break
            except OSError:
                time.sleep(0.05)
        else:
            raise AssertionError("dashboard did not start")

        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/import",
            data=json.dumps(
                {
                    "filename": "xray-bridge.json",
                    "source_filename": "new-guangyuego-top-xray-bridge.json",
                    "content": imported_cfg,
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json", "Host": f"127.0.0.1:{port}"},
            method="POST",
        )
        with opener.open(request, timeout=1) as response:
            payload = json.loads(response.read().decode("utf-8"))
    finally:
        proc.terminate()
        proc.wait(timeout=5)

    saved_cfg = json.loads((tmp_path / "xray-bridge.json").read_text(encoding="utf-8"))
    saved_reverse = next(item for item in saved_cfg["outbounds"] if item["tag"] == "tunnel-reverse-out")
    assert payload["ok"] is True
    assert saved_reverse["settings"]["address"] == "203.0.113.10"
    assert saved_reverse["streamSettings"]["sockopt"] == {"interface": "en0"}


def test_bridge_dashboard_rejects_xray_config_imported_as_metadata(tmp_path):
    import tunnel_bridge_bundle
    import tunnel_config_builder

    metadata = tunnel_bridge_bundle.dashboard_metadata(
        "dedicated",
        "old-api",
        "linux",
        [
            {
                "id": "old-api",
                "kind": "public_https",
                "name": "old.example.com",
                "public_domain": "old.example.com",
                "portal_port": 18082,
                "target_host": "127.0.0.1",
                "target_port": 18080,
            }
        ],
    )
    cfg = tunnel_config_builder.build_bridge_config(
        {
            "id": "new-guangyuego-top",
            "public_domain": "new.guangyuego.top",
            "client_id": "11111111-1111-4111-8111-111111111111",
            "target_host": "127.0.0.1",
            "target_port": 8888,
        },
        {
            "address": "new.guangyuego.top",
            "port": 443,
            "server_name": "www.cloudflare.com",
            "public_key": "public-key",
            "short_id": "abcd1234",
        },
    )
    (tmp_path / "bridge-dashboard.json").write_text(json.dumps(metadata), encoding="utf-8")
    (tmp_path / "xray-bridge.json").write_text("{}", encoding="utf-8")
    script = tmp_path / "bridge-dashboard.py"
    script.write_text(tunnel_bridge_bundle.dashboard_script(), encoding="utf-8")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    proc = subprocess.Popen(
        [sys.executable, str(script), "--host", "127.0.0.1", "--port", str(port)],
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        for _ in range(40):
            try:
                with opener.open(f"http://127.0.0.1:{port}/status.json", timeout=1):
                    break
            except OSError:
                time.sleep(0.05)
        else:
            raise AssertionError("dashboard did not start")

        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/import",
            data=json.dumps({"filename": "bridge-dashboard.json", "content": cfg}).encode("utf-8"),
            headers={"Content-Type": "application/json", "Host": f"127.0.0.1:{port}"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            opener.open(request, timeout=1)
    finally:
        proc.terminate()
        proc.wait(timeout=5)

    assert excinfo.value.code == 400
    assert json.loads((tmp_path / "bridge-dashboard.json").read_text(encoding="utf-8"))["services"][0]["public_domain"] == "old.example.com"


def test_bridge_dashboard_restarts_runtime_from_local_api(tmp_path):
    import tunnel_bridge_bundle

    metadata = tunnel_bridge_bundle.dashboard_metadata(
        "dedicated",
        "office-api",
        "linux",
        [
            {
                "id": "office-api",
                "kind": "public_https",
                "name": "Office API",
                "public_domain": "api.example.com",
                "portal_port": 18082,
                "target_host": "127.0.0.1",
                "target_port": 9,
            }
        ],
    )
    metadata["runtime"]["restart_command"] = f"{sys.executable} -c \"from pathlib import Path; Path('restart-marker').write_text('ok')\""
    (tmp_path / "bridge-dashboard.json").write_text(json.dumps(metadata), encoding="utf-8")
    (tmp_path / "xray-bridge.json").write_text("{}", encoding="utf-8")
    script = tmp_path / "bridge-dashboard.py"
    script.write_text(tunnel_bridge_bundle.dashboard_script(), encoding="utf-8")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    proc = subprocess.Popen(
        [sys.executable, str(script), "--host", "127.0.0.1", "--port", str(port)],
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        for _ in range(40):
            try:
                with opener.open(f"http://127.0.0.1:{port}/", timeout=1) as response:
                    page = response.read().decode("utf-8")
                    break
            except OSError:
                time.sleep(0.05)
        else:
            raise AssertionError("dashboard did not start")

        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/restart",
            data=b"{}",
            headers={"Content-Type": "application/json", "Host": f"127.0.0.1:{port}"},
            method="POST",
        )
        with opener.open(request, timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
    finally:
        proc.terminate()
        proc.wait(timeout=5)

    assert "重启 Bridge" in page
    assert "restartBridge" in page
    assert "POST /api/restart" in page
    assert payload["ok"] is True
    assert payload["message"]
    assert (tmp_path / "restart-marker").read_text(encoding="utf-8") == "ok"


def test_bridge_dashboard_script_uses_fake_ui_shell_and_redacts_sensitive_values():
    import tunnel_bridge_bundle

    script = tunnel_bridge_bundle.dashboard_script()

    for token in ["--bg", "--surface", "--primary", "--accent", "--radius"]:
        assert token in script
    for marker in [
        "app-shell",
        "side-nav",
        "overview-section",
        "services-section",
        "import-section",
        "instructions-section",
        "debug-section",
        "api-section",
        "metric-grid",
        "service-table",
        "function importConfig",
        "fetch('/api/import'",
        "function restartBridge",
        "fetch('/api/restart'",
        "GET /status.json",
        "POST /api/restart",
    ]:
        assert marker in script
    for label in ["概览", "服务状态", "导入配置", "使用说明", "日志/调试", "选择 JSON 文件", "重启 Bridge", "常见问题"]:
        assert label in script
    assert "def redact_sensitive" in script
    assert "def xray_config_preview" in script
    assert "def import_json_file" in script
    assert "pairing_token" in script
    assert "privateKey" in script
    assert "publicKey" in script
    assert "shortId" in script


def test_bridge_dashboard_render_redacts_logs_and_config_snippets(tmp_path):
    import tunnel_bridge_bundle

    script_path = tmp_path / "bridge_dashboard_runtime.py"
    script_path.write_text(tunnel_bridge_bundle.dashboard_script(), encoding="utf-8")
    spec = importlib.util.spec_from_file_location("bridge_dashboard_runtime", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    secret_uuid = "11111111-1111-4111-8111-111111111111"
    secret_v7_uuid = "01890f8e-7d1a-7cc2-98c4-0b7a8fb2cabc"
    secret_nil_uuid = "00000000-0000-0000-0000-000000000000"
    secret_token = "pairing_token=super-secret-token"
    secret_public = '"publicKey": "server-public-key"'
    secret_private = '"privateKey": "server-private-key"'
    secret_short = '"shortId": "0123456789abcdef"'
    status = {
        "metadata": {
            "bundle_kind": "dedicated",
            "bridge_id": "office-api",
            "platform": "linux",
            "dashboard": {"host": "127.0.0.1", "port": 19090},
            "runtime": {"name": "fake-ui-tunnel-office-api.service", "restart_command": "sudo systemctl restart fake-ui-tunnel-office-api.service"},
            "services": [],
        },
        "runtime": {"ok": True, "message": "running"},
        "xray_config": {"ok": True, "path": str(tmp_path / "xray-bridge.json"), "message": "valid json"},
        "services": [],
        "logs": [
            {
                "path": str(tmp_path / "bridge.err.log"),
                "exists": True,
                "tail": f"{secret_uuid}\n{secret_v7_uuid}\n{secret_nil_uuid}\n{secret_token}\n{secret_public}\n{secret_private}\n{secret_short}",
            }
        ],
        "config_preview": f"{secret_uuid}\n{secret_v7_uuid}\n{secret_nil_uuid}\n{secret_public}\n{secret_private}\n{secret_short}",
    }

    html = module.render_dashboard(status).decode("utf-8")

    assert secret_uuid not in html
    assert secret_v7_uuid not in html
    assert secret_nil_uuid not in html
    assert "super-secret-token" not in html
    assert "server-public-key" not in html
    assert "server-private-key" not in html
    assert "0123456789abcdef" not in html
    assert "[redacted" in html


def test_bridge_dashboard_keeps_raw_runtime_output_inside_debug_details(tmp_path):
    import tunnel_bridge_bundle

    script_path = tmp_path / "bridge_dashboard_runtime.py"
    script_path.write_text(tunnel_bridge_bundle.dashboard_script(), encoding="utf-8")
    spec = importlib.util.spec_from_file_location("bridge_dashboard_runtime", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    raw_runtime = "gui/501/com.fakeui.bridge.client = { active count = 1 path = /Users/example/Library/LaunchAgents/com.fakeui.bridge.client.plist }"
    status = {
        "metadata": {
            "bundle_kind": "bridge-client",
            "bridge_id": "macbook-web",
            "platform": "macos",
            "dashboard": {"host": "127.0.0.1", "port": 19090},
            "runtime": {"name": "com.fakeui.bridge.client", "restart_command": "launchctl kickstart -k gui/$(id -u)/com.fakeui.bridge.client"},
            "services": [],
        },
        "runtime": {"ok": True, "message": raw_runtime},
        "xray_config": {"ok": True, "path": str(tmp_path / "xray-bridge.json"), "message": "valid json"},
        "services": [],
        "logs": [],
        "config_preview": "{}",
    }

    html = module.render_dashboard(status).decode("utf-8")
    topbar = html.split("</header>", 1)[0]

    assert "运行中" in topbar
    assert raw_runtime not in topbar
    assert raw_runtime in html
    assert "运行时详情" in html


def test_bridge_dashboard_accepts_manual_client_runtime(tmp_path):
    import tunnel_bridge_bundle

    metadata = {
        "bundle_kind": "client-template",
        "bridge_id": "client-template",
        "platform": "macos",
        "dashboard": {"host": "127.0.0.1", "port": 19090},
        "runtime": {
            "kind": "manual",
            "name": "fake-ui bridge client",
            "restart_command": "bash stop-bridge.sh && bash start-bridge.sh",
            "log_command": "open bridge-client.err.log",
        },
        "logs": ["bridge-dashboard.out.log"],
        "xray_config": {"path": "xray-bridge.json"},
        "services": [],
    }
    (tmp_path / "bridge-dashboard.json").write_text(json.dumps(metadata), encoding="utf-8")
    (tmp_path / "xray-bridge.json").write_text("{}", encoding="utf-8")
    script = tmp_path / "bridge-dashboard.py"
    script.write_text(tunnel_bridge_bundle.dashboard_script(), encoding="utf-8")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    proc = subprocess.Popen(
        [sys.executable, str(script), "--host", "127.0.0.1", "--port", str(port)],
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        for _ in range(40):
            try:
                with opener.open(f"http://127.0.0.1:{port}/status.json", timeout=1) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                    break
            except OSError:
                time.sleep(0.05)
        else:
            raise AssertionError("dashboard did not start")
    finally:
        proc.terminate()
        proc.wait(timeout=5)

    assert payload["runtime"]["ok"] is True
    assert payload["runtime"]["message"] == "manual client mode"
