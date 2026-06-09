import os
import secrets
import uuid
from datetime import timedelta

import app_urls
from panel_config import AIRPORT_LOGIN_LOG, ENFORCE_USERS_CMD
import user_store
import audit_log
import orders_store
import plans_store
import registration_store
import node_catalog
import password_utils
import user_stats_service
from sync_utils import run_shell


def append_user_event_log(title, username, sub_token="", expires_at="", traffic_text="", password_generated=False):
    AIRPORT_LOGIN_LOG.write_text(
        AIRPORT_LOGIN_LOG.read_text(encoding="utf-8") if AIRPORT_LOGIN_LOG.exists() else "",
        encoding="utf-8",
    )
    with AIRPORT_LOGIN_LOG.open("a", encoding="utf-8") as f:
        f.write(f"\n===== {title} =====\n")
        f.write(f"Username: {username}\n")
        if password_generated:
            f.write("Panel Password: 已生成，仅在本次 API/页面响应中一次性返回，不再写入历史日志。\n")
        if sub_token:
            f.write(f"Subscribe: {app_urls.subscription_url(sub_token)}\n")
        if expires_at:
            f.write(f"Expires: {expires_at}\n")
        if traffic_text:
            f.write(f"Traffic: {traffic_text}\n")
    os.chmod(AIRPORT_LOGIN_LOG, 0o600)


def b64e(raw: bytes) -> str:
    return password_utils.b64e(raw)


def make_password_hash(password: str):
    return password_utils.make_password_hash(password)


def enforce_users_now():
    code, out = run_shell(ENFORCE_USERS_CMD, timeout=90)
    if code != 0:
        raise RuntimeError("同步用户到 Xray / Hysteria2 失败：\n" + out)
    return out


def normalize_node_ids(node_ids):
    if node_ids in ("", None):
        return []
    if isinstance(node_ids, str):
        items = [item.strip() for item in node_ids.replace("\n", ",").split(",")]
    else:
        items = [str(item).strip() for item in node_ids]
    valid_ids = {node.get("id") for node in node_catalog.list_nodes(include_disabled=True)}
    result = []
    for item in items:
        if not item:
            continue
        if item not in valid_ids:
            raise RuntimeError(f"节点不存在：{item}")
        if item not in result:
            result.append(item)
    return result


def get_xray_user_stat_snapshot(username):
    user = user_store.get_user(username) or {}
    return user_stats_service.get_xray_user_stat_snapshot(username, user)


def get_hy2_user_stat_snapshot(username, user=None):
    return user_stats_service.get_hy2_user_stat_snapshot(username, user)


