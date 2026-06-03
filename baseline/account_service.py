import secrets

import auth_store


def update_settings(data):
    old_password = data.get("old_password", "")
    admin_username = data.get("admin_username", "").strip()
    admin_password = data.get("admin_password", "")
    viewer_username = data.get("viewer_username", "").strip()
    viewer_password = data.get("viewer_password", "")

    auth, users = auth_store.get_auth_users()
    admin_old_user = next((u for u, rec in users.items() if rec.get("role") == "admin"), None)
    admin_old_rec = users.get(admin_old_user) if admin_old_user else None
    viewer_old_user = next((u for u, rec in users.items() if rec.get("role") == "user"), None)
    viewer_old_rec = users.get(viewer_old_user) if viewer_old_user else None

    if not admin_old_rec or not auth_store.verify_password(old_password, admin_old_rec["password"]):
        raise RuntimeError("current administrator password is incorrect")
    if not admin_username or not viewer_username or admin_username == viewer_username:
        raise RuntimeError("admin and viewer usernames must be non-empty and different")
    if admin_password and len(admin_password) < 8:
        raise RuntimeError("new administrator password must be at least 8 characters")
    if viewer_password and len(viewer_password) < 8:
        raise RuntimeError("new viewer password must be at least 8 characters")

    admin_hash = auth_store.make_password_hash(admin_password) if admin_password else admin_old_rec["password"]
    viewer_hash = (
        auth_store.make_password_hash(viewer_password)
        if viewer_password
        else (viewer_old_rec["password"] if viewer_old_rec else auth_store.make_password_hash(secrets.token_urlsafe(14)))
    )

    auth["users"] = {
        admin_username: {"role": "admin", "password": admin_hash},
        viewer_username: {"role": "user", "password": viewer_hash},
    }
    auth["session_secret"] = secrets.token_urlsafe(32)
    auth_store.save_auth(auth)
    return {"message": "settings updated"}

