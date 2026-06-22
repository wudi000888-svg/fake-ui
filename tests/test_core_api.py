import importlib
import json
import pathlib
import sys
import tarfile
from datetime import timedelta
from io import BytesIO

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
    "security",
    "payment_wallets",
    "payment_verifier",
    "payment_service",
    "registration_store",
    "public_settings",
    "email_settings",
    "email_service",
    "password_reset_service",
    "admin_profile",
    "audit_log",
    "backup_manager",
    "subscription_guard",
    "app_urls",
    "link_settings",
    "user_stats_service",
    "user_admin",
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
    "tunnel_config_builder",
    "tunnel_catalog",
    "tunnel_domains",
    "api_tunnel_routes",
    "api",
]


@pytest.fixture()
def app_modules(tmp_path, monkeypatch):
    panel_dir = tmp_path / "panel"
    panel_dir.mkdir()
    hy2_dir = tmp_path / "hysteria2"
    hy2_dir.mkdir()
    hy2_env_file = hy2_dir / ".env"
    hy2_config_file = hy2_dir / "server.yaml"
    hy2_env_file.write_text("HY_DOMAIN=hy.example.test\nHY_PASSWORD=secret\nHY_PORT=443\n", encoding="utf-8")
    hy2_config_file.write_text(
        "listen: :443\noutbounds:\n  - name: direct\n    type: direct\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PANEL_DIR", str(panel_dir))
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.test")
    monkeypatch.setenv("ENFORCE_USERS_CMD", "python noop.py")
    monkeypatch.setenv("AIRPORT_LOGIN_LOG", str(tmp_path / "airport-users.log"))
    monkeypatch.setenv("HY2_ENV_FILE", str(hy2_env_file))
    monkeypatch.setenv("HY2_CONFIG_FILE", str(hy2_config_file))

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
    api_tunnel_routes = sys.modules["api_tunnel_routes"]
    default_xray_config = {
        "inbounds": [
            {
                "tag": "vless-reality-in",
                "listen": "0.0.0.0",
                "port": 8443,
                "protocol": "vless",
                "settings": {"clients": [], "decryption": "none"},
                "streamSettings": {
                    "network": "tcp",
                    "security": "reality",
                    "realitySettings": {
                        "dest": "www.cloudflare.com:443",
                        "serverNames": ["www.cloudflare.com"],
                        "publicKey": "server-public-key",
                        "privateKey": "server-private-key",
                        "shortIds": ["0123456789abcdef"],
                    },
                },
            }
        ],
        "outbounds": [{"tag": "direct", "protocol": "freedom"}],
        "routing": {"rules": []},
    }
    monkeypatch.setattr(api_tunnel_routes.xray_runtime, "load_config", lambda: json.loads(json.dumps(default_xray_config)))
    monkeypatch.setattr(api_tunnel_routes.xray_runtime, "write_and_restart_xray", lambda cfg: "backup")
    monkeypatch.setattr(
        api_tunnel_routes.tunnel_nginx,
        "apply_native_nginx",
        lambda tunnels: {"domains": [item.get("public_domain") for item in tunnels if item.get("public_domain")]},
    )
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


def test_admin_app_shell_includes_tunnel_nav(app_modules):
    api = app_modules["api"]

    status, payload = api.handle_get("/api/app-shell", admin_session(app_modules))

    assert status == 200
    assert {"id": "tunnels", "label": "内网穿透", "icon": "⇄"} in payload["nav"]


def test_public_registration_is_disabled_by_default(app_modules):
    api = app_modules["api"]

    status, payload = api.handle_post(
        "/api/register",
        {"username": "newbie", "password": "password123", "email": "n@example.test"},
        None,
    )

    assert status == 403
    assert payload["ok"] is False


def test_enabled_public_registration_creates_no_plan_user_and_logs_in(app_modules):
    api = app_modules["api"]
    user_store = app_modules["user_store"]
    ops = app_modules["operations_service"]

    ops.update_public_settings({"registration_enabled": True})

    status, payload = api.handle_post(
        "/api/register",
        {"username": "newbie", "password": "password123", "email": "n@example.test"},
        None,
    )

    assert status == 200
    assert "session" not in payload
    assert "token" not in payload
    assert payload["message"] == "registration complete; please log in"
    user = user_store.get_user("newbie")
    assert user["plan_id"] == ""
    assert user["node_groups"] == []
    assert user["node_ids"] == []
    assert user["quota_bytes"] == 0
    assert user["expires_at"] == ""
    assert user["email"] == "n@example.test"

    status, session_payload = api.handle_get("/api/session", {"u": "newbie", "r": "user", "role": "user", "csrf": "csrf"})
    assert status == 200
    assert session_payload["session"]["username"] == "newbie"


def test_admin_email_settings_do_not_return_smtp_password(app_modules, monkeypatch):
    api = app_modules["api"]
    monkeypatch.setattr(app_modules["dashboard_service"].xray_panel, "current_status", lambda: {"proxy": ""})
    monkeypatch.setattr(app_modules["dashboard_service"].hy2_panel, "hy2_status", lambda: {})

    status, payload = api.handle_post(
        "/api/email-settings",
        {
            "password_reset_enabled": True,
            "email_provider": "smtp",
            "smtp_host": "smtp.example.test",
            "smtp_port": "587",
            "smtp_username": "mailer",
            "smtp_password": "smtp-secret",
            "smtp_from": "noreply@example.test",
            "smtp_tls": True,
        },
        admin_session(app_modules),
    )

    assert status == 200
    assert payload["email_settings"]["smtp_configured"] is True
    assert "smtp_password" not in json.dumps(payload)

    status, dashboard = api.handle_get("/api/dashboard", admin_session(app_modules))
    assert status == 200
    assert dashboard["data"]["public_settings"]["password_reset_enabled"] is True
    assert dashboard["data"]["email_settings"]["smtp_host"] == "smtp.example.test"
    assert "smtp_password" not in json.dumps(dashboard)


def test_user_can_update_own_email(app_modules):
    api = app_modules["api"]
    user_admin = app_modules["user_admin"]
    user_store = app_modules["user_store"]

    user_admin.create_airport_user("mailuser", "30", panel_password_input="password123", traffic_gb_input="1")

    status, payload = api.handle_post(
        "/api/self/email",
        {"email": "mailuser@example.test"},
        {"u": "mailuser", "r": "user", "role": "user"},
    )

    assert status == 200
    assert payload["profile"]["email"] == "mailuser@example.test"
    assert user_store.get_user("mailuser")["email"] == "mailuser@example.test"


def test_user_can_change_own_password_with_current_password(app_modules):
    api = app_modules["api"]
    auth_store = app_modules["auth_store"]
    user_admin = app_modules["user_admin"]
    user_store = app_modules["user_store"]

    user_admin.create_airport_user("pwuser", "30", panel_password_input="oldpass123", traffic_gb_input="1")

    status, payload = api.handle_post(
        "/api/self/password",
        {"old_password": "wrongpass", "new_password": "newpass123"},
        {"u": "pwuser", "r": "user", "role": "user"},
    )

    assert status == 400
    assert payload["ok"] is False
    assert auth_store.authenticate_user("pwuser", "oldpass123") == "user"

    status, payload = api.handle_post(
        "/api/self/password",
        {"old_password": "oldpass123", "new_password": "newpass123"},
        {"u": "pwuser", "r": "user", "role": "user"},
    )

    assert status == 200
    assert payload["message"] == "password updated"
    saved = user_store.get_user("pwuser")["panel_password"]
    assert saved["alg"] == "pbkdf2_sha256"
    assert saved["iter"] == 260000
    assert auth_store.authenticate_user("pwuser", "oldpass123") is None
    assert auth_store.authenticate_user("pwuser", "newpass123") == "user"


