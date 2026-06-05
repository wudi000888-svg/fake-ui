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

    assert "FAKE_UI_VERSION=2.0.1" in script
    assert "FAKE_UI_VERSION: ${FAKE_UI_VERSION:-2.0.1}" in compose
    assert "FAKE_UI_STORE=sqlite" in script
    assert "FAKE_UI_STORE: ${FAKE_UI_STORE:-sqlite}" in compose
    assert "migrate-json-to-sqlite.py" in script
    assert "migrate-json-to-sqlite.py" in deploy
    assert '"FAKE_UI_STORE": "sqlite"' in deploy
    assert '"FAKE_UI_VERSION": "2.0.1"' in deploy
    assert "/assets/js/main.js" in script
    assert "/assets/app.js" not in script
    assert "/assets/app.js" not in deploy
    assert "APP_VERSION" in routes
