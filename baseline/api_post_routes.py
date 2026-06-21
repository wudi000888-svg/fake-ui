import urllib.parse

import api_v2_routes
import operations_service as ops
from api_agent_routes import handle_agent_post
from api_admin_routes import handle_admin_post
from api_common import ok, require_admin
from api_node_routes import handle_node_post
from api_payment_routes import handle_payment_post, is_admin
from api_public_routes import handle_public_post
from api_self_routes import handle_self_post
from api_tunnel_routes import handle_tunnel_post
from api_user_routes import handle_user_post
from http_utils import api_error


def handle_post(path, data, session):
    clean = urllib.parse.urlparse(path).path

    public_result = handle_public_post(clean, data)
    if public_result is not None:
        return public_result

    agent_result = handle_agent_post(clean, data)
    if agent_result is not None:
        return agent_result

    if not session:
        return api_error("not authenticated", 401)

    v2_result = api_v2_routes.handle_post(clean, data, session)
    if v2_result is not None:
        return v2_result

    self_result = handle_self_post(clean, data, session)
    if self_result is not None:
        return self_result

    if clean == "/api/settings":
        if (err := require_admin(session)):
            return err
        result = ops.update_settings(data)
        result["clear_session"] = True
        return ok(**result)

    if clean == "/api/public-settings":
        if (err := require_admin(session)):
            return err
        return ok(public_settings=ops.update_public_settings(data))

    if clean == "/api/email-settings":
        if (err := require_admin(session)):
            return err
        if "password_reset_enabled" in (data or {}):
            ops.update_public_settings({"password_reset_enabled": data.get("password_reset_enabled")})
        email_public = ops.update_email_settings(data)
        return ok(email_settings=email_public, public_settings=ops.get_public_settings())

    if not is_admin(session):
        if clean in {"/api/orders/create", "/api/orders/action"}:
            return handle_user_post(clean, data, session)
        payment_result = handle_payment_post(clean, data, session)
        if payment_result is not None:
            return payment_result
        return api_error("forbidden", 403)

    for handler in (handle_admin_post, handle_user_post, handle_node_post, handle_tunnel_post, handle_payment_post):
        result = handler(clean, data, session)
        if result is not None:
            return result

    return api_error("not found", 404)
