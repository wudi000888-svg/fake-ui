from pathlib import Path
import os

from panel_config import PANEL_DIR
import subprocess

from process_utils import run


ACME_ROOT = Path("/opt/fake-ui/data/acme")
LETSENCRYPT_LIVE = Path("/etc/letsencrypt/live")
NGINX_TUNNEL_CONF = Path("/etc/nginx/conf.d/fake-ui-tunnels.conf")
LEGACY_CONF_GLOB = "fake-ui-tunnel-*.conf"


def domain_for(tunnel):
    domain = str((tunnel or {}).get("public_domain") or "").strip().lower()
    if not domain:
        raise RuntimeError("public domain is required")
    return domain


def portal_port_for(tunnel):
    port = int((tunnel or {}).get("portal_port") or 0)
    if not port:
        raise RuntimeError("portal port is required")
    return port


def render_http_server(tunnel, acme_root=ACME_ROOT):
    domain = domain_for(tunnel)
    port = portal_port_for(tunnel)
    return f"""server {{
    listen 80;
    listen [::]:80;
    server_name {domain};

    location ^~ /.well-known/acme-challenge/ {{
        root {acme_root};
        default_type text/plain;
    }}

    location / {{
        proxy_pass http://127.0.0.1:{port};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto http;
        proxy_read_timeout 300s;
    }}
}}
"""


def render_https_server(tunnel, letsencrypt_live=LETSENCRYPT_LIVE):
    domain = domain_for(tunnel)
    port = portal_port_for(tunnel)
    cert_dir = Path(letsencrypt_live) / domain
    return f"""server {{
    listen 127.0.0.1:10000 ssl http2;
    server_name {domain};

    ssl_certificate {cert_dir}/fullchain.pem;
    ssl_certificate_key {cert_dir}/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_session_timeout 1d;
    ssl_session_cache shared:SSL:10m;
    add_header Strict-Transport-Security "max-age=31536000" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header Referrer-Policy "same-origin" always;
    add_header Permissions-Policy "camera=(), microphone=(), geolocation=()" always;

    location / {{
        proxy_pass http://127.0.0.1:{port};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 300s;
    }}
}}
"""


def combined_config(tunnels, acme_root=ACME_ROOT, letsencrypt_live=LETSENCRYPT_LIVE):
    parts = []
    for tunnel in tunnels or []:
        if not (tunnel or {}).get("public_domain"):
            continue
        parts.append(render_http_server(tunnel, acme_root))
        parts.append(render_https_server(tunnel, letsencrypt_live))
    return "\n".join(parts)


def write_text(path, text):
    path = Path(path)
    if os.getenv("FAKE_UI_HOST_COMMAND_MODE", "").strip() == "docker-nsenter":
        host_write_text(path, text)
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def host_write_text(path, text):
    helper_image = os.getenv("FAKE_UI_HOST_HELPER_IMAGE", "xray-proxy-panel:local").strip()
    cmd = [
        "docker",
        "run",
        "--rm",
        "-i",
        "--privileged",
        "--pid=host",
        "--network=host",
        helper_image,
        "nsenter",
        "-t",
        "1",
        "-m",
        "-u",
        "-n",
        "-i",
        "--",
        "sh",
        "-c",
        f"mkdir -p {quote_sh(str(path.parent))} && cat > {quote_sh(str(path))}",
    ]
    p = subprocess.run(cmd, input=text, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30)
    if p.returncode != 0:
        raise RuntimeError("写入宿主机文件失败：\n" + p.stdout)


def quote_sh(value):
    return "'" + str(value).replace("'", "'\"'\"'") + "'"


def run_checked(cmd, timeout=60):
    cmd = host_command(cmd)
    code, out = run(cmd, timeout=timeout)
    if code != 0:
        raise RuntimeError("命令执行失败：{}\n{}".format(" ".join(map(str, cmd)), out))
    return out


