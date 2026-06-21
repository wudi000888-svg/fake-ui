import importlib
import sys
import threading
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "baseline"
if str(BASELINE) not in sys.path:
    sys.path.insert(0, str(BASELINE))


MODULES = [
    "panel_config",
    "db_schema",
    "store_facade",
    "tunnel_catalog",
    "tunnel_config_builder",
    "tunnel_bridge_bundle",
    "agent_pairing",
    "api_agent_routes",
    "api_post_routes",
    "api",
    "http_api_routes",
]


def tunnel_payload(**overrides):
    data = {
        "id": "office-api",
        "kind": "public_https",
        "name": "Office API",
        "public_domain": "api.example.com",
        "portal_port": 18082,
        "target_host": "127.0.0.1",
        "target_port": 5000,
        "client_id": "11111111-1111-4111-8111-111111111111",
        "flow": "xtls-rprx-vision",
        "reality_sni": "www.cloudflare.com",
        "server_address": "vless.example.com",
        "server_port": 443,
        "internal_port": 8443,
        "public_key": "server-public-key",
        "short_id": "0123456789abcdef",
    }
    data.update(overrides)
    return data


@pytest.fixture()
def pairing_modules(tmp_path, monkeypatch):
    panel_dir = tmp_path / "panel"
    panel_dir.mkdir()
    monkeypatch.setenv("PANEL_DIR", str(panel_dir))
    monkeypatch.setenv("FAKE_UI_DB", str(panel_dir / "fake-ui.db"))
    for name in MODULES:
        if name in sys.modules:
            importlib.reload(sys.modules[name])
        else:
            importlib.import_module(name)
    sys.modules["db_schema"].migrate()
    return {name: sys.modules[name] for name in MODULES}


def test_create_pairing_hashes_token_and_returns_raw_token_once(pairing_modules):
    pairing = pairing_modules["agent_pairing"]
    settings = importlib.import_module("repositories.sqlite_settings").SQLiteSettingsRepository()

    result = pairing.create_pairing("dedicated", "office-api", "macos", created_by="admin")
    stored = settings.get("agent_pairings")
    record = stored["pairings"][result["record"]["token_id"]]

    assert result["pairing_token"]
    assert result["pairing_token"] != record["token_hash"]
    assert "pairing_token" not in result["record"]
    assert "pairing_token" not in record
    assert record["token_hash"]
    assert record["bundle_kind"] == "dedicated"
    assert record["bridge_id"] == "office-api"
    assert record["platform"] == "macos"


def test_bootstrap_agent_consumes_valid_token_once(pairing_modules):
    pairing = pairing_modules["agent_pairing"]
    tunnel_catalog = pairing_modules["tunnel_catalog"]
    tunnel_catalog.save_catalog({"version": 1, "tunnels": [tunnel_payload()]})
    created = pairing.create_pairing("dedicated", "office-api", "linux")

    response = pairing.bootstrap_agent(
        {
            "schema": 1,
            "token_id": created["record"]["token_id"],
            "pairing_token": created["pairing_token"],
            "platform": "linux",
            "agent_version": "3.0.2",
        }
    )

    assert response["agent"]["agent_id"]
    assert response["agent"]["bridge_id"] == "office-api"
    assert response["agent"]["bundle_kind"] == "dedicated"
    assert response["agent"]["capabilities"] == ["bootstrap", "local_status"]
    assert response["xray_config"]["outbounds"]
    assert response["dashboard_metadata"]["bridge_id"] == "office-api"
    assert response["dashboard_metadata"]["services"][0]["public_url"] == "https://api.example.com/"
    assert response["install"]["service_name"]

    with pytest.raises(RuntimeError, match="used"):
        pairing.bootstrap_agent(
            {
                "schema": 1,
                "token_id": created["record"]["token_id"],
                "pairing_token": created["pairing_token"],
            }
        )


def test_bootstrap_agent_rejects_expired_token(pairing_modules):
    pairing = pairing_modules["agent_pairing"]
    created = pairing.create_pairing("dedicated", "office-api", "macos")
    expired = datetime.now(timezone.utc) - timedelta(minutes=1)
    pairing.update_pairing(created["record"]["token_id"], {"expires_at": expired.isoformat()})

    with pytest.raises(RuntimeError, match="expired"):
        pairing.bootstrap_agent(
            {
                "schema": 1,
                "token_id": created["record"]["token_id"],
                "pairing_token": created["pairing_token"],
            }
        )


