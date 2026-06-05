import geo_utils
import hy2_panel
import node_catalog


def apply_node_exit_info(node):
    kind = node.get("kind")
    if kind == "hy2":
        mode = hy2_panel.hy2_outbound_mode()
        if mode == "direct":
            info = geo_utils.direct_exit_info()
        else:
            proxy = hy2_panel.hy2_proxy_endpoint()
            if not proxy.get("addr") or not proxy.get("port"):
                raise RuntimeError("Hysteria2 代理配置缺少地址或端口，无法检测出口。")
            info = geo_utils.proxy_exit_info(
                proxy.get("addr", ""),
                int(proxy.get("port", 0) or 0),
                proxy.get("user", ""),
                proxy.get("password", ""),
                proxy.get("type", mode),
            )
        node["outbound_mode"] = mode
    elif kind == "vless":
        mode = node_catalog.outbound_mode(node)
        if mode == "direct":
            info = geo_utils.direct_exit_info()
        else:
            info = geo_utils.proxy_exit_info(
                node.get("proxy_addr", ""),
                int(node.get("proxy_port", 0) or 0),
                node.get("proxy_user", ""),
                node.get("proxy_password", ""),
                mode,
            )
    else:
        return node
    node["exit_ip"] = info.get("ip", "")
    node["proxy_test_ip"] = info.get("ip", "") if kind == "vless" and mode != "direct" else ""
    node["country_code"] = info.get("country_code", "")
    node["country"] = info.get("country", "")
    node["city"] = info.get("city", "")
    node["region"] = info.get("country_code") or node.get("region", "")
    if node.get("exit_ip"):
        node["name"] = node_catalog.display_name_for_node(node, node.get("name", ""))
    return node