def test_admin_can_change_own_password_from_self_endpoint(app_modules):
    api = app_modules["api"]
    auth_store = app_modules["auth_store"]

    status, payload = api.handle_post(
        "/api/self/password",
        {"old_password": "adminpass", "new_password": "newadminpass123"},
        admin_session(app_modules),
    )

    assert status == 200
    assert payload["message"] == "password updated"
    saved = auth_store.load_auth()["users"]["admin"]["password"]
    assert saved["alg"] == "pbkdf2_sha256"
    assert saved["iter"] == 260000
    assert auth_store.authenticate_user("admin", "adminpass") is None
    assert auth_store.authenticate_user("admin", "newadminpass123") == "admin"


def test_password_reset_email_code_flow(app_modules, monkeypatch):
    api = app_modules["api"]
    ops = app_modules["operations_service"]
    user_admin = app_modules["user_admin"]
    auth_store = app_modules["auth_store"]
    registration_store = app_modules["registration_store"]
    password_reset_service = app_modules["password_reset_service"]
    sent = []

    user_admin.create_airport_user("resetme", "30", panel_password_input="oldpass123", traffic_gb_input="1")
    user_admin.update_user_email("resetme", "resetme@example.test")
    ops.update_public_settings({"password_reset_enabled": True})
    ops.update_email_settings(
        {
            "email_provider": "smtp",
            "smtp_host": "smtp.example.test",
            "smtp_password": "smtp-secret",
            "smtp_from": "noreply@example.test",
        }
    )
    monkeypatch.setattr(password_reset_service, "generate_code", lambda: "123456")
    monkeypatch.setattr(password_reset_service.email_service, "send_verification_code", lambda email, code: sent.append((email, code)))

    status, payload = api.handle_post("/api/password-reset/send-code", {"username": "resetme"}, None)

    assert status == 200
    assert payload["message"] == "verification code sent"
    assert sent == [("resetme@example.test", "123456")]
    reset = registration_store.list_resets()[0]
    assert reset["email"] == "resetme@example.test"
    assert reset["code_hash"] != "123456"
    assert "code" not in reset

    status, bad = api.handle_post(
        "/api/password-reset/confirm",
        {"username": "resetme", "code": "000000", "new_password": "newpass123"},
        None,
    )
    assert status == 400
    assert bad["ok"] is False
    assert registration_store.list_resets()[0]["attempts"] == 1

    status, payload = api.handle_post(
        "/api/password-reset/confirm",
        {"username": "resetme", "code": "123456", "new_password": "newpass123"},
        None,
    )
    assert status == 200
    assert payload["message"] == "password reset complete"
    assert auth_store.authenticate_user("resetme", "newpass123") == "user"
    assert registration_store.list_resets()[0]["status"] == "consumed"


def test_password_reset_disabled_blocks_request(app_modules):
    api = app_modules["api"]
    registration_store = app_modules["registration_store"]

    status, payload = api.handle_post("/api/password-reset/send-code", {"username": "resetme"}, None)

    assert status == 403
    assert payload["ok"] is False

    status, payload = api.handle_post("/api/password-reset/request", {"username": "resetme"}, None)

    assert status == 401
    assert payload["ok"] is False
    assert registration_store.list_resets() == []


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


def test_admin_can_delete_user_from_sqlite_store(app_modules):
    api = app_modules["api"]
    user_store = app_modules["user_store"]

    status, payload = api.handle_post(
        "/api/users/create",
        {"username": "delete_me", "days": "7", "panel_password": "password123", "traffic_gb": "1"},
        admin_session(app_modules),
    )
    assert status == 200
    assert user_store.get_user("delete_me")

    status, payload = api.handle_post(
        "/api/users/action",
        {"username": "delete_me", "action": "delete"},
        admin_session(app_modules),
    )

    assert status == 200
    assert user_store.get_user("delete_me") is None
    assert not any(item["username"] == "delete_me" for item in payload["users"])


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


def test_new_plan_order_replaces_existing_subscription(app_modules, monkeypatch):
    user_admin = app_modules["user_admin"]
    user_store = app_modules["user_store"]
    plans_store = app_modules["plans_store"]
    orders_store = app_modules["orders_store"]
    monkeypatch.setattr(user_admin, "get_xray_user_stat_snapshot", lambda username: {"uplink": 0, "downlink": 0})
    monkeypatch.setattr(user_admin, "get_hy2_user_stat_snapshot", lambda username, user=None: {"tx": 0, "rx": 0})

    starter = plans_store.upsert_plan(
        {
            "id": "starter-replace",
            "name": "Starter Replace",
            "days": "30",
            "traffic_gb": "100",
            "price": "9",
            "node_groups": "default",
        }
    )
    vip = plans_store.upsert_plan(
        {
            "id": "vip-replace",
            "name": "VIP Replace",
            "days": "10",
            "traffic_gb": "200",
            "price": "19",
            "node_groups": "vip",
        }
    )
    user_admin.create_airport_user(
        "replace_me",
        starter["days"],
        panel_password_input="password123",
        traffic_gb_input=starter["traffic_gb"],
        plan_id=starter["id"],
    )
    users = user_store.load_users()
    old_exp = (user_store.now_utc() + timedelta(days=90)).isoformat()
    users["users"]["replace_me"].update(
        {
            "expires_at": old_exp,
            "used_bytes": 50 * 1024 * 1024 * 1024,
            "quota_exceeded": True,
            "node_ids": ["vless-main"],
        }
    )
    user_store.save_users(users)

    order = orders_store.create_pending_order("replace_me", "new", vip)
    result = user_admin.confirm_order(order["id"], operator="admin")
    user = user_store.get_user("replace_me")
    new_exp = user_store.parse_time(user["expires_at"])
    days_left = (new_exp - user_store.now_utc()).total_seconds() / 86400

    assert result["mode"] == "replace"
    assert user["plan_id"] == "vip-replace"
    assert user["node_groups"] == ["vip"]
    assert "node_ids" not in user
    assert user["quota_bytes"] == 200 * 1024 * 1024 * 1024
    assert user["used_bytes"] == 0
    assert user["quota_exceeded"] is False
    assert 9 <= days_left <= 10


def test_renew_order_extends_existing_subscription(app_modules):
    user_admin = app_modules["user_admin"]
    user_store = app_modules["user_store"]
    plans_store = app_modules["plans_store"]
    orders_store = app_modules["orders_store"]

    plan = plans_store.upsert_plan(
        {
            "id": "renew-same",
            "name": "Renew Same",
            "days": "30",
            "traffic_gb": "100",
            "price": "9",
            "node_groups": "default",
        }
    )
    user_admin.create_airport_user(
        "renew_me",
        plan["days"],
        panel_password_input="password123",
        traffic_gb_input=plan["traffic_gb"],
        plan_id=plan["id"],
    )
    users = user_store.load_users()
    base_exp = user_store.now_utc() + timedelta(days=20)
    users["users"]["renew_me"]["expires_at"] = base_exp.isoformat()
    user_store.save_users(users)

    order = orders_store.create_pending_order("renew_me", "renew", plan)
    result = user_admin.confirm_order(order["id"], operator="admin")
    user = user_store.get_user("renew_me")
    new_exp = user_store.parse_time(user["expires_at"])

    assert result["mode"] == "renew"
    assert (new_exp - base_exp).total_seconds() / 86400 >= 29


def test_user_checkout_different_plan_creates_new_order_kind(app_modules):
    api = app_modules["api"]
    user_admin = app_modules["user_admin"]
    plans_store = app_modules["plans_store"]

    starter = plans_store.upsert_plan(
        {"id": "starter-checkout", "name": "Starter Checkout", "days": "30", "traffic_gb": "100", "price": "9"}
    )
    vip = plans_store.upsert_plan(
        {"id": "vip-checkout", "name": "VIP Checkout", "days": "30", "traffic_gb": "200", "price": "19"}
    )
    user_admin.create_airport_user(
        "checkout_me",
        starter["days"],
        panel_password_input="password123",
        traffic_gb_input=starter["traffic_gb"],
        plan_id=starter["id"],
    )

    status, payload = api.handle_post(
        "/api/orders/create",
        {"plan_id": vip["id"], "kind": "renew"},
        {"u": "checkout_me", "r": "user", "role": "user"},
    )

    assert status == 200
    assert payload["order"]["kind"] == "new"


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