def test_public_bootstrap_route_returns_payload_without_admin_session(pairing_modules):
    api = pairing_modules["api"]
    pairing = pairing_modules["agent_pairing"]
    tunnel_catalog = pairing_modules["tunnel_catalog"]
    tunnel_catalog.save_catalog(
        {
            "version": 1,
            "tunnels": [
                tunnel_payload(
                    id="web",
                    name="Web",
                    public_domain="web.example.com",
                    target_port=3000,
                    bridge_mode="shared",
                    bridge_id="office-linux",
                    bridge_platform="linux",
                ),
                tunnel_payload(
                    id="api",
                    name="API",
                    public_domain="api.example.com",
                    portal_port=18083,
                    target_port=5000,
                    client_id="33333333-3333-4333-8333-333333333333",
                    bridge_mode="shared",
                    bridge_id="office-linux",
                    bridge_platform="linux",
                ),
            ],
        }
    )
    created = pairing.create_pairing("shared", "office-linux", "linux")

    status, payload = api.handle_post(
        "/api/agents/bootstrap",
        {
            "schema": 1,
            "token_id": created["record"]["token_id"],
            "pairing_token": created["pairing_token"],
            "platform": "linux",
        },
        None,
    )

    assert status == 200
    assert payload["ok"] is True
    assert payload["agent"]["agent_id"]
    assert payload["agent"]["bridge_id"] == "office-linux"
    assert payload["agent"]["capabilities"] == ["bootstrap", "local_status"]
    assert payload["dashboard_metadata"]["bundle_kind"] == "shared"
    assert [service["id"] for service in payload["dashboard_metadata"]["services"]] == ["web", "api"]
    assert payload["xray_config"]["routing"]["rules"]

    status, payload = api.handle_post(
        "/api/agents/bootstrap",
        {"schema": 1, "token_id": "missing", "pairing_token": "bad"},
        None,
    )

    assert status == 400
    assert payload["ok"] is False


def test_bootstrap_route_rejects_malformed_schema_without_consuming_token(pairing_modules):
    api = pairing_modules["api"]
    pairing = pairing_modules["agent_pairing"]
    tunnel_catalog = pairing_modules["tunnel_catalog"]
    tunnel_catalog.save_catalog({"version": 1, "tunnels": [tunnel_payload()]})
    created = pairing.create_pairing("dedicated", "office-api", "macos")
    payload = {
        "schema": 1.5,
        "token_id": created["record"]["token_id"],
        "pairing_token": created["pairing_token"],
        "platform": "macos",
    }

    status, out = api.handle_post("/api/agents/bootstrap", payload, None)

    assert status == 400
    assert out["ok"] is False

    status, out = api.handle_post(
        "/api/agents/bootstrap",
        {**payload, "schema": 1},
        None,
    )

    assert status == 200
    assert out["ok"] is True


def test_bootstrap_route_rejects_non_object_body_and_boolean_schema(pairing_modules):
    api = pairing_modules["api"]
    pairing = pairing_modules["agent_pairing"]
    tunnel_catalog = pairing_modules["tunnel_catalog"]
    tunnel_catalog.save_catalog({"version": 1, "tunnels": [tunnel_payload()]})
    created = pairing.create_pairing("dedicated", "office-api", "macos")

    status, out = api.handle_post("/api/agents/bootstrap", ["not", "an", "object"], None)

    assert status == 400
    assert out["ok"] is False

    status, out = api.handle_post(
        "/api/agents/bootstrap",
        {
            "schema": True,
            "token_id": created["record"]["token_id"],
            "pairing_token": created["pairing_token"],
        },
        None,
    )

    assert status == 400
    assert out["ok"] is False

    status, out = api.handle_post(
        "/api/agents/bootstrap",
        {
            "schema": 1,
            "token_id": created["record"]["token_id"],
            "pairing_token": created["pairing_token"],
        },
        None,
    )

    assert status == 200
    assert out["ok"] is True


def test_http_bootstrap_ignores_stale_session_csrf(pairing_modules):
    http_api_routes = pairing_modules["http_api_routes"]
    pairing = pairing_modules["agent_pairing"]
    tunnel_catalog = pairing_modules["tunnel_catalog"]
    tunnel_catalog.save_catalog({"version": 1, "tunnels": [tunnel_payload()]})
    created = pairing.create_pairing("dedicated", "office-api", "macos")
    captured = {}

    class FakeHandler:
        path = "/api/agents/bootstrap"
        headers = {"Content-Type": "application/json"}

        def current_session(self):
            return {"u": "olduser", "r": "user", "role": "user", "csrf": "old-csrf"}

        def read_json_or_form(self):
            return {
                "schema": 1,
                "token_id": created["record"]["token_id"],
                "pairing_token": created["pairing_token"],
                "platform": "macos",
            }

        def respond_json(self, payload, status):
            captured["payload"] = payload
            captured["status"] = status

    http_api_routes.handle_post(FakeHandler())

    assert captured["status"] == 200
    assert captured["payload"]["ok"] is True


def test_pairing_token_is_consumed_atomically(pairing_modules, monkeypatch):
    pairing = pairing_modules["agent_pairing"]
    created = pairing.create_pairing("dedicated", "office-api", "macos")
    original_save_store = pairing.save_store
    barrier = threading.Barrier(2)

    def slow_save_store(data):
        barrier.wait(timeout=2)
        return original_save_store(data)

    monkeypatch.setattr(pairing, "save_store", slow_save_store)

    def consume_once():
        try:
            pairing.consume_pairing(created["record"]["token_id"], created["pairing_token"])
            return "ok"
        except RuntimeError as exc:
            return str(exc)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [future.result(timeout=5) for future in [pool.submit(consume_once), pool.submit(consume_once)]]

    assert results.count("ok") == 1
    assert any("used" in result for result in results)
