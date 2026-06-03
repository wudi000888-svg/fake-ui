import api


def handle_frontend(handler):
    frontend_file = api.frontend_file_for_path(handler.path)
    if frontend_file is None:
        return False
    handler.respond_file(frontend_file)
    return True
