from process_utils import run


def proxy_auth_enabled(user, password):
    user = user.strip()
    password = password.strip()
    if bool(user) != bool(password):
        raise RuntimeError("代理用户名和密码需要同时填写；无认证代理请两项都留空。")
    return bool(user)


def normalize_proxy_type(proxy_type):
    proxy_type = (proxy_type or "http").strip().lower()
    if proxy_type not in ("http", "socks5"):
        raise RuntimeError("代理类型只支持 HTTP 或 SOCKS5。")
    return proxy_type


def test_proxy(addr, port, user, password, proxy_type="http"):
    proxy_type = normalize_proxy_type(proxy_type)
    proxy_scheme = "socks5h" if proxy_type == "socks5" else "http"
    cmd = [
        "curl",
        "-4sS",
        "--connect-timeout",
        "15",
        "--max-time",
        "30",
        "--proxy",
        f"{proxy_scheme}://{addr}:{port}",
    ]
    if proxy_auth_enabled(user, password):
        cmd += ["--proxy-user", f"{user.strip()}:{password.strip()}"]
    cmd.append("https://api.ipify.org")

    code, out = run(cmd, timeout=40)
    raw = (out or "").strip()
    if code != 0 or not raw:
        raise RuntimeError(f"代理测试失败。\n\ncurl 返回码：{code}\n\ncurl 输出：\n{raw}")
    return raw.splitlines()[-1].strip()
