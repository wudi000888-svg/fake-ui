from http_utils import api_error


def require_admin(session):
    if not session:
        return api_error("not authenticated", 401)
    if (session.get("role") or session.get("r")) != "admin":
        return api_error("forbidden", 403)
    return None


def ok(**payload):
    return 200, {"ok": True, **payload}