def test_admin_can_save_tunnel_node_and_export_bridge_config(app_modules, monkeypatch):
    api = app_modules["api"]
    monkeypatch.setattr(app_modules["dashboard_service"].xray_panel, "current_status", lambda: {"proxy": "127.0.0.1:8443"})
    monkeypatch.setattr(app_modules["dashboard_service"].hy2_panel, "hy2_status", lambda: {})
    monkeypatch.setattr(
        app_modules["api_tunnel_routes"].xray_runtime,
        "load_config",
        lambda: {
            "inbounds": [
                {
                    "tag": "vless-reality-in",
                    "listen": "0.0.0.0",
                    "port": 8443,
                    "protocol": "vless",
                    "settings": {"clients": [], "decryption": "none"},
                    "streamSettings": {
                        "network": "tcp",
                        "security": "reality",
                        "realitySettings": {
                            "dest": "www.cloudflare.com:443",
                            "serverNames": ["www.cloudflare.com"],
                            "privateKey": "server-private-key",
                            "shortIds": ["0123456789abcdef"],
                        },
                    },
                }
            ],
            "outbounds": [{"tag": "direct", "protocol": "freedom"}],
            "routing": {"rules": []},
        },
    )

    status, payload = api.handle_post(
        "/api/tunnels/save",
        {
            "id": "macmini",
            "name": "Mac mini SSH",
            "portal_port": "2222",
            "target_host": "127.0.0.1",
            "target_port": "22",
            "client_id": "11111111-1111-4111-8111-111111111111",
            "reality_sni": "www.cloudflare.com",
            "server_address": "vless.example.com",
            "server_port": "443",
            "public_key": "server-public-key",
            "short_id": "0123456789abcdef",
            "flow": "   ",
        },
        admin_session(app_modules),
    )

    assert status == 200
    assert payload["tunnel"]["id"] == "macmini"
    assert payload["tunnel"]["portal_port"] == 2222
    assert payload["tunnel"]["target_port"] == 22
    assert payload["tunnel"]["flow"] == "xtls-rprx-vision"

    status, payload = api.handle_get("/api/tunnels", admin_session(app_modules))
    assert status == 200
    assert payload["tunnels"][0]["id"] == "macmini"
    assert payload["tunnels"][0]["display_name"] == "Mac mini SSH"

    status, payload = api.handle_get("/api/dashboard", admin_session(app_modules))
    assert status == 200
    assert payload["data"]["tunnels"][0]["id"] == "macmini"

    status, payload = api.handle_get("/api/tunnels/macmini/bridge-config", admin_session(app_modules))
    assert status == 200
    assert payload["filename"] == "macmini-xray-bridge.json"
    cfg = payload["config"]
    reverse = next(item for item in cfg["outbounds"] if item.get("tag") == "tunnel-reverse-out")
    assert reverse["settings"]["address"] == "vless.example.com"
    assert reverse["streamSettings"]["realitySettings"]["serverName"] == "www.cloudflare.com"
    local = next(item for item in cfg["outbounds"] if item.get("tag") == "tunnel-local-service")
    assert local["settings"]["redirect"] == "127.0.0.1:22"

    status, payload = api.handle_get("/api/tunnels/portal-config", admin_session(app_modules))
    assert status == 200
    portal_cfg = payload["config"]
    vless = next(item for item in portal_cfg["inbounds"] if item.get("tag") == "vless-reality-in")
    assert vless["settings"]["clients"][0]["reverse"] == {"tag": "tunnel-reverse-macmini"}
    assert next(item for item in portal_cfg["inbounds"] if item.get("tag") == "tunnel-portal-macmini")["port"] == 2222


def test_admin_can_save_generic_domain_tunnel_and_export_macos_bundle(app_modules, monkeypatch):
    api = app_modules["api"]
    monkeypatch.setattr(
        app_modules["api_tunnel_routes"].xray_runtime,
        "load_config",
        lambda: {
            "inbounds": [
                {
                    "tag": "vless-reality-in",
                    "listen": "0.0.0.0",
                    "port": 8443,
                    "protocol": "vless",
                    "settings": {
                        "clients": [
                            {"id": "22222222-2222-4222-8222-222222222222", "email": "panel-user:alice"}
                        ],
                        "decryption": "none",
                    },
                    "streamSettings": {
                        "network": "tcp",
                        "security": "reality",
                        "realitySettings": {
                            "dest": "www.cloudflare.com:443",
                            "serverNames": ["www.cloudflare.com"],
                            "publicKey": "server-public-key",
                            "privateKey": "server-private-key",
                            "shortIds": ["0123456789abcdef"],
                        },
                    },
                }
            ],
            "outbounds": [{"tag": "direct", "protocol": "freedom"}],
            "routing": {"rules": []},
        },
    )

    status, payload = api.handle_post(
        "/api/tunnels/save",
        {
            "public_domain": "New.Example.COM",
            "name": "New service",
            "target_port": "3000",
        },
        admin_session(app_modules),
    )

    assert status == 200
    tunnel = payload["tunnel"]
    assert tunnel["id"] == "new-example-com"
    assert tunnel["public_domain"] == "new.example.com"
    assert tunnel["portal_port"] == 18081
    assert tunnel["server_address"] == "new.example.com"
    assert tunnel["public_key"] == "server-public-key"
    assert tunnel["short_id"] == "0123456789abcdef"
    assert tunnel["client_id"] != "22222222-2222-4222-8222-222222222222"

    status, bundle = api.handle_get("/api/tunnels/new-example-com/macos-bundle", admin_session(app_modules))
    assert status == 200
    assert bundle["filename"] == "new-example-com-macos-bridge.tgz"
    assert bundle["content_type"] == "application/gzip"
    assert isinstance(bundle["content"], bytes)


def test_tunnel_api_exposes_only_resolved_non_reserved_domain_options(app_modules, monkeypatch):
    api = app_modules["api"]
    domains = app_modules["tunnel_domains"]

    monkeypatch.setenv("PANEL_DOMAIN", "panel.example.test")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://panel.example.test")
    monkeypatch.setenv("TUNNEL_DOMAIN_CANDIDATES", "ready.example.test,panel.example.test,node.example.test,wrong.example.test")
    monkeypatch.setenv("TUNNEL_SERVER_IPS", "203.0.113.10")
    monkeypatch.setattr(
        app_modules["api_tunnel_routes"].link_settings,
        "read",
        lambda: {"vless_address": "node.example.test", "vless_port": 443},
    )
    monkeypatch.setattr(domains, "resolve_ips", lambda domain: {
        "ready.example.test": ["203.0.113.10"],
        "panel.example.test": ["203.0.113.10"],
        "node.example.test": ["203.0.113.10"],
        "wrong.example.test": ["198.51.100.99"],
    }.get(domain, []))

    status, payload = api.handle_get("/api/tunnels", admin_session(app_modules))

    assert status == 200
    assert [item["domain"] for item in payload["domain_options"]["available"]] == ["ready.example.test"]
    hidden = {item["domain"]: item["reason"] for item in payload["domain_options"]["unavailable"]}
    assert hidden["panel.example.test"] == "reserved_panel_domain"
    assert hidden["node.example.test"] == "reserved_node_domain"
    assert hidden["wrong.example.test"] == "not_resolved_to_server"


