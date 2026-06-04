from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_install_script_uses_panel_domain_for_hy2_masquerade():
    script = (ROOT / "scripts" / "install-fresh-vps.sh").read_text(encoding="utf-8")

    assert "HY2_MASQUERADE_URL=https://$PANEL_DOMAIN" in script
    assert 'HY2_MASQUERADE_URL="https://$PANEL_DOMAIN"' in script
    assert "HY2_MASQUERADE_URL=https://$ROOT_DOMAIN" not in script
    assert 'HY2_MASQUERADE_URL="https://$ROOT_DOMAIN"' not in script
