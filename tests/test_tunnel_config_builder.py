import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "baseline"
if str(BASELINE) not in sys.path:
    sys.path.insert(0, str(BASELINE))


def tunnel_node():
    return {
        "id": "macmini",
        "name": "Mac mini SSH",
        "enabled": True,
        "portal_port": 2222,
        "target_host": "127.0.0.1",
        "target_port": 22,
        "client_id": "11111111-1111-4111-8111-111111111111",
        "flow": "xtls-rprx-vision",
    }


def tunnel_node_with_blank_flow():
    node = tunnel_node()
    node["flow"] = "   "
    return node


def reality_profile():
    return {
        "server_name": "www.cloudflare.com",
        "private_key": "server-private-key",
        "public_key": "server-public-key",
        "short_id": "0123456789abcdef",
        "address": "vless.example.com",
        "port": 443,
        "internal_port": 9443,
    }


def base_xray_config():
    return {
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
                        "show": False,
                        "dest": "www.cloudflare.com:443",
                        "xver": 0,
                        "serverNames": ["www.cloudflare.com"],
                        "privateKey": "server-private-key",
                        "shortIds": ["0123456789abcdef"],
                    },
                },
            }
        ],
        "outbounds": [
            {"tag": "direct", "protocol": "freedom", "settings": {"domainStrategy": "UseIPv4"}},
            {"tag": "block", "protocol": "blackhole"},
        ],
        "routing": {
            "domainStrategy": "IPIfNonMatch",
            "rules": [
                {"type": "field", "inboundTag": ["vless-reality-in"], "outboundTag": "direct"}
            ],
        },
    }


def test_build_portal_config_reuses_existing_reality_inbound_and_adds_reverse_client():
    import tunnel_config_builder

    cfg = tunnel_config_builder.build_portal_config(base_xray_config(), [tunnel_node()])

    vless = next(item for item in cfg["inbounds"] if item["tag"] == "vless-reality-in")
    assert vless["listen"] == "0.0.0.0"
    assert vless["port"] == 8443
    assert vless["protocol"] == "vless"
    assert vless["settings"]["clients"] == [
        {"id": "22222222-2222-4222-8222-222222222222", "email": "panel-user:alice"},
        {
            "id": "11111111-1111-4111-8111-111111111111",
            "email": "tunnel:macmini",
            "flow": "xtls-rprx-vision",
            "reverse": {"tag": "tunnel-reverse-macmini"},
        }
    ]
    reality = vless["streamSettings"]["realitySettings"]
    assert reality["dest"] == "www.cloudflare.com:443"
    assert reality["serverNames"] == ["www.cloudflare.com"]
    assert reality["privateKey"] == "server-private-key"
    assert reality["shortIds"] == ["0123456789abcdef"]
    assert [item["tag"] for item in cfg["inbounds"]].count("vless-reality-in") == 1
    assert "tunnel-reality-in" not in [item["tag"] for item in cfg["inbounds"]]

    portal = next(item for item in cfg["inbounds"] if item["tag"] == "tunnel-portal-macmini")
    assert portal["listen"] == "0.0.0.0"
    assert portal["port"] == 2222
    assert portal["protocol"] == "tunnel"
    assert portal["settings"]["allowedNetwork"] == "tcp"

    assert {
        "type": "field",
        "inboundTag": ["tunnel-portal-macmini"],
        "outboundTag": "tunnel-reverse-macmini",
    } in cfg["routing"]["rules"]
    assert {"tag": "direct", "protocol": "freedom", "settings": {"domainStrategy": "UseIPv4"}} in cfg["outbounds"]


def test_build_portal_config_rejects_tunnel_uuid_reused_by_panel_user():
    import pytest
    import tunnel_config_builder

    node = tunnel_node()
    node["client_id"] = "22222222-2222-4222-8222-222222222222"

    with pytest.raises(RuntimeError, match="UUID"):
        tunnel_config_builder.build_portal_config(base_xray_config(), [node])


def test_build_portal_config_rejects_duplicate_portal_ports_and_tags():
    import pytest
    import tunnel_config_builder

    first = tunnel_node()
    second = tunnel_node()
    second.update(
        {
            "id": "macmini-copy",
            "portal_port": first["portal_port"],
            "client_id": "33333333-3333-4333-8333-333333333333",
        }
    )

    with pytest.raises(RuntimeError, match="portal"):
        tunnel_config_builder.build_portal_config(base_xray_config(), [first, second])


def test_build_bridge_config_connects_back_and_redirects_to_local_service():
    import tunnel_config_builder

    cfg = tunnel_config_builder.build_bridge_config(tunnel_node(), reality_profile())

    reverse = next(item for item in cfg["outbounds"] if item["tag"] == "tunnel-reverse-out")
    assert reverse["protocol"] == "vless"
    assert reverse["settings"]["address"] == "vless.example.com"
    assert reverse["settings"]["port"] == 443
    assert reverse["settings"]["id"] == "11111111-1111-4111-8111-111111111111"
    assert reverse["settings"]["flow"] == "xtls-rprx-vision"
    assert reverse["settings"]["reverse"] == {"tag": "tunnel-reverse-in"}
    assert reverse["streamSettings"]["security"] == "reality"
    reality = reverse["streamSettings"]["realitySettings"]
    assert reality["serverName"] == "www.cloudflare.com"
    assert reality["publicKey"] == "server-public-key"
    assert reality["shortId"] == "0123456789abcdef"

    local = next(item for item in cfg["outbounds"] if item["tag"] == "tunnel-local-service")
    assert local["protocol"] == "freedom"
    assert local["settings"]["redirect"] == "127.0.0.1:22"
    assert local["settings"]["finalRules"] == [
        {"action": "allow", "network": "tcp", "ip": "127.0.0.1", "port": "22"}
    ]
    assert {
        "type": "field",
        "inboundTag": ["tunnel-reverse-in"],
        "outboundTag": "tunnel-local-service",
    } in cfg["routing"]["rules"]


