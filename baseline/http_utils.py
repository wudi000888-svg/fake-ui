import json
import urllib.parse
from pathlib import Path

from panel_config import PANEL_DIR


FRONTEND_DIR = PANEL_DIR / "frontend"
if not FRONTEND_DIR.exists():
    FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"


SPA_ROUTES = {
    "/",
    "/login",
    "/links",
    "/users",
    "/hysteria2",
    "/settings",
    "/plans",
    "/orders",
    "/nodes",
    "/audit",
    "/backups",
    "/account",
    "/register",
    "/forgot",
    "/requests",
    "/sub-access",
}


def json_bytes(payload):
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def api_error(message, status=400):
    return status, {"ok": False, "error": str(message)}


def frontend_file_for_path(path):
    clean = urllib.parse.urlparse(path).path
    if clean in SPA_ROUTES:
        return FRONTEND_DIR / "index.html"
    if clean.startswith("/assets/"):
        rel = clean.lstrip("/")
        candidate = (FRONTEND_DIR / rel).resolve()
        root = FRONTEND_DIR.resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            return None
        return candidate
    return None


def content_type(path):
    suffix = Path(path).suffix.lower()
    if suffix == ".html":
        return "text/html; charset=utf-8"
    if suffix == ".css":
        return "text/css; charset=utf-8"
    if suffix == ".js":
        return "application/javascript; charset=utf-8"
    if suffix == ".svg":
        return "image/svg+xml"
    return "application/octet-stream"

