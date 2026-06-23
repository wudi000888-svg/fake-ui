from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_install_script_uses_panel_domain_for_hy2_masquerade():
    script = (ROOT / "scripts" / "install-fresh-vps.sh").read_text(encoding="utf-8")

    assert "HY2_MASQUERADE_URL=https://$PANEL_DOMAIN" in script
    assert 'HY2_MASQUERADE_URL="https://$PANEL_DOMAIN"' in script
    assert "TUNNEL_SERVER_IPS=$PUBLIC_IP" in script
    assert 'TUNNEL_SERVER_IPS="$PUBLIC_IP"' in script
    assert "无法自动检测公网 IP" in script
    assert "HY2_MASQUERADE_URL=https://$ROOT_DOMAIN" not in script
    assert 'HY2_MASQUERADE_URL="https://$ROOT_DOMAIN"' not in script


def test_install_script_checks_v2_module_entry_and_sets_version():
    script = (ROOT / "scripts" / "install-fresh-vps.sh").read_text(encoding="utf-8")
    deploy = (ROOT / "scripts" / "deploy-compose-windows.ps1").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    routes = (ROOT / "baseline" / "api_v2_routes.py").read_text(encoding="utf-8")

    assert "FAKE_UI_VERSION=3.0.2" in script
    assert "FAKE_UI_VERSION: ${FAKE_UI_VERSION:-3.0.2}" in compose
    assert "FAKE_UI_STORE" not in script
    assert "FAKE_UI_STORE" not in compose
    assert "migrate-json-to-sqlite.py" not in script
    assert "migrate-json-to-sqlite.py" not in deploy
    assert "export-sqlite-to-json.py" not in script
    assert "export-sqlite-to-json.py" not in deploy
    assert '"FAKE_UI_VERSION": "3.0.2"' in deploy
    assert "/assets/js/main.js" in script
    assert "/assets/app.js" not in script
    assert "/assets/app.js" not in deploy
    assert "APP_VERSION" in routes


def test_default_runtime_images_are_pinned_not_latest():
    script = (ROOT / "scripts" / "install-fresh-vps.sh").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "ghcr.io/xtls/xray-core:26.3.27" in script
    assert "tobyxdd/hysteria:v2.9.2" in script
    assert "certbot/certbot:v5.2.2" in script
    assert "nginx:1.27-alpine" in script
    assert ":latest" not in script
    assert ":latest" not in compose


def test_docker_dns_defaults_avoid_polluted_domestic_resolvers():
    script = (ROOT / "scripts" / "install-fresh-vps.sh").read_text(encoding="utf-8")

    assert 'cp /etc/docker/daemon.json "/etc/docker/daemon.json.bak.$(date +%Y%m%d%H%M%S)"' in script
    assert "&& ! grep -q '\"dns\"' /etc/docker/daemon.json" not in script
    assert '"dns": ["1.1.1.1", "8.8.8.8", "9.9.9.9", "208.67.222.222"]' in script
    assert "183.60.83.19" not in script
    assert "183.60.82.98" not in script
    assert "223.5.5.5" not in script
    assert "119.29.29.29" not in script


def test_windows_deploy_refuses_dirty_worktree_by_default():
    deploy = (ROOT / "scripts" / "deploy-compose-windows.ps1").read_text(encoding="utf-8")

    assert "[switch]$AllowDirtyHead" in deploy
    assert "git status --porcelain" in deploy
    assert "Refusing to deploy with uncommitted changes" in deploy
    assert "git archive --format=tar -o $Archive HEAD" in deploy


def test_native_nginx_install_includes_security_headers():
    script = (ROOT / "scripts" / "install-fresh-vps.sh").read_text(encoding="utf-8")

    assert 'add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;' in script
    assert 'add_header X-Content-Type-Options "nosniff" always;' in script
    assert 'add_header X-Frame-Options "DENY" always;' in script
    assert 'add_header Referrer-Policy "same-origin" always;' in script
    assert 'add_header Permissions-Policy "camera=(), microphone=(), geolocation=()" always;' in script