def test_tunnel_save_rejects_public_domain_not_resolved_to_server(app_modules, monkeypatch):
    api = app_modules["api"]
    domains = app_modules["tunnel_domains"]

    monkeypatch.setenv("TUNNEL_SERVER_IPS", "203.0.113.10")
    monkeypatch.setattr(domains, "resolve_ips", lambda domain: ["198.51.100.99"])
    monkeypatch.setattr(
        app_modules["api_tunnel_routes"].xray_runtime,
        "load_config",
        lambda: {
            "inbounds": [
                {
                    "tag": "vless-reality-in",
                    "port": 8443,
                    "settings": {"clients": [], "decryption": "none"},
                    "streamSettings": {
                        "security": "reality",
                        "realitySettings": {
                            "serverNames": ["www.cloudflare.com"],
                            "publicKey": "server-public-key",
                            "privateKey": "server-private-key",
                            "shortIds": ["0123456789abcdef"],
                        },
                    },
                }
            ],
            "outbounds": [{"tag": "direct", "protocol": "freedom"}],
            "routing": {"rules": []},
        },
    )

    status, payload = api.handle_post(
        "/api/tunnels/save",
        {"public_domain": "wrong.example.test", "name": "Wrong", "target_port": "3000"},
        admin_session(app_modules),
    )

    assert status == 400
    assert "must resolve to this server" in payload["error"]


def test_tunnel_save_rejects_panel_or_proxy_node_domain(app_modules, monkeypatch):
    api = app_modules["api"]
    domains = app_modules["tunnel_domains"]

    monkeypatch.setenv("PANEL_DOMAIN", "panel.example.test")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://panel.example.test")
    monkeypatch.setenv("TUNNEL_SERVER_IPS", "203.0.113.10")
    monkeypatch.setattr(
        app_modules["api_tunnel_routes"].link_settings,
        "read",
        lambda: {"vless_address": "node.example.test", "vless_port": 443},
    )
    monkeypatch.setattr(domains, "resolve_ips", lambda domain: ["203.0.113.10"])

    for public_domain, reason in [
        ("panel.example.test", "reserved for the panel"),
        ("node.example.test", "reserved for a proxy node"),
    ]:
        status, payload = api.handle_post(
            "/api/tunnels/save",
            {"public_domain": public_domain, "name": public_domain, "target_port": "3000"},
            admin_session(app_modules),
        )
        assert status == 400
        assert reason in payload["error"]


def test_tunnel_save_rejects_hy2_domain(app_modules, monkeypatch):
    api = app_modules["api"]
    domains = app_modules["tunnel_domains"]

    monkeypatch.setenv("HY2_DOMAIN", "hy.example.test")
    monkeypatch.setenv("TUNNEL_SERVER_IPS", "203.0.113.10")
    monkeypatch.setattr(domains, "resolve_ips", lambda domain: ["203.0.113.10"])
    monkeypatch.setattr(
        app_modules["api_tunnel_routes"].xray_runtime,
        "load_config",
        lambda: {
            "inbounds": [
                {
                    "tag": "vless-reality-in",
                    "port": 8443,
                    "settings": {"clients": [], "decryption": "none"},
                    "streamSettings": {
                        "security": "reality",
                        "realitySettings": {
                            "serverNames": ["www.cloudflare.com"],
                            "publicKey": "server-public-key",
                            "privateKey": "server-private-key",
                            "shortIds": ["0123456789abcdef"],
                        },
                    },
                }
            ],
            "outbounds": [{"tag": "direct", "protocol": "freedom"}],
            "routing": {"rules": []},
        },
    )

    status, payload = api.handle_post(
        "/api/tunnels/save",
        {"public_domain": "hy.example.test", "name": "HY2 domain", "target_port": "3000"},
        admin_session(app_modules),
    )

    assert status == 400
    assert "reserved for a proxy node" in payload["error"]


def test_tunnel_save_rejects_missing_reality_public_key(app_modules, monkeypatch):
    api = app_modules["api"]
    monkeypatch.setattr(
        app_modules["api_tunnel_routes"].xray_runtime,
        "load_config",
        lambda: {
            "inbounds": [
                {
                    "tag": "vless-reality-in",
                    "listen": "0.0.0.0",
                    "port": 8443,
                    "protocol": "vless",
                    "settings": {"clients": [], "decryption": "none"},
                    "streamSettings": {
                        "network": "tcp",
                        "security": "reality",
                        "realitySettings": {
                            "dest": "www.cloudflare.com:443",
                            "serverNames": ["www.cloudflare.com"],
                            "privateKey": "server-private-key",
                            "shortIds": ["0123456789abcdef"],
                        },
                    },
                }
            ],
            "outbounds": [{"tag": "direct", "protocol": "freedom"}],
            "routing": {"rules": []},
        },
    )
    monkeypatch.setattr(app_modules["api_tunnel_routes"], "derive_public_key", lambda private_key: "")

    status, payload = api.handle_post(
        "/api/tunnels/save",
        {
            "public_domain": "new.example.com",
            "name": "New service",
            "target_port": "3000",
        },
        admin_session(app_modules),
    )

    assert status == 400
    assert "Reality public key" in payload["error"]


def test_tunnel_public_key_derivation_parses_current_xray_output(app_modules, monkeypatch):
    routes = app_modules["api_tunnel_routes"]

    def fake_run(cmd, timeout=15):
        return 0, "\n".join(
            [
                "PrivateKey: server-private-key",
                "Password (PublicKey): server-public-key",
                "Hash32: ignored",
            ]
        )

    monkeypatch.setattr(routes, "run", fake_run)

    assert routes.derive_public_key("server-private-key") == "server-public-key"


def test_admin_can_save_private_tcp_tunnel_without_public_domain(app_modules, monkeypatch):
    api = app_modules["api"]
    base_cfg = {
        "inbounds": [
            {
                "tag": "vless-reality-in",
                "listen": "0.0.0.0",
                "port": 8443,
                "protocol": "vless",
                "settings": {"clients": [], "decryption": "none"},
                "streamSettings": {
                    "network": "tcp",
                    "security": "reality",
                    "realitySettings": {
                        "dest": "www.cloudflare.com:443",
                        "serverNames": ["www.cloudflare.com"],
                        "publicKey": "server-public-key",
                        "privateKey": "server-private-key",
                        "shortIds": ["0123456789abcdef"],
                    },
                },
            }
        ],
        "outbounds": [{"tag": "direct", "protocol": "freedom"}],
        "routing": {"rules": []},
    }
    applied = {}
    monkeypatch.setattr(app_modules["api_tunnel_routes"].xray_runtime, "load_config", lambda: base_cfg)
    monkeypatch.setattr(app_modules["api_tunnel_routes"].xray_runtime, "write_and_restart_xray", lambda cfg: applied.setdefault("xray", cfg) or "backup")

    def fake_apply_nginx(tunnels):
        applied["nginx"] = list(tunnels)
        return {"domains": [], "issued": [], "conf": "/etc/nginx/conf.d/fake-ui-tunnels.conf"}

    monkeypatch.setattr(app_modules["api_tunnel_routes"].tunnel_nginx, "apply_native_nginx", fake_apply_nginx)

    status, payload = api.handle_post(
        "/api/tunnels/save",
        {
            "kind": "private_tcp",
            "id": "macbook-ssh",
            "name": "MacBook SSH",
            "target_host": "127.0.0.1",
            "target_port": "22",
        },
        admin_session(app_modules),
    )

    assert status == 200
    tunnel = payload["tunnel"]
    assert tunnel["kind"] == "private_tcp"
    assert tunnel["public_domain"] == ""
    assert tunnel["server_address"] == "vless.example.com"
    assert tunnel["target_port"] == 22

    status, bundle = api.handle_get("/api/tunnels/macbook-ssh/macos-bundle", admin_session(app_modules))
    assert status == 200
    assert bundle["filename"] == "macbook-ssh-macos-bridge.tgz"

    status, payload = api.handle_post("/api/tunnels/apply", {}, admin_session(app_modules))

    assert status == 200
    assert payload["nginx"]["domains"] == []
    assert next(item for item in applied["xray"]["inbounds"] if item["tag"] == "tunnel-portal-macbook-ssh")["port"] == 18081
    client = next(
        item for item in next(inbound for inbound in applied["xray"]["inbounds"] if inbound["tag"] == "vless-reality-in")["settings"]["clients"]
        if item.get("email") == "tunnel:macbook-ssh"
    )
    assert client["reverse"] == {"tag": "tunnel-reverse-macbook-ssh"}


