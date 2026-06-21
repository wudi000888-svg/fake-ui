import json
import socket
import subprocess
import sys
import tarfile
import time
import urllib.request
from io import BytesIO
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "baseline"
if str(BASELINE) not in sys.path:
    sys.path.insert(0, str(BASELINE))


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
    assert payload["xray_config"]["ok"] is True
    assert payload["services"][0]["id"] == "office-api"
    assert payload["services"][0]["local_reachable"]["ok"] is False


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
