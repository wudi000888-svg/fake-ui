import audit_log
import operations_service as ops
import orders_store
import plans_store
import registration_store
import user_admin
import user_store
from api_common import ok


def handle_user_post(clean, data, session):
    if clean == "/api/orders/create":
        role = session.get("role") or session.get("r")
        username = data.get("username", "").strip() if role == "admin" else session.get("u", "")
        if not username:
            username = session.get("u", "")
        plan = plans_store.get_plan(data.get("plan_id", ""))
        if not plan:
            raise RuntimeError("plan not found")
        order = orders_store.create_pending_order(username, data.get("kind", "renew"), plan, note=data.get("note", ""), operator=session.get("u", username))
        audit_log.write(session.get("u", username), "order.create", order.get("id", ""), {"username": username, "plan_id": plan.get("id")})
        return ok(order=order, orders=orders_store.list_orders(username=None if role == "admin" else username))

    if clean == "/api/users/create":
        result = user_admin.create_airport_user(
            data.get("username", ""),
            data.get("days", "30"),
            data.get("note", ""),
            data.get("panel_password", ""),
            data.get("traffic_gb", "0"),
            data.get("plan_id", ""),
            session.get("u", "admin"),
        )
        return ok(result=result, users=ops.list_users())

    if clean == "/api/users/action":
        user_admin.airport_user_action(
            data.get("username", ""),
            data.get("action", ""),
            data.get("days", "30"),
            data.get("quota_gb", ""),
            data.get("plan_id", ""),
            session.get("u", "admin"),
            data.get("node_ids", ""),
        )
        return ok(users=ops.list_users())

    if clean == "/api/users/reset-subscription":
        token = user_admin.reset_user_subscription(data.get("username", ""), operator=session.get("u", "admin"))
        return ok(sub_token=token, users=ops.list_users())

    if clean == "/api/orders/action":
        action = data.get("action", "")
        order_id = data.get("id", "")
        if action == "confirm":
            result = user_admin.confirm_order(order_id, operator=session.get("u", "admin"))
        elif action == "cancel":
            result = user_admin.cancel_order(order_id, operator=session.get("u", "admin"))
        else:
            raise RuntimeError("unknown order action")
        return ok(result=result, orders=orders_store.list_orders(limit=200), users=ops.list_users())

    if clean == "/api/registrations/action":
        action = data.get("action", "")
        token = data.get("token", "")
        if action == "approve":
            result = user_admin.approve_registration(token, operator=session.get("u", "admin"))
        elif action == "reject":
            result = user_admin.reject_registration(token, operator=session.get("u", "admin"))
        else:
            raise RuntimeError("unknown registration action")
        return ok(result=result, registrations=registration_store.list_registrations(), users=ops.list_users())

    if clean == "/api/password-reset/action":
        action = data.get("action", "")
        token = data.get("token", "")
        if action == "approve":
            result = user_admin.approve_password_reset(token, data.get("new_password", ""), operator=session.get("u", "admin"))
        elif action == "reject":
            result = user_admin.reject_password_reset(token, operator=session.get("u", "admin"))
        else:
            raise RuntimeError("unknown reset action")
        return ok(result=result, password_resets=registration_store.list_resets())

    return None