def create_airport_user(
    username,
    days,
    note="",
    panel_password_input="",
    traffic_gb_input="0",
    plan_id="",
    operator="admin",
    panel_password_hash=None,
    reveal_password=True,
):
    username = username.strip()

    if not username:
        raise RuntimeError("用户名不能为空。")
    if not username.replace("_", "").replace("-", "").isalnum():
        raise RuntimeError("用户名只能包含字母、数字、下划线和短横线。")

    plan = plans_store.get_plan(plan_id) if plan_id else None
    if plan:
        days = plan.get("days", days)
        traffic_gb_input = plan.get("traffic_gb", traffic_gb_input)

    days = int(days)
    if days <= 0:
        raise RuntimeError("有效期天数必须大于 0。")

    quota_bytes = user_store.traffic_gb_to_bytes(traffic_gb_input)
    data = user_store.load_users()
    users = data.setdefault("users", {})

    if username in users:
        raise RuntimeError("用户已存在。")

    panel_password_input = panel_password_input.strip()
    if panel_password_hash:
        panel_password = ""
        stored_panel_password = panel_password_hash
    elif panel_password_input:
        if len(panel_password_input) < 8:
            raise RuntimeError("用户登录密码至少 8 位。")
        panel_password = panel_password_input
        stored_panel_password = make_password_hash(panel_password)
    else:
        panel_password = secrets.token_urlsafe(12)
        stored_panel_password = make_password_hash(panel_password)

    sub_token = secrets.token_hex(24)
    vless_uuid = str(uuid.uuid4())
    vless_node_uuids = {}
    for node in node_catalog.vless_nodes(include_disabled=True):
        node_id = node.get("id", "")
        if not node_id:
            continue
        vless_node_uuids[node_id] = vless_uuid if node_id == node_catalog.PRIMARY_VLESS_NODE_ID else str(uuid.uuid4())
    users[username] = {
        "enabled": True,
        "role": "user",
        "panel_password": stored_panel_password,
        "vless_uuid": vless_uuid,
        "vless_node_uuids": vless_node_uuids,
        "sub_token": sub_token,
        "expires_at": user_store.make_expiry(days),
        "created_at": user_store.now_utc().isoformat(),
        "note": note,
        "plan_id": plan.get("id", "") if plan else "",
        "node_groups": plan.get("node_groups", ["default"]) if plan else ["default"],
        "quota_bytes": quota_bytes,
        "used_bytes": 0,
        "quota_exceeded": False,
        "last_xray_stats": {"uplink": 0, "downlink": 0},
        "hy2_username": username,
        "hy2_password": secrets.token_urlsafe(18),
        "last_hy2_stats": {"tx": 0, "rx": 0},
    }

    user_store.save_users(data)
    enforce_users_now()
    orders_store.record_order(username, "create", plan=plan, amount=(plan or {}).get("price", 0), note="create user", operator=operator)
    audit_log.write(operator, "user.create", username, {"days": days, "traffic_gb": traffic_gb_input, "plan_id": (plan or {}).get("id", "")})

    append_user_event_log(
        "新增用户",
        username,
        sub_token=sub_token,
        expires_at=users[username]["expires_at"],
        traffic_text=user_store.bytes_to_gb_text(quota_bytes) if quota_bytes else "不限量",
        password_generated=True,
    )

    result = {
        "username": username,
        "sub_token": sub_token,
        "expires_at": users[username]["expires_at"],
        "quota_bytes": quota_bytes,
        "hy2_username": users[username]["hy2_username"],
        "hy2_password": users[username]["hy2_password"],
        "plan_id": users[username].get("plan_id", ""),
        "node_groups": users[username].get("node_groups", []),
    }
    if reveal_password:
        result["panel_password"] = panel_password
    return result


def create_self_registered_user(username, password_hash, email="", note="", operator="self-register"):
    username = str(username or "").strip()
    if not username:
        raise RuntimeError("用户名不能为空。")
    if not username.replace("_", "").replace("-", "").isalnum():
        raise RuntimeError("用户名只能包含字母、数字、下划线和短横线。")
    if not password_hash:
        raise RuntimeError("用户登录密码不能为空。")

    data = user_store.load_users()
    users = data.setdefault("users", {})
    if username in users:
        raise RuntimeError("用户已存在。")

    sub_token = secrets.token_hex(24)
    users[username] = {
        "enabled": True,
        "role": "user",
        "panel_password": password_hash,
        "vless_uuid": str(uuid.uuid4()),
        "vless_node_uuids": {},
        "sub_token": sub_token,
        "expires_at": "",
        "created_at": user_store.now_utc().isoformat(),
        "email": str(email or "").strip(),
        "note": note or f"self registration {email}".strip(),
        "plan_id": "",
        "node_groups": [],
        "node_ids": [],
        "quota_bytes": 0,
        "used_bytes": 0,
        "quota_exceeded": False,
        "last_xray_stats": {"uplink": 0, "downlink": 0},
        "hy2_username": username,
        "hy2_password": secrets.token_urlsafe(18),
        "last_hy2_stats": {"tx": 0, "rx": 0},
    }
    user_store.save_users(data)
    audit_log.write(operator, "user.self_register", username, {"email": email})
    return {"username": username, "sub_token": sub_token}


def update_user_email(username, email, operator=None):
    username = str(username or "").strip()
    email = str(email or "").strip()
    if email and ("@" not in email or len(email) > 254):
        raise RuntimeError("邮箱格式不正确。")

    data = user_store.load_users()
    users = data.setdefault("users", {})
    if username not in users:
        raise RuntimeError("用户不存在。")

    users[username]["email"] = email
    user_store.save_users(data)
    audit_log.write(operator or username, "user.email_update", username)
    return {"username": username, "email": email}


