import importlib
import pathlib
import sys

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[1]
BASELINE = ROOT / "baseline"
if str(BASELINE) not in sys.path:
    sys.path.insert(0, str(BASELINE))


MODULES = [
    "panel_config",
    "json_store",
    "auth_store",
    "user_store",
    "node_catalog",
    "plans_store",
    "orders_store",
    "payments_store",
    "payment_rates",
    "payment_wallets",
    "payment_verifier",
    "payment_service",
    "registration_store",
    "admin_profile",
    "audit_log",
    "backup_manager",
    "subscription_guard",
    "app_urls",
    "link_settings",
    "operations_service",
    "dashboard_service",
    "api_common",
    "api_payment_routes",
    "api_v2_routes",
    "api_get_routes",
    "api_post_routes",
    "api",
]


@pytest.fixture()
def v2_modules(tmp_path, monkeypatch):
    panel_dir = tmp_path / "panel"
    panel_dir.mkdir()
    monkeypatch.setenv("PANEL_DIR", str(panel_dir))
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.test")
    for name in MODULES:
        if name in sys.modules:
            importlib.reload(sys.modules[name])
        else:
            importlib.import_module(name)
    user_store = sys.modules["user_store"]
    user_store.save_users(
        {
            "version": 1,
            "users": {
                "alice": {
                    "enabled": True,
                    "sub_token": "tok_alice",
                    "quota_bytes": 100,
                    "used_bytes": 20,
                    "node_groups": ["default"],
                }
            },
        }
    )
    return {name: sys.modules[name] for name in MODULES}


def test_api_app_shell_and_me(v2_modules):
    api = v2_modules["api"]

    status, payload = api.handle_get("/api/app-shell", {"u": "alice", "r": "user", "role": "user"})
    assert status == 200
    assert payload["role"] == "user"
    assert [item["id"] for item in payload["nav"]] == [
        "dashboard",
        "plans",
        "links",
        "orders",
        "account",
    ]

    status, payload = api.handle_get("/api/me", {"u": "alice", "r": "user", "role": "user"})
    assert status == 200
    assert payload["username"] == "alice"
    assert payload["subscription_url"] == "https://example.test/sub/tok_alice"


def test_api_v2_cache_status_and_clear_are_admin_only(v2_modules):
    api = v2_modules["api"]
    cache_store = v2_modules["api_v2_routes"].cache_store
    cache_store.app_cache.get("dashboard", "admin", ttl=30, loader=lambda: {"ok": True})

    status, payload = api.handle_get("/api/cache/status", {"u": "admin", "r": "admin", "role": "admin"})
    assert status == 200
    assert payload["cache"]["items"] == 1

    status, payload = api.handle_post("/api/cache/clear", {}, {"u": "alice", "r": "user", "role": "user"})
    assert status == 403

    status, payload = api.handle_post("/api/cache/clear", {}, {"u": "admin", "r": "admin", "role": "admin"})
    assert status == 200
    assert payload["cache"]["items"] == 0


def test_admin_dashboard_survives_subscription_link_generation_failure(v2_modules, monkeypatch):
    api = v2_modules["api"]
    links = importlib.import_module("links")
    xray_panel = importlib.import_module("xray_panel")
    hy2_panel = importlib.import_module("hy2_panel")

    monkeypatch.setattr(
        links,
        "build_vless_links_for_airport_user",
        lambda username, user: (_ for _ in ()).throw(FileNotFoundError("xray")),
    )
    monkeypatch.setattr(xray_panel, "current_status", lambda: {"xray": "test", "proxy": ""})
    monkeypatch.setattr(hy2_panel, "hy2_status", lambda: {"running": "test"})

    status, payload = api.handle_get("/api/dashboard", {"u": "admin", "r": "admin", "role": "admin"})

    assert status == 200
    assert "data" in payload
    assert payload["data"]["links"]["error"] == "xray"
    assert "users" in payload["data"]