def disable_legacy_single_tunnel_confs(conf_path=NGINX_TUNNEL_CONF):
    conf_path = Path(conf_path)
    conf_dir = conf_path.parent
    if os.getenv("FAKE_UI_HOST_COMMAND_MODE", "").strip() == "docker-nsenter":
        script = (
            f"for f in {quote_sh(str(conf_dir))}/fake-ui-tunnel-*.conf; do "
            "[ -e \"$f\" ] || continue; "
            f"[ \"$f\" = {quote_sh(str(conf_path))} ] && continue; "
            "mv \"$f\" \"$f.disabled\"; "
            "printf '%s\\n' \"$f.disabled\"; "
            "done"
        )
        out = run_checked(["sh", "-c", script], timeout=30)
        return [line.strip() for line in out.splitlines() if line.strip()]

    disabled = []
    if not conf_dir.exists():
        return disabled
    for path in sorted(conf_dir.glob(LEGACY_CONF_GLOB)):
        if path == conf_path:
            continue
        target = Path(str(path) + ".disabled")
        path.rename(target)
        disabled.append(str(target))
    return disabled


def host_command(cmd):
    if os.getenv("FAKE_UI_HOST_COMMAND_MODE", "").strip() != "docker-nsenter":
        return list(cmd)
    helper_image = os.getenv("FAKE_UI_HOST_HELPER_IMAGE", "xray-proxy-panel:local").strip()
    return [
        "docker",
        "run",
        "--rm",
        "--privileged",
        "--pid=host",
        "--network=host",
        helper_image,
        "nsenter",
        "-t",
        "1",
        "-m",
        "-u",
        "-n",
        "-i",
        "--",
        *[str(part) for part in cmd],
    ]


def cert_exists(domain, letsencrypt_live=LETSENCRYPT_LIVE):
    if os.getenv("FAKE_UI_HOST_COMMAND_MODE", "").strip() == "docker-nsenter":
        code, _ = run(host_command(["test", "-f", str(Path(letsencrypt_live) / domain / "fullchain.pem")]), timeout=20)
        return code == 0
    cert_dir = Path(letsencrypt_live) / domain
    return (cert_dir / "fullchain.pem").exists() and (cert_dir / "privkey.pem").exists()


def issue_cert(domain, acme_root=ACME_ROOT):
    run_checked(
        [
            "certbot",
            "certonly",
            "--webroot",
            "-w",
            str(acme_root),
            "--cert-name",
            domain,
            "-d",
            domain,
            "--key-type",
            "ecdsa",
            "--non-interactive",
            "--agree-tos",
            "--register-unsafely-without-email",
        ],
        timeout=180,
    )


def apply_native_nginx(tunnels, conf_path=NGINX_TUNNEL_CONF, acme_root=ACME_ROOT, letsencrypt_live=LETSENCRYPT_LIVE):
    enabled = [dict(item) for item in (tunnels or []) if item.get("enabled", True) and item.get("public_domain")]
    Path(acme_root).mkdir(parents=True, exist_ok=True)
    legacy_disabled = disable_legacy_single_tunnel_confs(conf_path)

    # First write HTTP-only ACME-capable blocks so new domains can pass webroot validation.
    http_only = "\n".join(render_http_server(item, acme_root) for item in enabled)
    write_text(conf_path, http_only)
    run_checked(["nginx", "-t"], timeout=30)
    run_checked(["systemctl", "reload", "nginx"], timeout=30)

    issued = []
    for item in enabled:
        domain = domain_for(item)
        if not cert_exists(domain, letsencrypt_live):
            issue_cert(domain, acme_root)
            issued.append(domain)

    write_text(conf_path, combined_config(enabled, acme_root, letsencrypt_live))
    run_checked(["nginx", "-t"], timeout=30)
    run_checked(["systemctl", "reload", "nginx"], timeout=30)
    return {
        "domains": [domain_for(item) for item in enabled],
        "issued": issued,
        "conf": str(conf_path),
        "legacy_disabled": legacy_disabled,
    }