def airport_user_action(username, action, days="30", quota_gb="", plan_id="", operator="admin", node_ids=None):
    username = username.strip()
    data = user_store.load_users()
    users = data.setdefault("users", {})

    if username not in users:
        raise RuntimeError("用户不存在。")

    user = users[username]
    plan = plans_store.get_plan(plan_id) if plan_id else None

    if action == "disable":
        user["enabled"] = False
    elif action == "enable":
        user["enabled"] = True
        if int(user.get("quota_bytes", 0) or 0) > 0 and int(user.get("used_bytes", 0) or 0) < int(user.get("quota_bytes", 0) or 0):
            user["quota_exceeded"] = False
    elif action == "extend":
        if plan:
            days = plan.get("days", days)
            quota_gb = plan.get("traffic_gb", quota_gb)
            user["plan_id"] = plan.get("id", "")
            user["node_groups"] = plan.get("node_groups", user.get("node_groups", ["default"]))
        days_int = int(days)
        if days_int <= 0:
            raise RuntimeError("延长天数必须大于 0。")
        current_exp = user_store.parse_time(user.get("expires_at"))
        base = current_exp if current_exp and current_exp > user_store.now_utc() else user_store.now_utc()
        user["expires_at"] = (base + timedelta(days=days_int)).isoformat()
        user["enabled"] = True
        if quota_gb not in ("", None):
            user["quota_bytes"] = user_store.traffic_gb_to_bytes(quota_gb)
            user["quota_exceeded"] = False
    elif action == "set_quota":
        user["quota_bytes"] = user_store.traffic_gb_to_bytes(quota_gb)
        user["quota_exceeded"] = (
            int(user.get("quota_bytes", 0) or 0) > 0
            and int(user.get("used_bytes", 0) or 0) >= int(user.get("quota_bytes", 0) or 0)
        )
    elif action == "set_nodes":
        selected_ids = normalize_node_ids(node_ids)
        if selected_ids:
            user["node_ids"] = selected_ids
        else:
            user.pop("node_ids", None)
    elif action == "reset_traffic":
        user["used_bytes"] = 0
        user["quota_exceeded"] = False
        user["last_xray_stats"] = get_xray_user_stat_snapshot(username)
        user["last_hy2_stats"] = get_hy2_user_stat_snapshot(username, user)
    elif action == "reset":
        new_password = secrets.token_urlsafe(12)
        user["panel_password"] = make_password_hash(new_password)
        user["sub_token"] = secrets.token_hex(24)
        append_user_event_log(
            "重置用户",
            username,
            sub_token=user["sub_token"],
            expires_at=user.get("expires_at", ""),
            traffic_text=user_store.quota_text(user),
            password_generated=True,
        )
    elif action == "delete":
        users.pop(username)
        user_store.delete_user(username)
    else:
        raise RuntimeError("未知操作。")

    if action != "delete":
        user_store.save_users(data)
    enforce_users_now()
    if action in ("extend", "set_quota"):
        orders_store.record_order(username, action, plan=plan, amount=(plan or {}).get("price", 0), note=action, operator=operator)
    audit_log.write(operator, "user." + action, username, {"days": days, "quota_gb": quota_gb, "plan_id": plan_id, "node_ids": user.get("node_ids", [])})
    return True