def test_tunnel_apply_updates_xray_and_native_nginx(app_modules, monkeypatch):
    api = app_modules["api"]
    base_cfg = {
        "inbounds": [
            {
                "tag": "vless-reality-in",
                "listen": "0.0.0.0",
                "port": 8443,
                "protocol": "vless",
                "settings": {"clients": [], "decryption": "none"},
                "streamSettings": {
                    "network": "tcp",
                    "security": "reality",
                    "realitySettings": {
                        "dest": "www.cloudflare.com:443",
                        "serverNames": ["www.cloudflare.com"],
                        "publicKey": "server-public-key",
                        "privateKey": "server-private-key",
                        "shortIds": ["0123456789abcdef"],
                    },
                },
            }
        ],
        "outbounds": [{"tag": "direct", "protocol": "freedom"}],
        "routing": {"rules": []},
    }
    applied = {}
    monkeypatch.setattr(app_modules["api_tunnel_routes"].xray_runtime, "load_config", lambda: base_cfg)
    monkeypatch.setattr(app_modules["api_tunnel_routes"].xray_runtime, "write_and_restart_xray", lambda cfg: applied.setdefault("xray", cfg) or "backup")
    def fake_apply_nginx(tunnels):
        applied["nginx"] = list(tunnels)
        return {"domains": ["new.example.com"]}

    monkeypatch.setattr(app_modules["api_tunnel_routes"].tunnel_nginx, "apply_native_nginx", fake_apply_nginx)

    status, payload = api.handle_post(
        "/api/tunnels/save",
        {
            "public_domain": "new.example.com",
            "name": "New service",
            "target_port": "3000",
        },
        admin_session(app_modules),
    )
    assert status == 200

    status, payload = api.handle_post("/api/tunnels/apply", {}, admin_session(app_modules))

    assert status == 200
    assert payload["nginx"] == {"domains": ["new.example.com"]}
    assert next(item for item in applied["xray"]["inbounds"] if item["tag"] == "tunnel-portal-new-example-com")["port"] == 18081
    assert applied["nginx"][0]["public_domain"] == "new.example.com"


def test_tunnel_save_auto_applies_xray_and_native_nginx(app_modules, monkeypatch):
    api = app_modules["api"]
    base_cfg = {
        "inbounds": [
            {
                "tag": "vless-reality-in",
                "listen": "0.0.0.0",
                "port": 8443,
                "protocol": "vless",
                "settings": {"clients": [], "decryption": "none"},
                "streamSettings": {
                    "network": "tcp",
                    "security": "reality",
                    "realitySettings": {
                        "dest": "www.cloudflare.com:443",
                        "serverNames": ["www.cloudflare.com"],
                        "publicKey": "server-public-key",
                        "privateKey": "server-private-key",
                        "shortIds": ["0123456789abcdef"],
                    },
                },
            }
        ],
        "outbounds": [{"tag": "direct", "protocol": "freedom"}],
        "routing": {"rules": []},
    }
    applied = {}
    monkeypatch.setattr(app_modules["api_tunnel_routes"].xray_runtime, "load_config", lambda: base_cfg)
    monkeypatch.setattr(app_modules["api_tunnel_routes"].xray_runtime, "write_and_restart_xray", lambda cfg: applied.setdefault("xray", cfg) or "backup")

    def fake_apply_nginx(tunnels):
        applied["nginx"] = list(tunnels)
        return {"domains": [item.get("public_domain") for item in tunnels if item.get("public_domain")]}

    monkeypatch.setattr(app_modules["api_tunnel_routes"].tunnel_nginx, "apply_native_nginx", fake_apply_nginx)

    status, payload = api.handle_post(
        "/api/tunnels/save",
        {
            "public_domain": "new.example.com",
            "name": "New service",
            "target_port": "3000",
        },
        admin_session(app_modules),
    )

    assert status == 200
    assert payload["applied"] is True
    assert payload["nginx"] == {"domains": ["new.example.com"]}
    assert next(item for item in applied["xray"]["inbounds"] if item["tag"] == "tunnel-portal-new-example-com")["port"] == 18081
    assert applied["nginx"][0]["public_domain"] == "new.example.com"


def test_tunnel_action_auto_applies_after_disable_and_delete(app_modules, monkeypatch):
    api = app_modules["api"]
    base_cfg = {
        "inbounds": [
            {
                "tag": "vless-reality-in",
                "listen": "0.0.0.0",
                "port": 8443,
                "protocol": "vless",
                "settings": {"clients": [], "decryption": "none"},
                "streamSettings": {
                    "network": "tcp",
                    "security": "reality",
                    "realitySettings": {
                        "dest": "www.cloudflare.com:443",
                        "serverNames": ["www.cloudflare.com"],
                        "publicKey": "server-public-key",
                        "privateKey": "server-private-key",
                        "shortIds": ["0123456789abcdef"],
                    },
                },
            }
        ],
        "outbounds": [{"tag": "direct", "protocol": "freedom"}],
        "routing": {"rules": []},
    }
    applied = {"xray": []}
    monkeypatch.setattr(app_modules["api_tunnel_routes"].xray_runtime, "load_config", lambda: base_cfg)

    def fake_write_xray(cfg):
        applied.setdefault("xray", []).append(cfg)
        return "backup"

    def fake_apply_nginx(tunnels):
        applied.setdefault("nginx", []).append(list(tunnels))
        return {"domains": [item.get("public_domain") for item in tunnels if item.get("public_domain")]}

    monkeypatch.setattr(app_modules["api_tunnel_routes"].xray_runtime, "write_and_restart_xray", fake_write_xray)
    monkeypatch.setattr(app_modules["api_tunnel_routes"].tunnel_nginx, "apply_native_nginx", fake_apply_nginx)

    status, payload = api.handle_post(
        "/api/tunnels/save",
        {
            "public_domain": "new.example.com",
            "name": "New service",
            "target_port": "3000",
        },
        admin_session(app_modules),
    )
    assert status == 200, payload

    status, payload = api.handle_post(
        "/api/tunnels/action",
        {"id": "new-example-com", "action": "disable"},
        admin_session(app_modules),
    )

    assert status == 200
    assert payload["applied"] is True
    assert "tunnel-portal-new-example-com" not in [item.get("tag") for item in applied["xray"][-1]["inbounds"]]
    assert applied["nginx"][-1] == []

    status, payload = api.handle_post(
        "/api/tunnels/action",
        {"id": "new-example-com", "action": "delete"},
        admin_session(app_modules),
    )

    assert status == 200
    assert payload["applied"] is True
    assert "tunnel-portal-new-example-com" not in [item.get("tag") for item in applied["xray"][-1]["inbounds"]]
    assert applied["nginx"][-1] == []


