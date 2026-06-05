import importlib
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
BASELINE = ROOT / "baseline"
if str(BASELINE) not in sys.path:
    sys.path.insert(0, str(BASELINE))

MODULES_TO_RELOAD = [
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
    "node_display",
    "node_mutations",
    "operations_service",
    "dashboard_service",
    "api_common",
    "api_public_routes",
    "api_self_routes",
    "api_user_routes",
    "api_node_routes",
    "api_admin_routes",
    "api_payment_routes",
    "api_get_routes",
    "api_post_routes",
    "links",
    "subscription_routes",
    "xray_config_builder",
    "hy2_env_service",
    "hy2_config_builder",
    "hy2_runtime",
    "hy2_status_service",
    "api",
]


@pytest.fixture()
def app_modules(tmp_path, monkeypatch):
    panel_dir = tmp_path / "panel"
    panel_dir.mkdir()
    monkeypatch.setenv("PANEL_DIR", str(panel_dir))
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.test")
    monkeypatch.setenv("ENFORCE_USERS_CMD", "python noop.py")

    for name in MODULES_TO_RELOAD:
        if name in sys.modules:
            importlib.reload(sys.modules[name])
        else:
            importlib.import_module(name)

    import auth_store
    import user_admin

    auth = {
        "session_secret": "test-secret",
        "users": {
            "admin": {"role": "admin", "password": auth_store.make_password_hash("adminpass")},
            "viewer": {"role": "user", "password": auth_store.make_password_hash("viewerpass")},
        },
    }
    auth_store.save_auth(auth)
    monkeypatch.setattr(user_admin, "enforce_users_now", lambda: "ok")
    return {name: sys.modules[name] for name in MODULES_TO_RELOAD}


def admin_session(mods):
    return {"u": "admin", "r": "admin", "role": "admin"}


def test_api_auth_and_public_routes(app_modules):
    api = app_modules["api"]

    status, payload = api.handle_get("/api/session", None)
    assert status == 200
    assert payload["session"] is None

    status, payload = api.handle_get("/api/users", None)
    assert status == 401
    assert payload["ok"] is False

    status, payload = api.handle_post("/api/login", {"username": "admin", "password": "adminpass"}, None)
    assert status == 200
    assert payload["session"]["role"] == "admin"
    assert payload["token"]

    status, payload = api.handle_post("/api/login", {"username": "admin", "password": "wrong"}, None)
    assert status == 401


def test_user_create_and_node_assignment(app_modules):
    api = app_modules["api"]
    user_store = app_modules["user_store"]

    status, payload = api.handle_post(
        "/api/users/create",
        {"username": "alice", "days": "7", "panel_password": "password123", "traffic_gb": "5"},
        admin_session(app_modules),
    )
    assert status == 200
    users = user_store.load_users()["users"]
    assert "alice" in users
    assert users["alice"]["quota_bytes"] == 5 * 1024 * 1024 * 1024
    assert users["alice"]["sub_token"]
    assert users["alice"]["vless_node_uuids"]

    status, payload = api.handle_get("/api/users", admin_session(app_modules))
    assert status == 200
    assert any(item["username"] == "alice" for item in payload["users"])


