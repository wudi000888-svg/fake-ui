import admin_profile
import audit_log
import node_catalog
import operations_service as ops
import user_admin
import user_store
from api_common import ok


def handle_node_post(clean, data, session):
    if clean == "/api/nodes/save":
        previous = None
        try:
            previous = node_catalog.get_node(data.get("id", ""))
        except Exception:
            previous = None
        node = node_catalog.upsert_node(data)
        try:
            node = node_catalog.upsert_node(ops.apply_node_exit_info(node))
        except Exception:
            if previous:
                node_catalog.upsert_node(previous)
            else:
                try:
                    node_catalog.delete_node(node.get("id", ""))
                except Exception:
                    pass
            raise
        user_admin.enforce_users_now()
        audit_log.write(session.get("u", "admin"), "node.save", node.get("id", ""), node)
        return ok(node=node_catalog.public_node(node, admin=True), nodes=node_catalog.list_public_nodes(admin=True))

    if clean == "/api/nodes/add-vless":
        node = node_catalog.create_default_vless_node()
        try:
            node = node_catalog.upsert_node(ops.apply_node_exit_info(node))
        except Exception:
            node_catalog.delete_node(node.get("id", ""))
            raise
        user_admin.enforce_users_now()
        audit_log.write(session.get("u", "admin"), "node.add_vless", node.get("id", ""), node)
        return ok(node=node_catalog.public_node(node, admin=True), nodes=node_catalog.list_public_nodes(admin=True))

    if clean == "/api/nodes/action":
        action = data.get("action", "")
        node_id = data.get("id", "")
        if action == "delete":
            node = node_catalog.delete_node(node_id)
            user_store.remove_vless_node_uuid(node_id)
            admin_profile.remove_vless_node_uuid(node_id)
        elif action == "refresh":
            node = node_catalog.upsert_node(ops.apply_node_exit_info(node_catalog.get_node(node_id)))
        elif action in ("enable", "disable"):
            node = node_catalog.set_node_enabled(node_id, action == "enable")
        else:
            raise RuntimeError("unknown node action")
        user_admin.enforce_users_now()
        audit_log.write(session.get("u", "admin"), "node." + action, node_id)
        return ok(node=node_catalog.public_node(node, admin=True), nodes=node_catalog.list_public_nodes(admin=True))

    return None
