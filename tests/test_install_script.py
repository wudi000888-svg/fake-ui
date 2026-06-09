from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_install_script_uses_panel_domain_for_hy2_masquerade():
    script = (ROOT / "scripts" / "install-fresh-vps.sh").read_text(encoding="utf-8")

    assert "HY2_MASQUERADE_URL=https://$PANEL_DOMAIN" in script
    assert 'HY2_MASQUERADE_URL="https://$PANEL_DOMAIN"' in script
    assert "HY2_MASQUERADE_URL=https://$ROOT_DOMAIN" not in script
    assert 'HY2_MASQUERADE_URL="https://$ROOT_DOMAIN"' not in script


def test_install_script_checks_v2_module_entry_and_sets_version():
    script = (ROOT / "scripts" / "install-fresh-vps.sh").read_text(encoding="utf-8")
    deploy = (ROOT / "scripts" / "deploy-compose-windows.ps1").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    routes = (ROOT / "baseline" / "api_v2_routes.py").read_text(encoding="utf-8")

    assert "FAKE_UI_VERSION=2.1.2" in script
    assert "FAKE_UI_VERSION: ${FAKE_UI_VERSION:-2.1.2}" in compose
    assert "FAKE_UI_STORE" not in script
    assert "FAKE_UI_STORE" not in compose
    assert "migrate-json-to-sqlite.py" not in script
    assert "migrate-json-to-sqlite.py" not in deploy
    assert "export-sqlite-to-json.py" not in script
    assert "export-sqlite-to-json.py" not in deploy
    assert '"FAKE_UI_VERSION": "2.1.2"' in deploy
    assert "/assets/js/main.js" in script
    assert "/assets/app.js" not in script
    assert "/assets/app.js" not in deploy
    assert "APP_VERSION" in routes


def test_native_nginx_install_includes_security_headers():
    script = (ROOT / "scripts" / "install-fresh-vps.sh").read_text(encoding="utf-8")

    assert 'add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;' in script
    assert 'add_header X-Content-Type-Options "nosniff" always;' in script
    assert 'add_header X-Frame-Options "DENY" always;' in script
    assert 'add_header Referrer-Policy "same-origin" always;' in script
    assert 'add_header Permissions-Policy "camera=(), microphone=(), geolocation=()" always;' in script
