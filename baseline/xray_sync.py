import json
import os
import shutil

import admin_profile
import node_catalog
from panel_config import (
    INBOUND_TAG,
    MANAGED_PREFIX,
    XRAY_BACKUP_DIR,
    XRAY_BIN,
    XRAY_CONFIG,
    XRAY_RESTART_CMD,
)
from sync_utils import backup_file, run, run_shell


def proxy_server_from_node(node):
    server = {
        "address": str(node.get("proxy_addr", "")).strip(),
        "port": int(node.get("proxy_port", 0) or 0),
    }
    user = str(node.get("proxy_user", "") or "").strip()
    password = str(node.get("proxy_password", "") or "").strip()
    if bool(user) != bool(password):
        raise RuntimeError(f"{node.get('id')} 代理用户名和密码需要同时填写，或同时留空。")
    if user and password:
        server["users"] = [{"user": user, "pass": password}]
    if not server["address"] or not server["port"]:
        raise RuntimeError(f"{node.get('id')} 代理地址和端口不能为空。")
    return server


def outbound_for_node(node):
    mode = node_catalog.outbound_mode(node)
    node_id = node.get("id", "")
    if mode == "direct":
        return None
    return {
        "tag": node_catalog.safe_outbound_tag(node_id),
        "protocol": "socks" if mode == "socks5" else "http",
        "settings": {"servers": [proxy_server_from_node(node)]},
    }


def sync_xray(users):
    cfg = json.loads(XRAY_CONFIG.read_text(encoding="utf-8"))

    inbound = None
    for item in cfg.get("inbounds", []):
        if item.get("tag") == INBOUND_TAG:
            inbound = item
            break

    if inbound is None:
        raise RuntimeError(f"未找到 Xray 入站 tag={INBOUND_TAG}")

    clients = inbound.setdefault("settings", {}).setdefault("clients", [])
    clients = [
        c for c in clients
        if not str(c.get("email", "")).startswith(MANAGED_PREFIX)
    ]

    default_flow = ""
    for c in inbound["settings"].get("clients", []):
        if c.get("flow"):
            default_flow = c.get("flow")
            break

    vless_nodes = node_catalog.vless_nodes(include_disabled=False)
    if not vless_nodes:
        vless_nodes = [node_catalog.DEFAULT_NODES[0]]

    all_users = dict(users)
    all_users[admin_profile.ADMIN_USERNAME] = admin_profile.get_admin_user()

    for username, u in all_users.items():
        for node in node_catalog.nodes_for_user(u, kind="vless", include_disabled=False):
            node_id = node.get("id", "")
            uuid = node_catalog.vless_uuid_for_user(u, node_id)
            if not uuid:
                continue
            item = {
                "id": uuid,
                "email": node_catalog.vless_node_email(username, node_id),
            }
            if default_flow:
                item["flow"] = default_flow
            clients.append(item)

    inbound["settings"]["clients"] = clients
    cfg.setdefault("outbounds", [])
    cfg.setdefault("routing", {})
    cfg["routing"].setdefault("domainStrategy", "IPIfNonMatch")
    cfg["routing"].setdefault("rules", [])

    managed_tags = {node_catalog.safe_outbound_tag(n.get("id", "")) for n in node_catalog.vless_nodes(include_disabled=True)}
    cfg["outbounds"] = [
        o for o in cfg.get("outbounds", [])
        if o.get("tag") not in managed_tags and o.get("tag") != "webshare-out"
    ]

    if not any(o.get("tag") == "direct" for o in cfg["outbounds"]):
        cfg["outbounds"].append({"tag": "direct", "protocol": "freedom", "settings": {"domainStrategy": "UseIPv4"}})
    if not any(o.get("tag") == "block" for o in cfg["outbounds"]):
        cfg["outbounds"].append({"tag": "block", "protocol": "blackhole"})

    direct = [o for o in cfg["outbounds"] if o.get("tag") == "direct"]
    block = [o for o in cfg["outbounds"] if o.get("tag") == "block"]
    others = [o for o in cfg["outbounds"] if o.get("tag") not in ("direct", "block")]
    proxy_outbounds = []
    for node in node_catalog.vless_nodes(include_disabled=False):
        out = outbound_for_node(node)
        if out:
            proxy_outbounds.append(out)
    cfg["outbounds"] = direct + proxy_outbounds + others + block

    new_rules = []
    for rule in cfg["routing"].get("rules", []):
        inbound_tags = rule.get("inboundTag", [])
        if isinstance(inbound_tags, str):
            inbound_tags = [inbound_tags]
        outbound = rule.get("outboundTag", "")
        if INBOUND_TAG in inbound_tags:
            continue
        if outbound in managed_tags or outbound == "webshare-out":
            continue
        new_rules.append(rule)

    new_rules.append({"type": "field", "inboundTag": [INBOUND_TAG], "network": "udp", "outboundTag": "block"})

    for username, u in all_users.items():
        for node in node_catalog.nodes_for_user(u, kind="vless", include_disabled=False):
            node_id = node.get("id", "")
            if not node_catalog.vless_uuid_for_user(u, node_id):
                continue
            tag = "direct" if node_catalog.outbound_mode(node) == "direct" else node_catalog.safe_outbound_tag(node_id)
            new_rules.append({
                "type": "field",
                "inboundTag": [INBOUND_TAG],
                "user": [node_catalog.vless_node_email(username, node_id)],
                "outboundTag": tag,
            })

    new_rules.append({"type": "field", "inboundTag": [INBOUND_TAG], "outboundTag": "direct"})
    cfg["routing"]["rules"] = new_rules

    old = XRAY_CONFIG.read_text(encoding="utf-8")
    new = json.dumps(cfg, indent=2, ensure_ascii=False)

    if old.strip() == new.strip():
        print("Xray 无变化")
        return False

    backup = backup_file(XRAY_CONFIG, XRAY_BACKUP_DIR, "enforce-users")
    XRAY_CONFIG.write_text(new, encoding="utf-8")
    os.chmod(XRAY_CONFIG, 0o640)

    code, out = run([XRAY_BIN, "run", "-test", "-config", str(XRAY_CONFIG)], timeout=60)
    if code != 0:
        shutil.copy2(backup, XRAY_CONFIG)
        raise RuntimeError("Xray 配置测试失败，已回滚：\n" + out)

    code, out = run_shell(XRAY_RESTART_CMD, timeout=60)
    if code != 0:
        shutil.copy2(backup, XRAY_CONFIG)
        run_shell(XRAY_RESTART_CMD, timeout=60)
        raise RuntimeError("Xray 重启失败，已回滚：\n" + out)

    print(f"Xray 已同步，有效托管用户数：{len(users)}，管理员订阅已同步")
    return True
