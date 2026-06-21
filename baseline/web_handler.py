import json
import urllib.parse
from http import cookies
from http.server import BaseHTTPRequestHandler

import api
import auth_store
import http_api_routes
import http_auth_routes
import http_legacy_ui_routes
import http_qr_routes
import http_static_routes
import http_subscription_routes
import security


def cache_control_for_path(path):
    clean = urllib.parse.urlparse(path).path
    if clean.startswith("/assets/") or clean in {"/favicon.ico", "/favicon.svg"}:
        return "no-cache"
    return "no-store"


class PanelRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def read_post(self):
        length = int(self.headers.get("Content-Length", "0"))
        data = self.rfile.read(length).decode("utf-8", errors="ignore")
        return urllib.parse.parse_qs(data)

    def read_json_or_form(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8", errors="ignore")
        ctype = self.headers.get("Content-Type", "")
        if "application/json" in ctype:
            try:
                return json.loads(raw or "{}")
            except Exception:
                return {}
        parsed = urllib.parse.parse_qs(raw)
        return {k: v[0] if v else "" for k, v in parsed.items()}

    def respond(self, content, status=200):
        raw = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_security_headers("text/html")
        self.end_headers()
        self.wfile.write(raw)

    def respond_json(self, payload, status=200):
        token = payload.get("token") if isinstance(payload, dict) else None
        if token:
            session = auth_store.session_payload(token) or {}
            csrf = security.csrf_token_for_session(session)
            payload.setdefault("csrf_token", csrf)
        raw = api.json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        if token:
            self.send_header("Set-Cookie", security.session_cookie(token))
            self.send_header("Set-Cookie", security.csrf_cookie(payload.get("csrf_token", "")))
        if isinstance(payload, dict) and payload.get("clear_session"):
            self.send_header("Set-Cookie", security.clear_session_cookie())
            self.send_header("Set-Cookie", "panel_csrf=; Path=/; Max-Age=0; Secure; SameSite=Lax")
        self.send_security_headers("application/json")
        self.end_headers()
        self.wfile.write(raw)

    def respond_file(self, path):
        try:
            raw = path.read_bytes()
        except FileNotFoundError:
            self.respond_text("not found", 404)
            return
        self.send_response(200)
        self.send_header("Content-Type", api.content_type(path))
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", cache_control_for_path(self.path))
        self.send_security_headers(api.content_type(path))
        self.end_headers()
        self.wfile.write(raw)

    def respond_text(self, content, status=200):
        raw = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_security_headers("text/plain")
        self.end_headers()
        self.wfile.write(raw)

    def respond_text_with_headers(self, content, headers=None, status=200):
        headers = headers or {}
        raw = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_security_headers("text/plain")
        for k, v in headers.items():
            self.send_header(str(k), str(v).encode("ascii", "ignore").decode("ascii"))
        self.end_headers()
        self.wfile.write(raw)

    def respond_bytes(self, content, content_type, headers=None):
        headers = headers or {}
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_security_headers(content_type)
        for k, v in headers.items():
            self.send_header(str(k), str(v).encode("ascii", "ignore").decode("ascii"))
        self.end_headers()
        self.wfile.write(content)

    def redirect(self, location):
        self.send_response(302)
        self.send_header("Location", location)
        self.send_security_headers()
        self.end_headers()

    def send_security_headers(self, content_type=""):
        for k, v in security.security_headers(content_type).items():
            self.send_header(k, v)

    def get_cookie_token(self):
        c = cookies.SimpleCookie(self.headers.get("Cookie", ""))
        morsel = c.get("panel_session")
        return morsel.value if morsel else ""

    def current_session(self):
        return auth_store.session_payload(self.get_cookie_token())

    def current_role(self):
        p = self.current_session()
        return p.get("role") if p else ""

    def current_username(self):
        p = self.current_session()
        return p.get("u") if p else ""

    def require_login(self):
        if not self.current_session():
            self.redirect("/login")
            return False
        return True

    def is_admin(self):
        return self.current_role() == "admin"

    def forbidden(self):
        http_auth_routes.forbidden(self)

    def do_GET(self):
        if self.path == "/logout":
            http_auth_routes.handle_logout(self)
            return

        if self.path.startswith("/api/"):
            http_api_routes.handle_get(self)
            return

        if self.path.startswith("/qrsub/"):
            http_subscription_routes.handle_subscription_qr(self)
            return

        if self.path.startswith("/payqr/"):
            http_qr_routes.handle_payment_qr(self)
            return

        if self.path.startswith("/sub/"):
            http_subscription_routes.handle_subscription(self)
            return

        if http_static_routes.handle_frontend(self):
            return

        if self.path.startswith("/uqr/"):
            http_qr_routes.handle_user_node_qr(self)
            return

        if self.path.startswith("/qr/"):
            http_qr_routes.handle_admin_node_qr(self, self.current_username(), self.current_role())
            return

        http_legacy_ui_routes.handle_get(self)

    def do_POST(self):
        if self.path.startswith("/api/"):
            http_api_routes.handle_post(self)
            return

        if self.path == "/login":
            http_auth_routes.handle_login_post(self)
            return

        http_legacy_ui_routes.handle_post(self)


Handler = PanelRequestHandler