def test_admin_can_export_shared_bridge_agent_config_and_bundle(app_modules, monkeypatch):
    api = app_modules["api"]
    monkeypatch.setattr(
        app_modules["api_tunnel_routes"].xray_runtime,
        "load_config",
        lambda: {
            "inbounds": [
                {
                    "tag": "vless-reality-in",
                    "listen": "0.0.0.0",
                    "port": 8443,
                    "protocol": "vless",
                    "settings": {"clients": [], "decryption": "none"},
                    "streamSettings": {
                        "network": "tcp",
                        "security": "reality",
                        "realitySettings": {
                            "dest": "www.cloudflare.com:443",
                            "serverNames": ["www.cloudflare.com"],
                            "publicKey": "server-public-key",
                            "privateKey": "server-private-key",
                            "shortIds": ["0123456789abcdef"],
                        },
                    },
                }
            ],
            "outbounds": [{"tag": "direct", "protocol": "freedom"}],
            "routing": {"rules": []},
        },
    )

    for payload in [
        {
            "public_domain": "test.example.com",
            "id": "test-example-com",
            "name": "Test Web",
            "target_port": "18080",
            "bridge_mode": "shared",
            "bridge_id": "macbook-web",
            "bridge_platform": "macos",
        },
        {
            "public_domain": "mac.example.com",
            "id": "mac-example-com",
            "name": "Mac Web",
            "target_port": "18081",
            "bridge_mode": "shared",
            "bridge_id": "macbook-web",
            "bridge_platform": "macos",
        },
        {
            "kind": "private_tcp",
            "id": "macbook-ssh",
            "name": "MacBook SSH",
            "target_port": "22",
            "bridge_mode": "dedicated",
            "bridge_id": "macbook-ssh",
        },
    ]:
        status, body = api.handle_post("/api/tunnels/save", payload, admin_session(app_modules))
        assert status == 200, body

    status, body = api.handle_get("/api/tunnels/bridges/macbook-web/bridge-config", admin_session(app_modules))
    assert status == 200
    assert body["filename"] == "macbook-web-xray-bridge.json"
    tags = [item["tag"] for item in body["config"]["outbounds"]]
    assert "tunnel-reverse-out-test-example-com" in tags
    assert "tunnel-reverse-out-mac-example-com" in tags
    assert "tunnel-reverse-out-macbook-ssh" not in tags

    status, bundle = api.handle_get("/api/tunnels/bridges/macbook-web/macos-bundle", admin_session(app_modules))
    assert status == 200
    assert bundle["filename"] == "macbook-web-macos-bridge.tgz"
    assert bundle["content_type"] == "application/gzip"
    assert isinstance(bundle["content"], bytes)

    status, bundle = api.handle_get("/api/tunnels/bridges/macbook-web/linux-bundle", admin_session(app_modules))
    assert status == 200
    assert bundle["filename"] == "macbook-web-linux-bridge.tgz"

    status, bundle = api.handle_get("/api/tunnels/bridges/macbook-web/windows-bundle", admin_session(app_modules))
    assert status == 200
    assert bundle["filename"] == "macbook-web-windows-bridge.tgz"


def test_shared_bridge_save_adds_private_tcp_ssh_by_default(app_modules, monkeypatch):
    api = app_modules["api"]
    monkeypatch.setattr(
        app_modules["api_tunnel_routes"].xray_runtime,
        "load_config",
        lambda: {
            "inbounds": [
                {
                    "tag": "vless-reality-in",
                    "listen": "0.0.0.0",
                    "port": 8443,
                    "protocol": "vless",
                    "settings": {"clients": [], "decryption": "none"},
                    "streamSettings": {
                        "network": "tcp",
                        "security": "reality",
                        "realitySettings": {
                            "dest": "www.cloudflare.com:443",
                            "serverNames": ["www.cloudflare.com"],
                            "publicKey": "server-public-key",
                            "privateKey": "server-private-key",
                            "shortIds": ["0123456789abcdef"],
                        },
                    },
                }
            ],
            "outbounds": [{"tag": "direct", "protocol": "freedom"}],
            "routing": {"rules": []},
        },
    )

    status, payload = api.handle_post(
        "/api/tunnels/save",
        {
            "public_domain": "web.example.com",
            "id": "web-example-com",
            "name": "Web",
            "target_port": "3000",
            "bridge_mode": "shared",
            "bridge_id": "office-mac",
            "bridge_platform": "macos",
        },
        admin_session(app_modules),
    )

    assert status == 200
    by_id = {item["id"]: item for item in payload["tunnels"]}
    assert by_id["office-mac-ssh"]["kind"] == "private_tcp"
    assert by_id["office-mac-ssh"]["public_domain"] == ""
    assert by_id["office-mac-ssh"]["target_port"] == 22
    assert by_id["office-mac-ssh"]["bridge_mode"] == "shared"
    assert by_id["office-mac-ssh"]["bridge_id"] == "office-mac"
    assert by_id["office-mac-ssh"]["client_id"] != by_id["web-example-com"]["client_id"]

    status, body = api.handle_get("/api/tunnels/bridges/office-mac/bridge-config", admin_session(app_modules))

    assert status == 200
    tags = [item["tag"] for item in body["config"]["outbounds"]]
    assert "tunnel-reverse-out-web-example-com" in tags
    assert "tunnel-reverse-out-office-mac-ssh" in tags
    ssh_local = next(item for item in body["config"]["outbounds"] if item["tag"] == "tunnel-local-service-office-mac-ssh")
    assert ssh_local["settings"]["redirect"] == "127.0.0.1:22"


def test_shared_public_tunnel_defaults_to_existing_shared_bridge(app_modules, monkeypatch):
    api = app_modules["api"]
    monkeypatch.setattr(
        app_modules["api_tunnel_routes"].xray_runtime,
        "load_config",
        lambda: {
            "inbounds": [
                {
                    "tag": "vless-reality-in",
                    "listen": "0.0.0.0",
                    "port": 8443,
                    "protocol": "vless",
                    "settings": {"clients": [], "decryption": "none"},
                    "streamSettings": {
                        "network": "tcp",
                        "security": "reality",
                        "realitySettings": {
                            "dest": "www.cloudflare.com:443",
                            "serverNames": ["www.cloudflare.com"],
                            "publicKey": "server-public-key",
                            "privateKey": "server-private-key",
                            "shortIds": ["0123456789abcdef"],
                        },
                    },
                }
            ],
            "outbounds": [{"tag": "direct", "protocol": "freedom"}],
            "routing": {"rules": []},
        },
    )

    status, first = api.handle_post(
        "/api/tunnels/save",
        {
            "public_domain": "first.example.com",
            "name": "First",
            "target_port": "3000",
            "bridge_mode": "shared",
            "bridge_id": "office-mac",
            "bridge_platform": "macos",
        },
        admin_session(app_modules),
    )
    assert status == 200, first

    status, second = api.handle_post(
        "/api/tunnels/save",
        {
            "public_domain": "second.example.com",
            "name": "Second",
            "target_port": "3001",
            "bridge_mode": "shared",
            "bridge_platform": "macos",
        },
        admin_session(app_modules),
    )

    assert status == 200, second
    by_id = {item["id"]: item for item in second["tunnels"]}
    assert by_id["second-example-com"]["bridge_id"] == "office-mac"
    assert by_id["second-example-com"]["bridge_mode"] == "shared"
    ssh_tunnels = [
        item for item in second["tunnels"]
        if item["kind"] == "private_tcp" and item["target_port"] == 22 and item["bridge_mode"] == "shared"
    ]
    assert len(ssh_tunnels) == 1
    assert ssh_tunnels[0]["bridge_id"] == "office-mac"

    status, body = api.handle_get("/api/tunnels/bridges/office-mac/bridge-config", admin_session(app_modules))

    assert status == 200
    tags = [item["tag"] for item in body["config"]["outbounds"]]
    assert "tunnel-reverse-out-first-example-com" in tags
    assert "tunnel-reverse-out-second-example-com" in tags
    assert "tunnel-reverse-out-office-mac-ssh" in tags


