import node_catalog
import traffic_stats


def get_xray_user_stat_snapshot(username, user):
    stats = traffic_stats.query_xray_stats()
    uplink = 0
    downlink = 0
    for node in node_catalog.nodes_for_user(user, kind="vless", include_disabled=True):
        email = node_catalog.vless_node_email(username, node.get("id", ""))
        uplink += int(stats.get(f"user>>>{email}>>>traffic>>>uplink", 0) or 0)
        downlink += int(stats.get(f"user>>>{email}>>>traffic>>>downlink", 0) or 0)
    return {"uplink": uplink, "downlink": downlink}


def get_hy2_user_stat_snapshot(username, user=None):
    hy2_stats = traffic_stats.query_hy2_stats()
    hy_user = (user or {}).get("hy2_username") or username
    item = hy2_stats.get(hy_user) or {}
    return {
        "tx": int(item.get("tx", 0) or 0),
        "rx": int(item.get("rx", 0) or 0),
    }
