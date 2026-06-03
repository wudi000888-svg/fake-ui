import os
import secrets
import shutil
import time

from panel_config import (
    HY2_BACKUP_DIR,
    HY2_CONFIG_FILE,
    HY2_ENV_FILE,
    HY2_MASQUERADE_URL,
    HY2_RESTART_CMD,
    HY2_STATUS_CMD,
    HY2_TRAFFIC_SECRET_FILE,
)
import admin_profile
import node_catalog
from sync_utils import backup_file, run_shell


def read_hy2_env():
    data = {}
    for line in HY2_ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        data[k.strip()] = v.strip().strip('"').strip("'")
    if not data.get("HY_DOMAIN"):
        raise RuntimeError("Hysteria2 .env 缺少 HY_DOMAIN")
    data.setdefault("HY_PORT", "443")
    return data


def get_hy2_traffic_secret():
    if HY2_TRAFFIC_SECRET_FILE.exists():
        secret = HY2_TRAFFIC_SECRET_FILE.read_text(encoding="utf-8").strip()
        if secret:
            return secret

    secret = secrets.token_urlsafe(32)
    HY2_TRAFFIC_SECRET_FILE.write_text(secret + "\n", encoding="utf-8")
    os.chmod(HY2_TRAFFIC_SECRET_FILE, 0o600)
    return secret


def extract_hy2_outbounds_block():
    if not HY2_CONFIG_FILE.exists():
        return """outbounds:
  - name: direct
    type: direct
    direct:
      mode: 4
"""

    text = HY2_CONFIG_FILE.read_text(encoding="utf-8")
    lines = text.splitlines()

    start = None
    for i, line in enumerate(lines):
        if line.strip() == "outbounds:" and not line.startswith((" ", "\t")):
            start = i
            break

    if start is None:
        return """outbounds:
  - name: direct
    type: direct
    direct:
      mode: 4
"""

    block = "\n".join(lines[start:]).rstrip() + "\n"

    if "type:" not in block:
        return """outbounds:
  - name: direct
    type: direct
    direct:
      mode: 4
"""

    return block


def build_hy2_config(users):
    env = read_hy2_env()
    domain = env["HY_DOMAIN"]
    listen_port = env.get("HY_PORT", "443")
    traffic_secret = get_hy2_traffic_secret()
    all_users = dict(users)
    all_users[admin_profile.ADMIN_USERNAME] = admin_profile.get_admin_user()

    lines = [
        f"listen: :{listen_port}",
        "",
        "tls:",
        f"  cert: /etc/letsencrypt/live/{domain}/fullchain.pem",
        f"  key: /etc/letsencrypt/live/{domain}/privkey.pem",
        "",
        "auth:",
        "  type: userpass",
        "  userpass:",
    ]

    auth_names = set()
    admin_pass = env.get("HY_ADMIN_PASSWORD") or env.get("HY_PASSWORD")
    if admin_pass:
        lines.append(f"    admin: {admin_pass}")
        auth_names.add("admin")

    for username, u in all_users.items():
        if username != admin_profile.ADMIN_USERNAME and not node_catalog.nodes_for_user(u, kind="hy2", include_disabled=False):
            continue
        hy_user = u.get("hy2_username") or username
        hy_pass = u.get("hy2_password")
        if hy_user and hy_pass and hy_user not in auth_names:
            lines.append(f"    {hy_user}: {hy_pass}")
            auth_names.add(hy_user)

    lines += [
        "",
        "masquerade:",
        "  type: proxy",
        "  proxy:",
        f"    url: {HY2_MASQUERADE_URL}",
        "    rewriteHost: true",
        "",
        "trafficStats:",
        "  listen: 127.0.0.1:9999",
        f"  secret: {traffic_secret}",
        "",
    ]

    lines.append(extract_hy2_outbounds_block().rstrip())
    lines.append("")

    return "\n".join(lines)


def sync_hy2(users):
    new = build_hy2_config(users)
    old = HY2_CONFIG_FILE.read_text(encoding="utf-8") if HY2_CONFIG_FILE.exists() else ""

    if old.strip() == new.strip():
        print("Hysteria2 无变化")
        return False

    backup = backup_file(HY2_CONFIG_FILE, HY2_BACKUP_DIR, "enforce-users")
    HY2_CONFIG_FILE.write_text(new, encoding="utf-8")
    os.chmod(HY2_CONFIG_FILE, 0o644)

    code, out = run_shell(HY2_RESTART_CMD, timeout=60)
    time.sleep(3)

    code2, running = run_shell(HY2_STATUS_CMD, timeout=20)

    if code != 0 or code2 != 0 or running.strip().lower() not in ("true", "active", "running"):
        shutil.copy2(backup, HY2_CONFIG_FILE)
        run_shell(HY2_RESTART_CMD, timeout=60)
        raise RuntimeError("Hysteria2 重启失败，已回滚：\n" + out)

    print(f"Hysteria2 已同步，有效托管用户数：{len(users)}，管理员订阅已同步")
    return True