def test_shared_bridge_default_ssh_does_not_overwrite_existing_dedicated_tunnel(app_modules, monkeypatch):
    api = app_modules["api"]
    monkeypatch.setattr(
        app_modules["api_tunnel_routes"].xray_runtime,
        "load_config",
        lambda: {
            "inbounds": [
                {
                    "tag": "vless-reality-in",
                    "port": 8443,
                    "settings": {"clients": [], "decryption": "none"},
                    "streamSettings": {
                        "network": "tcp",
                        "security": "reality",
                        "realitySettings": {
                            "serverNames": ["www.cloudflare.com"],
                            "publicKey": "server-public-key",
                            "privateKey": "server-private-key",
                            "shortIds": ["0123456789abcdef"],
                        },
                    },
                }
            ],
            "outbounds": [{"tag": "direct", "protocol": "freedom"}],
            "routing": {"rules": []},
        },
    )

    status, body = api.handle_post(
        "/api/tunnels/save",
        {
            "kind": "private_tcp",
            "id": "office-mac-ssh",
            "name": "Existing SSH",
            "target_host": "10.0.0.20",
            "target_port": "2222",
            "bridge_mode": "dedicated",
            "bridge_id": "existing-ssh",
        },
        admin_session(app_modules),
    )
    assert status == 200, body

    status, payload = api.handle_post(
        "/api/tunnels/save",
        {
            "public_domain": "web.example.com",
            "id": "web-example-com",
            "name": "Web",
            "target_port": "3000",
            "bridge_mode": "shared",
            "bridge_id": "office-mac",
            "bridge_platform": "macos",
        },
        admin_session(app_modules),
    )

    assert status == 200, payload
    by_id = {item["id"]: item for item in payload["tunnels"]}
    assert by_id["office-mac-ssh"]["bridge_mode"] == "dedicated"
    assert by_id["office-mac-ssh"]["target"] == "10.0.0.20:2222"
    auto_ssh = [item for item in payload["tunnels"] if item["bridge_mode"] == "shared" and item["bridge_id"] == "office-mac" and item["kind"] == "private_tcp"]
    assert len(auto_ssh) == 1
    assert auto_ssh[0]["id"] == "office-mac-ssh-1"
    assert auto_ssh[0]["target_port"] == 22


def test_shared_bridge_default_ssh_is_global_not_per_bridge(app_modules, monkeypatch):
    api = app_modules["api"]
    monkeypatch.setattr(
        app_modules["api_tunnel_routes"].xray_runtime,
        "load_config",
        lambda: {
            "inbounds": [
                {
                    "tag": "vless-reality-in",
                    "port": 8443,
                    "settings": {"clients": [], "decryption": "none"},
                    "streamSettings": {
                        "network": "tcp",
                        "security": "reality",
                        "realitySettings": {
                            "serverNames": ["www.cloudflare.com"],
                            "publicKey": "server-public-key",
                            "privateKey": "server-private-key",
                            "shortIds": ["0123456789abcdef"],
                        },
                    },
                }
            ],
            "outbounds": [{"tag": "direct", "protocol": "freedom"}],
            "routing": {"rules": []},
        },
    )

    status, first = api.handle_post(
        "/api/tunnels/save",
        {
            "public_domain": "first.example.com",
            "name": "First",
            "target_port": "3000",
            "bridge_mode": "shared",
            "bridge_id": "first-bridge",
            "bridge_platform": "macos",
        },
        admin_session(app_modules),
    )
    assert status == 200, first

    status, second = api.handle_post(
        "/api/tunnels/save",
        {
            "public_domain": "second.example.com",
            "name": "Second",
            "target_port": "3001",
            "bridge_mode": "shared",
            "bridge_id": "second-bridge",
            "bridge_platform": "macos",
        },
        admin_session(app_modules),
    )

    assert status == 200, second
    default_ssh = [
        item for item in second["tunnels"]
        if item["kind"] == "private_tcp" and item["target_port"] == 22 and item["public_domain"] == ""
    ]
    assert len(default_ssh) == 1
    assert default_ssh[0]["bridge_id"] == "first-bridge"


def test_admin_can_export_dedicated_bridge_bundle_for_backend_platforms(app_modules, monkeypatch):
    api = app_modules["api"]
    monkeypatch.setattr(
        app_modules["api_tunnel_routes"].xray_runtime,
        "load_config",
        lambda: {
            "inbounds": [
                {
                    "tag": "vless-reality-in",
                    "port": 8443,
                    "streamSettings": {
                        "realitySettings": {
                            "dest": "www.cloudflare.com:443",
                            "serverNames": ["www.cloudflare.com"],
                            "publicKey": "server-public-key",
                            "privateKey": "server-private-key",
                            "shortIds": ["0123456789abcdef"],
                        },
                    },
                    "settings": {"clients": []},
                }
            ],
            "outbounds": [{"tag": "direct", "protocol": "freedom"}],
            "routing": {"rules": []},
        },
    )

    status, body = api.handle_post(
        "/api/tunnels/save",
        {
            "public_domain": "api.example.com",
            "id": "office-api",
            "name": "Office API",
            "target_port": "5000",
            "bridge_platform": "linux",
        },
        admin_session(app_modules),
    )
    assert status == 200, body

    status, bundle = api.handle_get("/api/tunnels/office-api/linux-bundle", admin_session(app_modules))
    assert status == 200
    assert bundle["filename"] == "office-api-linux-bridge.tgz"
    assert bundle["content_type"] == "application/gzip"
    assert isinstance(bundle["content"], bytes)

    status, bundle = api.handle_get("/api/tunnels/office-api/windows-bundle", admin_session(app_modules))
    assert status == 200
    assert bundle["filename"] == "office-api-windows-bridge.tgz"


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


def test_session_cookie_and_security_headers(app_modules):
    import auth_store
    import security
    import web_handler
    from web_handler import PanelRequestHandler

    token = auth_store.make_session("admin", "admin")
    assert "HttpOnly" in security.session_cookie(token)
    assert "Secure" in security.session_cookie(token)
    assert "SameSite=Lax" in security.session_cookie(token)
    headers = security.security_headers("text/html; charset=utf-8")
    assert headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    assert hasattr(PanelRequestHandler, "send_security_headers")
    assert web_handler.cache_control_for_path("/assets/js/main.js") == "no-cache"
    assert web_handler.cache_control_for_path("/favicon.ico") == "no-cache"
    assert web_handler.cache_control_for_path("/login") == "no-store"


def test_legacy_session_without_csrf_is_rejected(app_modules):
    import auth_store

    payload = auth_store.b64e(b'{"u":"admin","r":"admin","t":9999999999,"n":"legacy"}')
    token = f"{payload}.{auth_store.sign(payload, 'test-secret')}"

    assert auth_store.session_payload(token) is None


def test_login_rate_limit_tracks_failures(app_modules):
    import security

    key = "203.0.113.9:admin"
    security.clear_login_failures(key)
    for _ in range(security.LOGIN_MAX_ATTEMPTS):
        assert security.login_limited(key, now=1000) is False
        security.record_login_failure(key, now=1000)
    assert security.login_limited(key, now=1000) is True
    security.clear_login_failures(key)
    assert security.login_limited(key, now=1000) is False


def test_forwarded_client_ip_only_trusted_from_proxy(app_modules):
    import security
    import subscription_guard

    assert security.client_ip_from_request("127.0.0.1", "198.51.100.7, 127.0.0.1") == "198.51.100.7"
    assert security.client_ip_from_request("127.0.0.1", "198.51.100.99, 198.51.100.7") == "198.51.100.7"
    assert security.client_ip_from_request("8.8.8.8", "198.51.100.7, 127.0.0.1") == "8.8.8.8"
    assert security.login_key_from_request("Admin", remote_ip="8.8.8.8", forwarded_for="198.51.100.7") == "8.8.8.8:admin"
    assert subscription_guard.client_ip({"X-Forwarded-For": "198.51.100.7"}, "8.8.8.8") == "8.8.8.8"
    assert subscription_guard.client_ip({"X-Forwarded-For": "198.51.100.7"}, "127.0.0.1") == "198.51.100.7"