def test_build_shared_bridge_config_combines_multiple_services_in_one_xray_process():
    import tunnel_config_builder

    web = tunnel_node()
    web.update({"id": "web", "target_port": 3000, "client_id": "11111111-1111-4111-8111-111111111111"})
    api = tunnel_node()
    api.update({"id": "api", "target_port": 5000, "client_id": "33333333-3333-4333-8333-333333333333"})

    cfg = tunnel_config_builder.build_shared_bridge_config([web, api], reality_profile())

    tags = [item["tag"] for item in cfg["outbounds"]]
    assert "tunnel-reverse-out-web" in tags
    assert "tunnel-reverse-out-api" in tags
    assert "tunnel-local-service-web" in tags
    assert "tunnel-local-service-api" in tags
    web_reverse = next(item for item in cfg["outbounds"] if item["tag"] == "tunnel-reverse-out-web")
    api_reverse = next(item for item in cfg["outbounds"] if item["tag"] == "tunnel-reverse-out-api")
    assert web_reverse["settings"]["id"] == "11111111-1111-4111-8111-111111111111"
    assert api_reverse["settings"]["id"] == "33333333-3333-4333-8333-333333333333"
    assert web_reverse["settings"]["reverse"] == {"tag": "tunnel-reverse-in-web"}
    assert api_reverse["settings"]["reverse"] == {"tag": "tunnel-reverse-in-api"}
    web_local = next(item for item in cfg["outbounds"] if item["tag"] == "tunnel-local-service-web")
    api_local = next(item for item in cfg["outbounds"] if item["tag"] == "tunnel-local-service-api")
    assert web_local["settings"]["redirect"] == "127.0.0.1:3000"
    assert api_local["settings"]["redirect"] == "127.0.0.1:5000"
    assert {
        "type": "field",
        "inboundTag": ["tunnel-reverse-in-web"],
        "outboundTag": "tunnel-local-service-web",
    } in cfg["routing"]["rules"]
    assert {
        "type": "field",
        "inboundTag": ["tunnel-reverse-in-api"],
        "outboundTag": "tunnel-local-service-api",
    } in cfg["routing"]["rules"]


def test_public_domain_is_metadata_not_hardcoded_into_reality_bridge():
    import tunnel_config_builder

    node = tunnel_node()
    node["public_domain"] = "new.example.com"

    cfg = tunnel_config_builder.build_bridge_config(node, reality_profile())

    dumped = str(cfg)
    assert "new.example.com" not in dumped
    assert "www.cloudflare.com" in dumped


def test_blank_flow_falls_back_to_vision_for_reverse_registration():
    import tunnel_config_builder

    node = tunnel_node_with_blank_flow()
    portal_cfg = tunnel_config_builder.build_portal_config(base_xray_config(), [node])
    vless = next(item for item in portal_cfg["inbounds"] if item["tag"] == "vless-reality-in")
    reverse_client = next(client for client in vless["settings"]["clients"] if client.get("email") == "tunnel:macmini")
    assert reverse_client["flow"] == "xtls-rprx-vision"

    bridge_cfg = tunnel_config_builder.build_bridge_config(node, reality_profile())
    reverse = next(item for item in bridge_cfg["outbounds"] if item["tag"] == "tunnel-reverse-out")
    assert reverse["settings"]["flow"] == "xtls-rprx-vision"


def test_portal_route_precedes_private_ip_block_rules():
    import tunnel_config_builder

    base = base_xray_config()
    base["routing"]["rules"].append(
        {"type": "field", "ip": ["geoip:private"], "outboundTag": "block"}
    )
    cfg = tunnel_config_builder.build_portal_config(base, [tunnel_node()])

    rules = cfg["routing"]["rules"]
    portal_index = rules.index(
        {
            "type": "field",
            "inboundTag": ["tunnel-portal-macmini"],
            "outboundTag": "tunnel-reverse-macmini",
        }
    )
    block_index = rules.index(
        {"type": "field", "ip": ["geoip:private"], "outboundTag": "block"}
    )
    assert portal_index < block_index


def test_build_portal_config_removes_deleted_tunnel_artifacts():
    import tunnel_config_builder

    current = tunnel_config_builder.build_portal_config(base_xray_config(), [tunnel_node()])
    cfg = tunnel_config_builder.build_portal_config(current, [])

    vless = next(item for item in cfg["inbounds"] if item["tag"] == "vless-reality-in")
    assert vless["settings"]["clients"] == [
        {"id": "22222222-2222-4222-8222-222222222222", "email": "panel-user:alice"}
    ]
    assert "tunnel-portal-macmini" not in [item["tag"] for item in cfg["inbounds"]]
    assert {
        "type": "field",
        "inboundTag": ["tunnel-portal-macmini"],
        "outboundTag": "tunnel-reverse-macmini",
    } not in cfg["routing"]["rules"]
