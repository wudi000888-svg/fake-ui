import simple_pages


def user_can_access_path(clean):
    return clean == "/links" or clean.startswith("/qr/") or clean.startswith("/uqr/") or clean.startswith("/qrsub/")


def handle_get(handler):
    handler.respond(simple_pages.not_found(), 404)


def handle_post(handler):
    handler.respond_text("Legacy form routes have been removed. Use /api/*.", 410)