def test_admin_can_change_user_plan_and_exact_nodes(app_modules, monkeypatch):
    api = app_modules["api"]
    user_store = app_modules["user_store"]
    node_catalog = app_modules["node_catalog"]

    monkeypatch.setattr(app_modules["operations_service"], "apply_node_exit_info", lambda node: node)
    api.handle_post(
        "/api/plans/save",
        {
            "id": "vip",
            "name": "VIP",
            "days": "60",
            "traffic_gb": "200",
            "price": "9.9",
            "node_groups": "vip",
            "sort": "30",
            "enabled": True,
        },
        admin_session(app_modules),
    )
    status, payload = api.handle_post("/api/nodes/add-vless", {}, admin_session(app_modules))
    assert status == 200
    extra_node_id = payload["node"]["id"]

    api.handle_post(
        "/api/users/create",
        {"username": "managed", "days": "7", "panel_password": "password123", "traffic_gb": "5"},
        admin_session(app_modules),
    )

    status, payload = api.handle_post(
        "/api/users/update",
        {
            "username": "managed",
            "plan_id": "vip",
            "days": "60",
            "quota_gb": "200",
            "node_ids": [extra_node_id, "hy2-main"],
            "note": "upgraded",
            "enabled": True,
        },
        admin_session(app_modules),
    )
    assert status == 200
    user = user_store.get_user("managed")
    assert user["plan_id"] == "vip"
    assert user["node_groups"] == ["vip"]
    assert user["quota_bytes"] == 200 * 1024 * 1024 * 1024
    assert user["node_ids"] == [extra_node_id, "hy2-main"]
    assert user["note"] == "upgraded"
    assert [node["id"] for node in node_catalog.nodes_for_user(user, include_disabled=False)] == [extra_node_id, "hy2-main"]
    assert payload["user"]["effective_node_ids"] == [extra_node_id, "hy2-main"]

    status, payload = api.handle_post(
        "/api/users/update",
        {"username": "managed", "plan_id": "starter", "quota_gb": "", "enabled": True},
        admin_session(app_modules),
    )
    assert status == 200
    user = user_store.get_user("managed")
    assert user["plan_id"] == "starter"
    assert user["quota_bytes"] == 100 * 1024 * 1024 * 1024

    status, payload = api.handle_post(
        "/api/users/update",
        {"username": "managed", "node_ids": "", "enabled": True},
        admin_session(app_modules),
    )
    assert status == 200
    user = user_store.get_user("managed")
    assert "node_ids" not in user
    assert payload["user"]["effective_node_ids"]
    assert "vless-main" in payload["user"]["effective_node_ids"]
    assert "hy2-main" in payload["user"]["effective_node_ids"]


def test_node_add_disable_delete_flow(app_modules, monkeypatch):
    api = app_modules["api"]
    node_catalog = app_modules["node_catalog"]

    monkeypatch.setattr(app_modules["operations_service"], "apply_node_exit_info", lambda node: {**node, "exit_ip": "203.0.113.9", "country_code": "TS"})

    status, payload = api.handle_post("/api/nodes/add-vless", {}, admin_session(app_modules))
    assert status == 200
    node_id = payload["node"]["id"]
    assert node_id.startswith("vless-auto-")
    assert payload["node"]["display_name"] == "TS - 203.0.113.9"

    status, payload = api.handle_post("/api/nodes/action", {"id": node_id, "action": "disable"}, admin_session(app_modules))
    assert status == 200
    assert node_catalog.get_node(node_id)["enabled"] is False

    status, payload = api.handle_post("/api/nodes/action", {"id": node_id, "action": "delete"}, admin_session(app_modules))
    assert status == 200
    with pytest.raises(RuntimeError):
        node_catalog.get_node(node_id)


def test_node_save_refreshes_exit_info_and_public_payload(app_modules, monkeypatch):
    api = app_modules["api"]
    node_catalog = app_modules["node_catalog"]

    def fake_exit_info(node):
        updated = dict(node)
        updated.update(
            {
                "exit_ip": "198.51.100.44",
                "country_code": "JP",
                "country": "Japan",
                "city": "Tokyo",
                "region": "JP",
                "name": "JP - 198.51.100.44",
            }
        )
        return updated

    monkeypatch.setattr(app_modules["operations_service"], "apply_node_exit_info", fake_exit_info)

    status, payload = api.handle_post(
        "/api/nodes/save",
        {
            "id": "vless-main",
            "name": "Manual Name",
            "kind": "vless",
            "outbound_mode": "direct",
            "group": "default",
            "sort": "10",
        },
        admin_session(app_modules),
    )

    assert status == 200
    assert payload["node"]["exit_ip"] == "198.51.100.44"
    assert payload["node"]["country_code"] == "JP"
    assert payload["node"]["display_name"] == "JP - 198.51.100.44"
    stored = node_catalog.get_node("vless-main")
    assert stored["exit_ip"] == "198.51.100.44"
    assert stored["country_code"] == "JP"


def test_hy2_apply_and_disable_refresh_node_payload(app_modules, monkeypatch):
    api = app_modules["api"]

    monkeypatch.setattr(
        app_modules["api_admin_routes"].hy2_panel,
        "hy2_apply_proxy",
        lambda addr, port, user, password, proxy_type: {"message": "hy2 proxy enabled"},
    )
    monkeypatch.setattr(
        app_modules["api_admin_routes"].hy2_panel,
        "hy2_disable_proxy",
        lambda: {"message": "hy2 direct"},
    )

    def fake_exit_info(node):
        updated = dict(node)
        updated.update({"exit_ip": "203.0.113.88", "country_code": "SG", "country": "Singapore", "name": "SG - 203.0.113.88"})
        return updated

    monkeypatch.setattr(app_modules["operations_service"], "apply_node_exit_info", fake_exit_info)

    status, payload = api.handle_post(
        "/api/hy2/apply",
        {"addr": "127.0.0.1", "port": "8080", "proxy_type": "http", "user": "", "password": ""},
        admin_session(app_modules),
    )
    assert status == 200
    assert payload["node"]["id"] == "hy2-main"
    assert payload["node"]["display_name"] == "SG - 203.0.113.88"

    status, payload = api.handle_post("/api/hy2/disable", {}, admin_session(app_modules))
    assert status == 200
    assert payload["node"]["id"] == "hy2-main"


