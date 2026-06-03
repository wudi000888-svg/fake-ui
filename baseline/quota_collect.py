#!/usr/bin/env python3
from datetime import datetime, timezone

import node_catalog
from traffic_stats import query_hy2_stats, query_xray_stats, to_int
import user_store


def xray_totals_for_user(stats, username, user):
    uplink = 0
    downlink = 0
    for node in node_catalog.nodes_for_user(user, kind="vless", include_disabled=True):
        email = node_catalog.vless_node_email(username, node.get("id", ""))
        uplink += to_int(stats.get(f"user>>>{email}>>>traffic>>>uplink", 0))
        downlink += to_int(stats.get(f"user>>>{email}>>>traffic>>>downlink", 0))
    return uplink, downlink


def main():
    data = user_store.load_users()
    users = data.setdefault("users", {})
    stats = query_xray_stats()
    hy2_stats = query_hy2_stats()

    changed = False

    for username, u in users.items():
        up_now, down_now = xray_totals_for_user(stats, username, u)

        last = u.setdefault("last_xray_stats", {})
        up_last = to_int(last.get("uplink", 0))
        down_last = to_int(last.get("downlink", 0))

        up_delta = up_now - up_last if up_now >= up_last else up_now
        down_delta = down_now - down_last if down_now >= down_last else down_now
        delta = max(0, up_delta) + max(0, down_delta)

        if delta > 0:
            u["used_bytes"] = to_int(u.get("used_bytes", 0)) + delta
            u["last_traffic_update"] = datetime.now(timezone.utc).isoformat()
            changed = True

        if last.get("uplink") != up_now or last.get("downlink") != down_now:
            last["uplink"] = up_now
            last["downlink"] = down_now
            changed = True

        hy_user = u.get("hy2_username") or username
        hy_now = hy2_stats.get(hy_user, {})
        hy_tx_now = to_int(hy_now.get("tx", 0))
        hy_rx_now = to_int(hy_now.get("rx", 0))

        hy_last = u.setdefault("last_hy2_stats", {})
        hy_tx_last = to_int(hy_last.get("tx", 0))
        hy_rx_last = to_int(hy_last.get("rx", 0))

        hy_tx_delta = hy_tx_now - hy_tx_last if hy_tx_now >= hy_tx_last else hy_tx_now
        hy_rx_delta = hy_rx_now - hy_rx_last if hy_rx_now >= hy_rx_last else hy_rx_now
        hy_delta = max(0, hy_tx_delta) + max(0, hy_rx_delta)

        if hy_delta > 0:
            u["used_bytes"] = to_int(u.get("used_bytes", 0)) + hy_delta
            u["last_traffic_update"] = datetime.now(timezone.utc).isoformat()
            changed = True

        if hy_last.get("tx") != hy_tx_now or hy_last.get("rx") != hy_rx_now:
            hy_last["tx"] = hy_tx_now
            hy_last["rx"] = hy_rx_now
            changed = True

        quota = to_int(u.get("quota_bytes", 0))
        used = to_int(u.get("used_bytes", 0))
        over = quota > 0 and used >= quota

        if u.get("quota_exceeded") != over:
            u["quota_exceeded"] = over
            changed = True

    if changed:
        user_store.save_users(data)

    print("quota collect ok")


if __name__ == "__main__":
    main()
