import auth_store
import simple_pages
from panel_config import SESSION_TTL


def handle_logout(handler):
    handler.send_response(302)
    handler.send_header("Set-Cookie", "panel_session=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax")
    handler.send_header("Location", "/login")
    handler.end_headers()


def handle_login_post(handler):
    data = handler.read_post()
    username = data.get("username", [""])[0].strip()
    password = data.get("password", [""])[0]
    role = auth_store.authenticate_user(username, password)
    if role:
        token = auth_store.make_session(username, role)
        handler.send_response(302)
        handler.send_header("Set-Cookie", f"panel_session={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={SESSION_TTL}")
        handler.send_header("Location", "/" if role == "admin" else "/links")
        handler.end_headers()
        return
    handler.respond(simple_pages.login(error="账号或密码错误。"))


def forbidden(handler):
    handler.respond(simple_pages.forbidden(), 403)