def test_hy2_status_parses_http_and_socks5_proxy_endpoint(app_modules, tmp_path, monkeypatch):
    hy2_status_service = app_modules["hy2_status_service"]

    env_file = tmp_path / "hy2.env"
    env_file.write_text("HY_DOMAIN=hy.example.test\nHY_PASSWORD=secret\nHY_PORT=8443\n", encoding="utf-8")
    config_file = tmp_path / "hy2.yaml"
    monkeypatch.setattr(app_modules["hy2_env_service"], "HY2_ENV_FILE", env_file)
    monkeypatch.setattr(hy2_status_service, "HY2_CONFIG_FILE", config_file)
    monkeypatch.setattr(hy2_status_service, "run_shell", lambda cmd, timeout=15: (0, 'running"\n'))

    config_file.write_text(
        "\n".join(
            [
                "outbounds:",
                "  - name: http-proxy",
                "    type: http",
                "    http:",
                "      url: http://u:p@198.51.100.10:8080",
            ]
        ),
        encoding="utf-8",
    )
    assert hy2_status_service.outbound_mode() == "http"
    assert hy2_status_service.proxy_endpoint() == {
        "addr": "198.51.100.10",
        "port": 8080,
        "user": "u",
        "password": "p",
        "type": "http",
    }
    status = hy2_status_service.status()
    assert status["proxy"] == "http://u:p@198.51.100.10:8080"
    assert status["running"] == "running"

    config_file.write_text(
        "\n".join(
            [
                "outbounds:",
                "  - name: socks5-proxy",
                "    type: socks5",
                "    socks5:",
                "      addr: 203.0.113.20:1080",
                "      username: alice",
                "      password: secret-pass",
            ]
        ),
        encoding="utf-8",
    )
    assert hy2_status_service.outbound_mode() == "socks5"
    assert hy2_status_service.proxy_endpoint() == {
        "addr": "203.0.113.20",
        "port": 1080,
        "user": "alice",
        "password": "secret-pass",
        "type": "socks5",
    }
    assert hy2_status_service.status()["proxy"] == "socks5://alice:secret-pass@203.0.113.20:1080"


def test_hy2_exit_refresh_preserves_proxy_mode(app_modules, monkeypatch):
    node_exit_service = importlib.import_module("node_exit_service")

    monkeypatch.setattr(node_exit_service.hy2_panel, "hy2_outbound_mode", lambda: "socks5")
    monkeypatch.setattr(
        node_exit_service.hy2_panel,
        "hy2_proxy_endpoint",
        lambda: {"addr": "127.0.0.1", "port": 1080, "user": "", "password": "", "type": "socks5"},
    )
    monkeypatch.setattr(
        node_exit_service.geo_utils,
        "proxy_exit_info",
        lambda addr, port, user, password, proxy_type: {"ip": "203.0.113.9", "country_code": "US", "country": "United States"},
    )

    node = node_exit_service.apply_node_exit_info({"id": "hy2-main", "name": "Hysteria2", "kind": "hy2"})

    assert node["outbound_mode"] == "socks5"
    assert node["exit_ip"] == "203.0.113.9"
    assert node["country_code"] == "US"


def test_http_api_get_converts_exceptions_to_json_errors(app_modules, monkeypatch):
    http_api_routes = importlib.import_module("http_api_routes")
    captured = {}

    class FakeHandler:
        path = "/api/dashboard"

        def current_session(self):
            return admin_session(app_modules)

        def respond_json(self, payload, status):
            captured["payload"] = payload
            captured["status"] = status

    def raise_boom(path, session):
        raise RuntimeError("boom")

    monkeypatch.setattr(http_api_routes.api, "handle_get", raise_boom)
    http_api_routes.handle_get(FakeHandler())

    assert captured["status"] == 400
    assert captured["payload"]["ok"] is False
    assert captured["payload"]["error"] == "boom"


