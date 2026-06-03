import subscription_routes


def handle_subscription_qr(handler):
    try:
        handler.respond_bytes(subscription_routes.subscription_qr_png(handler.path), "image/png")
    except Exception as exc:
        handler.respond_text("Invalid QR: " + str(exc), 403)


def handle_subscription(handler):
    token = ""
    try:
        fallback_ip = handler.client_address[0] if handler.client_address else ""
        status, body, headers, token = subscription_routes.build_subscription_http_response(handler.path, dict(handler.headers), fallback_ip)
        if status != 200:
            handler.respond_text(body, status)
            return
        handler.respond_text_with_headers(body, headers, 200)
    except Exception as exc:
        subscription_routes.log_subscription_error(
            handler.path,
            dict(handler.headers),
            handler.client_address[0] if handler.client_address else "",
            token,
        )
        handler.respond_text("Invalid subscription: " + str(exc), 403)
