import base64
import hashlib
import secrets


def b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def make_password_hash(password: str):
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200000)
    return {
        "salt": b64e(salt),
        "hash": b64e(dk),
        "iterations": 200000,
    }