def test_admin_can_manage_plans(app_modules):
    api = app_modules["api"]
    plans_store = app_modules["plans_store"]

    status, payload = api.handle_post(
        "/api/plans/save",
        {
            "id": "pro-plan",
            "name": "Pro Plan",
            "days": "45",
            "traffic_gb": "512",
            "price": "19.9",
            "node_groups": "default,sg",
            "sort": "30",
            "enabled": True,
        },
        admin_session(app_modules),
    )
    assert status == 200
    assert payload["plan"]["id"] == "pro-plan"
    assert plans_store.get_plan("pro-plan")["price"] == 19.9

    status, payload = api.handle_post(
        "/api/plans/action",
        {"id": "pro-plan", "action": "disable"},
        admin_session(app_modules),
    )
    assert status == 200
    assert plans_store.get_plan("pro-plan")["enabled"] is False

    status, payload = api.handle_post(
        "/api/plans/action",
        {"id": "pro-plan", "action": "enable"},
        admin_session(app_modules),
    )
    assert status == 200
    assert plans_store.get_plan("pro-plan")["enabled"] is True

    status, payload = api.handle_post(
        "/api/plans/action",
        {"id": "pro-plan", "action": "delete"},
        admin_session(app_modules),
    )
    assert status == 200
    assert plans_store.get_plan("pro-plan") is None


def test_non_admin_cannot_manage_plans(app_modules):
    api = app_modules["api"]
    session = {"u": "viewer", "r": "user", "role": "user"}

    status, payload = api.handle_post(
        "/api/plans/save",
        {"id": "bad-plan", "name": "Bad", "days": "30", "traffic_gb": "1", "price": "1"},
        session,
    )
    assert status == 403

    status, payload = api.handle_post(
        "/api/plans/action",
        {"id": "starter", "action": "disable"},
        session,
    )
    assert status == 403


def test_subscription_urls_are_configured(app_modules):
    app_urls = app_modules["app_urls"]
    assert app_urls.subscription_url("tok") == "https://example.test/sub/tok"
    assert app_urls.subscription_url("tok", "mihomo") == "https://example.test/sub/tok/mihomo"
    assert app_urls.subscription_qr_path("tok", "raw") == "/qrsub/tok/raw"


def test_subscription_base64_raw_and_mihomo(app_modules, monkeypatch):
    api = app_modules["api"]
    user_store = app_modules["user_store"]
    links = app_modules["links"]

    api.handle_post(
        "/api/users/create",
        {"username": "subuser", "days": "7", "panel_password": "password123", "traffic_gb": "5"},
        admin_session(app_modules),
    )
    user = user_store.get_user("subuser")
    token = user["sub_token"]
    monkeypatch.setattr(links, "build_vless_links_for_airport_user", lambda username, user: ["vless://uuid@example:443?security=reality#Test"])
    monkeypatch.setattr(links, "build_hy2_link_for_airport_user", lambda username, user: "hysteria2://u:p@example:443/?sni=example#HY2")
    monkeypatch.setattr(
        links,
        "vless_reality_params",
        lambda: ({"vless_address": "example.test", "vless_port": 443}, {}, "sni.example", "sid", "public-key", ""),
    )

    body, headers = links.build_subscription_response_by_path(f"/sub/{token}")
    assert "Subscription-Userinfo" in headers
    assert "dmxlc3M6Ly91dWlk" in body

    raw, raw_headers = links.build_subscription_response_by_path(f"/sub/{token}/raw")
    assert raw.startswith("vless://")
    assert "hysteria2://" in raw

    mihomo, mihomo_headers = links.build_subscription_response_by_path(f"/sub/{token}/mihomo")
    assert "proxies:" in mihomo
    assert "proxy-groups:" in mihomo


def test_user_disabled_expired_and_quota_exhausted(app_modules):
    api = app_modules["api"]
    user_store = app_modules["user_store"]

    api.handle_post(
        "/api/users/create",
        {"username": "limited", "days": "1", "panel_password": "password123", "traffic_gb": "1"},
        admin_session(app_modules),
    )
    api.handle_post("/api/users/action", {"username": "limited", "action": "disable"}, admin_session(app_modules))
    user = user_store.get_user("limited")
    assert user_store.user_is_active("limited", user) is False

    data = user_store.load_users()
    user = data["users"]["limited"]
    user["enabled"] = True
    user["expires_at"] = "2000-01-01T00:00:00+00:00"
    user_store.save_users(data)
    assert user_store.user_is_active("limited", user_store.get_user("limited")) is False

    data = user_store.load_users()
    user = data["users"]["limited"]
    user["expires_at"] = user_store.make_expiry(1)
    user["quota_bytes"] = 100
    user["used_bytes"] = 100
    user["quota_exceeded"] = True
    user_store.save_users(data)
    assert user_store.user_is_active("limited", user_store.get_user("limited")) is False


