import api


def handle_get(handler):
    status, payload = api.handle_get(handler.path, handler.current_session())
    handler.respond_json(payload, status)


def handle_post(handler):
    try:
        status, payload = api.handle_post(handler.path, handler.read_json_or_form(), handler.current_session())
    except Exception as exc:
        status, payload = api.api_error(str(exc), 400)
    handler.respond_json(payload, status)
