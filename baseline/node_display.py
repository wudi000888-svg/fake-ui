def display_name_for_node(node, fallback):
    if not node:
        return fallback
    exit_ip = str(node.get("exit_ip") or node.get("proxy_test_ip") or "").strip()
    country_code = str(node.get("country_code") or node.get("region") or "").strip()
    if exit_ip:
        return f"{country_code} - {exit_ip}" if country_code else exit_ip
    parts = []
    if node.get("region"):
        parts.append(str(node.get("region")))
    parts.append(str(node.get("name") or fallback))
    mult = float(node.get("multiplier", 1) or 1)
    if mult != 1:
        parts.append(f"x{mult:g}")
    status = node.get("status")
    if status and status != "online":
        parts.append(status)
    return " - ".join(parts)


def public_node(node, admin=False, outbound_mode_fn=None):
    item = dict(node)
    item["outbound_mode"] = outbound_mode_fn(item) if outbound_mode_fn else item.get("outbound_mode", "direct")
    item["proxy_password_set"] = bool(item.get("proxy_password"))
    item["display_name"] = display_name_for_node(item, item.get("name", ""))
    item["can_delete"] = bool(item.get("kind") == "vless" and item.get("id") != "vless-main")
    item.pop("proxy_password", None)
    if not admin:
        item.pop("proxy_user", None)
        item.pop("proxy_addr", None)
        item.pop("proxy_port", None)
        item.pop("proxy_test_ip", None)
    return item