def test_xray_config_generation(app_modules):
    xray_config_builder = app_modules["xray_config_builder"]
    cfg = {
        "inbounds": [{"tag": "vless-reality-in", "settings": {}, "streamSettings": {}}],
        "outbounds": [{"tag": "direct", "protocol": "freedom"}, {"tag": "block", "protocol": "blackhole"}],
        "routing": {"rules": []},
    }
    proxy_cfg = xray_config_builder.build_proxy_config(cfg, "1.2.3.4", 8080, "u", "p", "socks5")
    out = proxy_cfg["outbounds"][0]
    assert out["tag"] == "webshare-out"
    assert out["protocol"] == "socks"
    assert out["settings"]["servers"][0]["users"][0]["user"] == "u"
    assert any(rule.get("outboundTag") == "webshare-out" for rule in proxy_cfg["routing"]["rules"])

    direct_cfg = xray_config_builder.build_direct_config(proxy_cfg)
    assert not any(out.get("tag") == "webshare-out" for out in direct_cfg["outbounds"])
    assert direct_cfg["routing"]["rules"][-1]["outboundTag"] == "direct"


def test_hy2_config_generation_and_validation(app_modules, tmp_path, monkeypatch):
    hy2_config_builder = app_modules["hy2_config_builder"]
    hy2_runtime = app_modules["hy2_runtime"]
    env_file = tmp_path / "hy2.env"
    env_file.write_text("HY_DOMAIN=hy.example.test\nHY_PASSWORD=secret\n", encoding="utf-8")
    secret_file = tmp_path / "hy2-secret.txt"
    monkeypatch.setattr(app_modules["hy2_env_service"], "HY2_ENV_FILE", env_file)
    monkeypatch.setattr(app_modules["hy2_env_service"], "HY2_TRAFFIC_SECRET_FILE", secret_file)

    direct = hy2_config_builder.build_config("direct")
    assert "listen: :443" in direct
    assert "type: direct" in direct
    assert hy2_runtime.validate_config_text(direct) is True

    proxied = hy2_config_builder.build_config("http", "1.2.3.4", "8080", "u", "p", "http")
    assert "type: http" in proxied
    assert "http://u:p@1.2.3.4:8080" in proxied

    env_file.write_text("HY_DOMAIN=hy.example.test\nHY_PASSWORD=secret\nHY_PORT=8443\n", encoding="utf-8")
    custom_port = hy2_config_builder.build_config("direct")
    assert "listen: :8443" in custom_port


def test_qr_png_generation():
    import qr_service

    raw = qr_service.qr_png_for_link("vless://example")
    assert raw.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(raw) > 100


def test_backup_export_and_restore_round_trip(app_modules):
    api = app_modules["api"]
    backup_manager = app_modules["backup_manager"]
    user_store = app_modules["user_store"]
    user_admin = importlib.import_module("user_admin")
    sync_calls = []
    user_admin.enforce_users_now = lambda: sync_calls.append("sync") or "ok"

    api.handle_post(
        "/api/users/create",
        {"username": "before", "days": "7", "panel_password": "password123", "traffic_gb": "5"},
        admin_session(app_modules),
    )
    backup = backup_manager.create_backup("round-trip")

    api.handle_post(
        "/api/users/create",
        {"username": "after", "days": "7", "panel_password": "password123", "traffic_gb": "5"},
        admin_session(app_modules),
    )
    assert "after" in user_store.load_users()["users"]

    exported = backup_manager.read_backup_bytes(backup["name"])
    assert exported.startswith(b"\x1f\x8b")

    restored = backup_manager.restore_backup_archive(exported, operator="admin")
    assert restored["restored"]["name"] == backup["name"]
    users = user_store.load_users()["users"]
    assert "before" in users
    assert "after" not in users

    status, payload = api.handle_get(f"/api/backups/download?name={backup['name']}", admin_session(app_modules))
    assert status == 200
    assert payload["filename"] == backup["name"]
    assert payload["content"].startswith(b"\x1f\x8b")

    status, payload = api.handle_post(
        "/api/backups/upload",
        {"filename": backup["name"], "content_b64": __import__("base64").b64encode(exported).decode()},
        admin_session(app_modules),
    )
    assert status == 200
    assert sync_calls