def update_airport_user(username, updates, operator="admin"):
    username = str(username or "").strip()
    data = user_store.load_users()
    users = data.setdefault("users", {})

    if username not in users:
        raise RuntimeError("用户不存在。")

    user = users[username]
    plan_id = str((updates or {}).get("plan_id", "") or "").strip()
    plan = plans_store.get_plan(plan_id) if plan_id else None

    if plan_id:
        if not plan:
            raise RuntimeError("套餐不存在。")
        user["plan_id"] = plan.get("id", "")
        user["node_groups"] = plan.get("node_groups", ["default"])

    if "enabled" in updates:
        enabled = updates.get("enabled")
        if isinstance(enabled, str):
            enabled = enabled.lower() not in {"0", "false", "no", "off"}
        user["enabled"] = bool(enabled)

    if "note" in updates:
        user["note"] = str(updates.get("note") or "").strip()

    days = str(updates.get("days", "") or "").strip()
    if days:
        days_int = int(days)
        if days_int <= 0:
            raise RuntimeError("有效期天数必须大于 0。")
        user["expires_at"] = user_store.make_expiry(days_int)

    quota_gb = updates.get("quota_gb", None)
    if quota_gb in (None, "") and plan:
        quota_gb = plan.get("traffic_gb", "")
    if quota_gb not in (None, ""):
        user["quota_bytes"] = user_store.traffic_gb_to_bytes(quota_gb)
        user["quota_exceeded"] = (
            int(user.get("quota_bytes", 0) or 0) > 0
            and int(user.get("used_bytes", 0) or 0) >= int(user.get("quota_bytes", 0) or 0)
        )

    if "node_ids" in updates:
        selected_ids = normalize_node_ids(updates.get("node_ids"))
        if selected_ids:
            user["node_ids"] = selected_ids
        else:
            user.pop("node_ids", None)

    user_store.save_users(data)
    enforce_users_now()
    audit_log.write(
        operator,
        "user.update",
        username,
        {
            "plan_id": user.get("plan_id", ""),
            "node_groups": user.get("node_groups", []),
            "node_ids": user.get("node_ids", []),
            "quota_bytes": user.get("quota_bytes", 0),
            "enabled": user.get("enabled", True),
        },
    )
    return user


def user_self_update_password(username, old_password, new_password):
    if len(new_password or "") < 8:
        raise RuntimeError("new password must be at least 8 characters")
    data = user_store.load_users()
    user = data.get("users", {}).get(username)
    if not user:
        raise RuntimeError("user not found")
    import auth_store
    if not auth_store.verify_password(old_password, user.get("panel_password", {})):
        raise RuntimeError("current password is incorrect")
    user["panel_password"] = make_password_hash(new_password)
    user_store.save_users(data)
    audit_log.write(username, "self.password", username)
    return True


def reset_user_subscription(username, operator="admin"):
    data = user_store.load_users()
    user = data.get("users", {}).get(username)
    if not user:
        raise RuntimeError("user not found")
    user["sub_token"] = secrets.token_hex(24)
    user_store.save_users(data)
    audit_log.write(operator, "user.reset_subscription", username)
    return user["sub_token"]


def create_or_renew_from_plan(username, plan_id, password="", note="", operator="admin", password_hash=None, reveal_password=True):
    plan = plans_store.get_plan(plan_id)
    if not plan:
        raise RuntimeError("plan not found")
    existing = user_store.get_user(username)
    if existing:
        airport_user_action(username, "extend", plan_id=plan_id, operator=operator)
        return {"mode": "renew", "username": username}
    result = create_airport_user(
        username,
        plan.get("days", 30),
        note=note,
        panel_password_input=password,
        traffic_gb_input=plan.get("traffic_gb", 0),
        plan_id=plan_id,
        operator=operator,
        panel_password_hash=password_hash,
        reveal_password=reveal_password,
    )
    return {"mode": "create", **result}


def replace_subscription_from_plan(username, plan_id, operator="admin"):
    plan = plans_store.get_plan(plan_id)
    if not plan:
        raise RuntimeError("plan not found")
    username = str(username or "").strip()
    data = user_store.load_users()
    users = data.setdefault("users", {})
    user = users.get(username)
    if not user:
        result = create_airport_user(
            username,
            plan.get("days", 30),
            traffic_gb_input=plan.get("traffic_gb", 0),
            plan_id=plan_id,
            operator=operator,
        )
        return {"mode": "create", **result}

    user["enabled"] = True
    user["plan_id"] = plan.get("id", "")
    user["node_groups"] = plan.get("node_groups", ["default"])
    user.pop("node_ids", None)
    user["expires_at"] = user_store.make_expiry(plan.get("days", 30))
    user["quota_bytes"] = user_store.traffic_gb_to_bytes(plan.get("traffic_gb", 0))
    user["used_bytes"] = 0
    user["quota_exceeded"] = False
    user["last_xray_stats"] = get_xray_user_stat_snapshot(username)
    user["last_hy2_stats"] = get_hy2_user_stat_snapshot(username, user)
    user_store.save_users(data)
    enforce_users_now()
    orders_store.record_order(username, "replace", plan=plan, amount=plan.get("price", 0), note="replace subscription", operator=operator)
    audit_log.write(operator, "user.replace_plan", username, {"plan_id": plan_id})
    return {"mode": "replace", "username": username}


