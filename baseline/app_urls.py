from panel_config import PUBLIC_BASE_URL


def absolute_url(path):
    path = str(path or "")
    if path.startswith("http://") or path.startswith("https://"):
        return path
    if not path.startswith("/"):
        path = "/" + path
    return PUBLIC_BASE_URL.rstrip("/") + path


def subscription_path(token, mode=""):
    token = str(token or "").strip()
    path = f"/sub/{token}"
    mode = str(mode or "").strip().strip("/")
    if mode:
        path += f"/{mode}"
    return path


def subscription_url(token, mode=""):
    return absolute_url(subscription_path(token, mode))


def subscription_qr_path(token, mode=""):
    token = str(token or "").strip()
    path = f"/qrsub/{token}"
    mode = str(mode or "").strip().strip("/")
    if mode:
        path += f"/{mode}"
    return path

