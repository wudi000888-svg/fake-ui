import audit_log
import backup_manager
import hy2_panel
import node_catalog
import operations_service as ops
import plans_store
import xray_panel
from api_common import ok


def handle_admin_post(clean, data, session):
    if clean == "/api/xray/apply":
        return ok(
            result=xray_panel.apply_proxy(
                data.get("addr", ""),
                data.get("port", ""),
                data.get("user", ""),
                data.get("password", ""),
                data.get("proxy_type", "http"),
            )
        )

    if clean == "/api/xray/disable":
        return ok(result=xray_panel.disable_proxy())

    if clean == "/api/hy2/apply":
        result = hy2_panel.hy2_apply_proxy(
            data.get("addr", ""),
            data.get("port", ""),
            data.get("user", ""),
            data.get("password", ""),
            data.get("proxy_type", "http"),
        )
        node = node_catalog.upsert_node(ops.apply_node_exit_info(node_catalog.get_node("hy2-main")))
        audit_log.write(session.get("u", "admin"), "hy2.apply", "hy2-main", node)
        return ok(result=result, node=node_catalog.public_node(node, admin=True))

    if clean == "/api/hy2/disable":
        result = hy2_panel.hy2_disable_proxy()
        node = node_catalog.upsert_node(ops.apply_node_exit_info(node_catalog.get_node("hy2-main")))
        audit_log.write(session.get("u", "admin"), "hy2.disable", "hy2-main", node)
        return ok(result=result, node=node_catalog.public_node(node, admin=True))

    if clean == "/api/plans/save":
        plan = plans_store.upsert_plan(data)
        audit_log.write(session.get("u", "admin"), "plan.save", plan.get("id", ""), plan)
        return ok(plan=plan, plans=plans_store.list_plans())

    if clean == "/api/plans/action":
        action = data.get("action", "")
        plan_id = data.get("id", "")
        if action == "enable":
            plan = plans_store.set_plan_enabled(plan_id, True)
        elif action == "disable":
            plan = plans_store.set_plan_enabled(plan_id, False)
        elif action == "delete":
            plans_store.delete_plan(plan_id)
            plan = {"id": plan_id}
        else:
            raise RuntimeError("unknown plan action")
        audit_log.write(session.get("u", "admin"), "plan." + action, plan_id)
        return ok(plan=plan, plans=plans_store.list_plans())

    if clean == "/api/backups/create":
        backup = backup_manager.create_backup(reason=data.get("reason", "manual"))
        audit_log.write(session.get("u", "admin"), "backup.create", backup.get("path", ""))
        return ok(backup=backup, backups=backup_manager.list_backups(100))

    return None
