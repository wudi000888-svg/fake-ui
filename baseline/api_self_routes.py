import operations_service as ops
import user_admin
from api_common import ok


def handle_self_post(clean, data, session):
    if clean == "/api/logout":
        return ok(clear_session=True)

    if clean == "/api/self/password":
        username = session.get("u", "")
        user_admin.user_self_update_password(username, data.get("old_password", ""), data.get("new_password", ""))
        return ok(message="password updated")

    if clean == "/api/self/email":
        username = session.get("u", "")
        profile = user_admin.update_user_email(username, data.get("email", ""), operator=username)
        return ok(message="email updated", profile=profile)

    if clean == "/api/self/reset-subscription":
        username = session.get("u", "")
        token = user_admin.reset_user_subscription(username, operator=username)
        return ok(sub_token=token, links=ops.user_links(username))

    return None
