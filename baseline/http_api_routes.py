import api
import security


PUBLIC_POSTS = {
    "/api/login",
    "/api/register",
    "/api/password-reset/send-code",
    "/api/password-reset/confirm",
}


def handle_get(handler):
    try:
        status, payload = api.handle_get(handler.path, handler.current_session())
    except Exception as exc:
        status, payload = api.api_error(str(exc), 400)
    if status == 200 and isinstance(payload, dict) and isinstance(payload.get("content"), (bytes, bytearray)):
        filename = payload.get("filename") or "fake-ui-backup.tgz"
        handler.respond_bytes(
            payload.get("content"),
            payload.get("content_type") or "application/octet-stream",
            {"Content-Disposition": f'attachment; filename="{filename}"'},
        )
        return
    handler.respond_json(payload, status)


def handle_post(handler):
    try:
        session = handler.current_session()
        csrf_error = None
        if handler.path not in PUBLIC_POSTS:
            csrf_error = security.csrf_error_for(handler, session)
        if csrf_error is not None:
            status, payload = csrf_error
        else:
            data = handler.read_json_or_form()
            if handler.path == "/api/login" and isinstance(data, dict):
                data["_request_remote_ip"] = getattr(handler, "client_address", [""])[0]
                data["_request_forwarded_for"] = handler.headers.get("X-Forwarded-For", "")
            status, payload = api.handle_post(handler.path, data, session)
    except Exception as exc:
        status, payload = api.api_error(str(exc), 400)
    handler.respond_json(payload, status)