def test_api_login_uses_rate_limit_and_audit(app_modules, monkeypatch):
    import api
    import audit_log
    import security

    monkeypatch.setattr(security, "login_key_from_request", lambda username, remote_ip="", forwarded_for="": "198.51.100.7:admin")

    for _ in range(security.LOGIN_MAX_ATTEMPTS):
        status, payload = api.handle_post("/api/login", {"username": "admin", "password": "wrong"}, None)
        assert status == 401
        assert payload["ok"] is False

    status, payload = api.handle_post("/api/login", {"username": "admin", "password": "adminpass"}, None)
    assert status == 429
    assert payload["ok"] is False
    assert "too many" in payload["error"].lower()

    events = audit_log.tail(20)
    assert any(item["action"] == "auth.login_failed" for item in events)
    assert any(item["action"] == "auth.login_rate_limited" for item in events)


def test_http_api_post_requires_csrf_for_authenticated_sessions(app_modules, monkeypatch):
    import http_api_routes

    captured = {}

    class FakeHandler:
        path = "/api/cache/clear"
        headers = {}

        def __init__(self, csrf_header=""):
            self.headers = {}
            if csrf_header:
                self.headers["X-CSRF-Token"] = csrf_header

        def current_session(self):
            return {"u": "admin", "r": "admin", "role": "admin", "csrf": "csrf-token"}

        def read_json_or_form(self):
            return {}

        def respond_json(self, payload, status):
            captured["payload"] = payload
            captured["status"] = status

    http_api_routes.handle_post(FakeHandler())
    assert captured["status"] == 403
    assert captured["payload"]["error"] == "csrf validation failed"

    monkeypatch.setattr(http_api_routes.api, "handle_post", lambda path, data, session: (200, {"ok": True}))
    http_api_routes.handle_post(FakeHandler("csrf-token"))
    assert captured["status"] == 200
    assert captured["payload"]["ok"] is True


def test_http_api_public_register_ignores_stale_session_csrf(app_modules, monkeypatch):
    import http_api_routes
    ops = app_modules["operations_service"]
    user_store = app_modules["user_store"]

    ops.update_public_settings({"registration_enabled": True})
    captured = {}

    class FakeHandler:
        path = "/api/register"
        headers = {"Content-Type": "application/json"}
        client_address = ("203.0.113.9", 12345)

        def current_session(self):
            return {"u": "olduser", "r": "user", "role": "user", "csrf": "old-csrf"}

        def read_json_or_form(self):
            return {"username": "stalecsrf", "password": "password123"}

        def respond_json(self, payload, status):
            captured["payload"] = payload
            captured["status"] = status

    http_api_routes.handle_post(FakeHandler())

    assert captured["status"] == 200
    assert captured["payload"]["message"] == "registration complete; please log in"
    assert user_store.get_user("stalecsrf")


def test_admin_node_qr_requires_admin(app_modules, monkeypatch):
    import http_qr_routes

    monkeypatch.setattr(http_qr_routes, "build_admin_node_link", lambda kind, node_id="": f"vless://{kind}/{node_id}")
    monkeypatch.setattr(http_qr_routes, "qr_png_for_link", lambda link: b"\x89PNG\r\n\x1a\nqr")

    class Handler:
        path = "/qr/vless"
        status = None
        body = None
        content_type = None

        def __init__(self, username="", role=""):
            self.username = username
            self.role = role

        def current_role(self):
            return self.role

        def current_username(self):
            return self.username

        def forbidden(self):
            self.status = 403

        def respond_bytes(self, body, content_type):
            self.status = 200
            self.body = body
            self.content_type = content_type

        def respond(self, body, status=200):
            self.status = status
            self.body = body

    anonymous = Handler()
    http_qr_routes.handle_admin_node_qr(anonymous, "", "")
    assert anonymous.status == 403

    viewer = Handler("viewer", "user")
    http_qr_routes.handle_admin_node_qr(viewer, "viewer", "user")
    assert viewer.status == 403

    admin = Handler("admin", "admin")
    http_qr_routes.handle_admin_node_qr(admin, "admin", "admin")
    assert admin.status == 200
    assert admin.content_type == "image/png"


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


def test_user_plan_name_tracks_plan_rename(app_modules):
    api = app_modules["api"]
    user_admin = app_modules["user_admin"]

    status, payload = api.handle_post(
        "/api/plans/save",
        {
            "id": "rename-plan",
            "name": "Original Name",
            "days": "30",
            "traffic_gb": "100",
            "price": "9",
            "node_groups": "default",
            "enabled": True,
        },
        admin_session(app_modules),
    )
    assert status == 200
    user_admin.create_airport_user(
        "rename_user",
        "30",
        panel_password_input="password123",
        traffic_gb_input="100",
        plan_id="rename-plan",
    )

    status, payload = api.handle_post(
        "/api/plans/save",
        {
            "id": "rename-plan",
            "name": "Renamed Plan",
            "days": "30",
            "traffic_gb": "100",
            "price": "9",
            "node_groups": "default",
            "enabled": True,
        },
        admin_session(app_modules),
    )
    assert status == 200

    status, users_payload = api.handle_get("/api/users", admin_session(app_modules))
    assert status == 200
    user_item = next(item for item in users_payload["users"] if item["username"] == "rename_user")
    assert user_item["plan_name"] == "Renamed Plan"
    assert user_item["metrics"]["plan_name"] == "Renamed Plan"

    status, dashboard_payload = api.handle_get(
        "/api/dashboard",
        {"u": "rename_user", "r": "user", "role": "user"},
    )
    assert status == 200
    assert dashboard_payload["data"]["profile"]["plan_name"] == "Renamed Plan"


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


def test_registration_password_is_not_stored_in_plaintext(app_modules):
    import registration_store
    import store_facade
    import user_admin

    store_facade.ensure_sqlite()
    submitted = "secret-pass-123"
    request = registration_store.create_registration("charlie", submitted, "charlie@example.test", "starter", "")
    stored = registration_store.get_registration(request["token"])

    assert "password" not in request
    assert stored.get("password") != submitted
    assert stored.get("password_hash", {}).get("alg") == "pbkdf2_sha256"

    result = user_admin.approve_registration(request["token"], operator="admin")
    assert result["username"] == "charlie"
    assert "panel_password" not in result


def test_restore_backup_sets_database_permissions_and_checks_integrity(app_modules):
    import backup_manager
    import os

    backup = backup_manager.create_backup("permissions")
    raw = backup_manager.read_backup_bytes(backup["name"])
    backup_manager.restore_backup_archive(raw, operator="admin")

    db_path = backup_manager.PANEL_DIR / "fake-ui.db"
    assert oct(os.stat(db_path).st_mode & 0o777) == "0o600"


def test_restore_backup_rejects_bad_database_without_overwriting_current(app_modules):
    import backup_manager
    import store_facade
    import user_store

    store_facade.ensure_sqlite()
    users = user_store.load_users()
    users["users"]["survivor"] = {"enabled": True, "sub_token": "sub_survivor", "panel_password": {}}
    user_store.save_users(users)
    backup_manager.create_backup("pre-bad-restore")

    raw = BytesIO()
    with tarfile.open(fileobj=raw, mode="w:gz") as tar:
        meta = b'{"reason":"bad-db","files":["fake-ui.db"]}'
        info = tarfile.TarInfo("panel-backup-bad/backup.json")
        info.size = len(meta)
        tar.addfile(info, BytesIO(meta))
        bad_db = b"not sqlite"
        info = tarfile.TarInfo("panel-backup-bad/fake-ui.db")
        info.size = len(bad_db)
        tar.addfile(info, BytesIO(bad_db))

    with pytest.raises(RuntimeError, match="backup database integrity check failed"):
        backup_manager.restore_backup_archive(raw.getvalue(), operator="admin")

    assert user_store.get_user("survivor")["sub_token"] == "sub_survivor"