def confirm_order(order_id, operator="admin"):
    order = orders_store.get_order(order_id)
    if not order:
        raise RuntimeError("order not found")
    if order.get("status") != "pending":
        raise RuntimeError("order is not pending")
    plan_id = order.get("plan_id", "")
    if order.get("kind") in {"new", "create", "replace"}:
        result = replace_subscription_from_plan(order.get("username", ""), plan_id, operator=operator)
    else:
        result = create_or_renew_from_plan(order.get("username", ""), plan_id, note="manual order", operator=operator)
    orders_store.update_order(order_id, status="completed", confirmed_at=user_store.now_utc().isoformat(), confirmed_by=operator)
    audit_log.write(operator, "order.confirm", order_id, {"username": order.get("username"), "plan_id": plan_id})
    return result


def cancel_order(order_id, operator="admin"):
    order = orders_store.get_order(order_id)
    if not order:
        raise RuntimeError("order not found")
    if order.get("status") != "pending":
        raise RuntimeError("order is not pending")
    orders_store.update_order(order_id, status="cancelled", cancelled_at=user_store.now_utc().isoformat(), cancelled_by=operator)
    audit_log.write(operator, "order.cancel", order_id, {"username": order.get("username"), "plan_id": order.get("plan_id")})
    return True


def approve_registration(token, operator="admin"):
    item = registration_store.get_registration(token)
    if not item:
        raise RuntimeError("registration not found")
    if item.get("status") != "pending":
        raise RuntimeError("registration is not pending")
    result = create_or_renew_from_plan(
        item.get("username", ""),
        item.get("plan_id", "") or "starter",
        password=item.get("password", ""),
        password_hash=item.get("password_hash"),
        note=item.get("note", "registration"),
        operator=operator,
        reveal_password=bool(item.get("password")),
    )
    registration_store.update_registration(token, status="approved", approved_at=user_store.now_utc().isoformat(), approved_by=operator)
    audit_log.write(operator, "registration.approve", item.get("username", ""), {"token": token[:10]})
    return result


def reject_registration(token, operator="admin"):
    item = registration_store.get_registration(token)
    if not item:
        raise RuntimeError("registration not found")
    registration_store.update_registration(token, status="rejected", rejected_at=user_store.now_utc().isoformat(), rejected_by=operator)
    audit_log.write(operator, "registration.reject", item.get("username", ""), {"token": token[:10]})
    return True


def approve_password_reset(token, new_password="", operator="admin"):
    item = registration_store.get_reset(token)
    if not item:
        raise RuntimeError("reset request not found")
    if item.get("status") != "pending":
        raise RuntimeError("reset request is not pending")
    username = item.get("username", "")
    data = user_store.load_users()
    user = data.get("users", {}).get(username)
    if not user:
        raise RuntimeError("user not found")
    password = new_password or secrets.token_urlsafe(12)
    user["panel_password"] = make_password_hash(password)
    user_store.save_users(data)
    registration_store.update_reset(token, status="approved", approved_at=user_store.now_utc().isoformat(), approved_by=operator)
    audit_log.write(operator, "password_reset.approve", username, {"token": token[:10]})
    return {"username": username, "password": password}


def reject_password_reset(token, operator="admin"):
    item = registration_store.get_reset(token)
    if not item:
        raise RuntimeError("reset request not found")
    registration_store.update_reset(token, status="rejected", rejected_at=user_store.now_utc().isoformat(), rejected_by=operator)
    audit_log.write(operator, "password_reset.reject", item.get("username", ""), {"token": token[:10]})
    return True
