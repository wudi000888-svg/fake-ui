import io
import json
import re
import tarfile


DASHBOARD_HOST = "127.0.0.1"
DASHBOARD_PORT = 19090


def service_id(tunnel):
    return f"com.fakeui.tunnel.{tunnel.get('id')}"


def bundle_dir(tunnel):
    return str(tunnel.get("id") or "fake-ui-tunnel")


def bundle_root(tunnel, platform):
    return f"{safe_id(tunnel.get('id') or 'fake-ui-tunnel')}-{safe_id(platform)}-bridge"


def safe_id(value):
    clean = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(value or "").strip()).strip("-")
    return clean or "bridge"


def plist_text(tunnel):
    sid = service_id(tunnel)
    node_id = tunnel.get("id")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{sid}</string>
  <key>ProgramArguments</key>
  <array>
    <string>__HOME__/.fake-ui/bin/xray</string>
    <string>run</string>
    <string>-c</string>
    <string>__HOME__/.fake-ui/tunnels/{node_id}/xray-bridge.json</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>__HOME__/.fake-ui/tunnels/{node_id}/bridge.out.log</string>
  <key>StandardErrorPath</key>
  <string>__HOME__/.fake-ui/tunnels/{node_id}/bridge.err.log</string>
</dict>
</plist>
"""


def shell_bootstrap_snippet():
    return """SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$SCRIPT_DIR/agent-profile.json" ] && [ -f "$SCRIPT_DIR/bootstrap-agent.py" ]; then
  PYTHON="${PYTHON:-}"
  if [ -z "$PYTHON" ]; then
    if command -v python3 >/dev/null 2>&1; then
      PYTHON=python3
    elif command -v python >/dev/null 2>&1; then
      PYTHON=python
    else
      echo "未找到 Python。请先安装 Python 3。" >&2
      exit 1
    fi
  fi
  "$PYTHON" "$SCRIPT_DIR/bootstrap-agent.py"
fi
if [ ! -f "$SCRIPT_DIR/xray-bridge.json" ]; then
  echo "未找到 xray-bridge.json。请先运行 bootstrap-agent.py 或放入静态配置。" >&2
  exit 1
fi
"""


def powershell_bootstrap_snippet():
    return """$Profile = Join-Path $PSScriptRoot "agent-profile.json"
$Bootstrap = Join-Path $PSScriptRoot "bootstrap-agent.py"
if ((Test-Path $Profile) -and (Test-Path $Bootstrap)) {
  $Python = Get-Command python.exe -ErrorAction SilentlyContinue
  if (-not $Python) {
    $Python = Get-Command py.exe -ErrorAction SilentlyContinue
  }
  if (-not $Python) {
    throw "未找到 Python。请先安装 Python 3。"
  }
  & $Python.Source $Bootstrap
}
if (-not (Test-Path (Join-Path $PSScriptRoot "xray-bridge.json"))) {
  throw "未找到 xray-bridge.json。请先运行 bootstrap-agent.py 或放入静态配置。"
}
"""


def install_script(tunnel):
    node_id = tunnel.get("id")
    sid = service_id(tunnel)
    bootstrap = shell_bootstrap_snippet()
    return f"""#!/usr/bin/env bash
set -euo pipefail

ROOT="$HOME/.fake-ui"
TUNNEL_DIR="$ROOT/tunnels/{node_id}"
PLIST="$HOME/Library/LaunchAgents/{sid}.plist"

mkdir -p "$ROOT/bin" "$TUNNEL_DIR" "$HOME/Library/LaunchAgents"
{bootstrap}\
cp "$(dirname "$0")/xray-bridge.json" "$TUNNEL_DIR/xray-bridge.json"
cp "$(dirname "$0")/{sid}.plist" "$PLIST"
sed -i '' "s|__HOME__|$HOME|g" "$PLIST"

if [ ! -x "$ROOT/bin/xray" ]; then
  if command -v xray >/dev/null 2>&1; then
    ln -sf "$(command -v xray)" "$ROOT/bin/xray"
  else
    echo "未找到 xray。请先安装 Xray，或把 xray 二进制放到 $ROOT/bin/xray" >&2
    exit 1
  fi
fi

"$ROOT/bin/xray" run -test -c "$TUNNEL_DIR/xray-bridge.json"
launchctl bootout "gui/$(id -u)" "$PLIST" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl kickstart -k "gui/$(id -u)/{sid}"
"$(dirname "$0")/status-macos.sh"
"""


def uninstall_script(tunnel):
    node_id = tunnel.get("id")
    sid = service_id(tunnel)
    return f"""#!/usr/bin/env bash
set -euo pipefail
PLIST="$HOME/Library/LaunchAgents/{sid}.plist"
launchctl bootout "gui/$(id -u)" "$PLIST" >/dev/null 2>&1 || true
rm -f "$PLIST"
rm -rf "$HOME/.fake-ui/tunnels/{node_id}"
echo "已卸载 {sid}"
"""


def status_script(tunnel):
    sid = service_id(tunnel)
    target_host = tunnel.get("target_host") or "127.0.0.1"
    target_port = int(tunnel.get("target_port") or 0)
    domain = tunnel.get("public_domain") or tunnel.get("server_address") or ""
    local_check = (
        f"nc -z {target_host} {target_port}\n"
        f"echo \"local tcp ok: {target_host}:{target_port}\""
        if tunnel.get("kind") == "private_tcp"
        else f"curl -fsS http://{target_host}:{target_port}/ >/dev/null\n"
        f"echo \"local service ok: http://{target_host}:{target_port}/\""
    )
    public_check = (
        ""
        if not tunnel.get("public_domain")
        else f"""echo "== public https =="
curl -fsS https://{domain}/ >/dev/null
echo "public https ok: https://{domain}/"
"""
    )
    return f"""#!/usr/bin/env bash
set -euo pipefail
echo "== launchd =="
launchctl print "gui/$(id -u)/{sid}" | sed -n '1,80p'
echo "== local service =="
{local_check}
{public_check}"""


def platform_label(platform):
    return {"macos": "macOS", "linux": "Linux", "windows": "Windows"}.get(safe_id(platform).lower(), platform)


def command_block(command, platform):
    if safe_id(platform).lower() == "windows":
        return f"```PowerShell\n{command}\n```"
    return f"```bash\n{command}\n```"


def install_command(platform):
    platform = safe_id(platform).lower()
    if platform == "windows":
        return "powershell -ExecutionPolicy Bypass -File .\\install-windows.ps1"
    return f"bash install-{platform}.sh"


def status_command(platform):
    platform = safe_id(platform).lower()
    if platform == "windows":
        return "powershell -ExecutionPolicy Bypass -File .\\status-windows.ps1"
    return f"bash status-{platform}.sh"


def dashboard_command(platform):
    platform = safe_id(platform).lower()
    if platform == "windows":
        return "powershell -ExecutionPolicy Bypass -File .\\open-dashboard.ps1"
    return "bash open-dashboard.sh"


def uninstall_command(platform):
    platform = safe_id(platform).lower()
    if platform == "windows":
        return "powershell -ExecutionPolicy Bypass -File .\\uninstall-windows.ps1"
    return f"bash uninstall-{platform}.sh"


def readme_text(tunnel, platform="macos"):
    label = platform_label(platform)
    if tunnel.get("kind") == "private_tcp":
        return f"""# fake-ui {label} Bridge

Tunnel: {tunnel.get('name') or tunnel.get('id')}
Type: private TCP
Local service: {tunnel.get('target_host')}:{tunnel.get('target_port')}
VPS portal: 127.0.0.1:{tunnel.get('portal_port')}

Install:

{command_block(install_command(platform), platform)}

Connect through the VPS SSH jump host:

```bash
ssh -J root@YOUR_VPS -p {tunnel.get('portal_port')} YOUR_MAC_USER@127.0.0.1
```

Or add an SSH config entry:

```sshconfig
Host {tunnel.get('id')}
  HostName 127.0.0.1
  Port {tunnel.get('portal_port')}
  User YOUR_MAC_USER
  ProxyJump root@YOUR_VPS
```

Status:

{command_block(status_command(platform), platform)}

Local dashboard:

{command_block(dashboard_command(platform), platform)}

Open http://127.0.0.1:19090/

Uninstall:

{command_block(uninstall_command(platform), platform)}
"""
    return f"""# fake-ui {label} Bridge

Tunnel: {tunnel.get('name') or tunnel.get('id')}
Public URL: https://{tunnel.get('public_domain') or tunnel.get('server_address')}/
Local service: http://{tunnel.get('target_host')}:{tunnel.get('target_port')}/

Install:

{command_block(install_command(platform), platform)}

Status:

{command_block(status_command(platform), platform)}

Local dashboard:

{command_block(dashboard_command(platform), platform)}

Open http://127.0.0.1:19090/

Uninstall:

{command_block(uninstall_command(platform), platform)}
"""


def add_text(tar, path, text, mode=0o644):
    raw = text.encode("utf-8")
    info = tarfile.TarInfo(path)
    info.size = len(raw)
    info.mode = mode
    tar.addfile(info, io.BytesIO(raw))


def build_macos_bundle(tunnel, bridge_config):
    root = bundle_dir(tunnel)
    content = io.BytesIO()
    with tarfile.open(fileobj=content, mode="w:gz") as tar:
        add_text(tar, f"{root}/xray-bridge.json", json.dumps(bridge_config, indent=2, ensure_ascii=False))
        add_text(tar, f"{root}/{service_id(tunnel)}.plist", plist_text(tunnel))
        add_text(tar, f"{root}/install-macos.sh", install_script(tunnel), mode=0o755)
        add_text(tar, f"{root}/uninstall-macos.sh", uninstall_script(tunnel), mode=0o755)
        add_text(tar, f"{root}/status-macos.sh", status_script(tunnel), mode=0o755)
        add_dashboard_assets(tar, root, "dedicated", tunnel.get("id"), "macos", [tunnel])
        add_text(tar, f"{root}/README.md", readme_text(tunnel, "macos"))
    return content.getvalue()


def dedicated_linux_service_id(tunnel):
    return f"fake-ui-tunnel-{safe_id(tunnel.get('id'))}.service"


def dedicated_windows_task_name(tunnel):
    return f"FakeUITunnel-{safe_id(tunnel.get('id'))}"


def platform_runtime(platform, dedicated_id="", bridge_id=""):
    platform = safe_id(platform).lower()
    if platform == "macos":
        name = service_id({"id": dedicated_id}) if dedicated_id else agent_service_id(bridge_id)
        return {
            "kind": "launchd",
            "name": name,
            "restart_command": f'launchctl kickstart -k "gui/$(id -u)/{name}"',
            "log_command": f'tail -n 80 ~/.fake-ui/{"tunnels/" + safe_id(dedicated_id) if dedicated_id else "bridges/" + safe_id(bridge_id)}/bridge.err.log',
        }
    if platform == "linux":
        name = dedicated_linux_service_id({"id": dedicated_id}) if dedicated_id else f"fake-ui-bridge-{safe_id(bridge_id)}.service"
        return {
            "kind": "systemd",
            "name": name,
            "restart_command": f"sudo systemctl restart {name}",
            "log_command": f"journalctl -u {name} -n 80 --no-pager",
        }
    if platform == "windows":
        name = dedicated_windows_task_name({"id": dedicated_id}) if dedicated_id else f"FakeUIBridge-{safe_id(bridge_id)}"
        return {
            "kind": "scheduled_task",
            "name": name,
            "restart_command": f'Restart-ScheduledTask -TaskName "{name}"',
            "log_command": f'Get-ScheduledTaskInfo -TaskName "{name}"',
        }
    return {"kind": platform, "name": ""}


def platform_logs(platform, dedicated_id="", bridge_id=""):
    platform = safe_id(platform).lower()
    if platform == "macos":
        if dedicated_id:
            base = f"~/.fake-ui/tunnels/{safe_id(dedicated_id)}"
        else:
            base = f"~/.fake-ui/bridges/{safe_id(bridge_id)}"
        return [f"{base}/bridge.out.log", f"{base}/bridge.err.log", "bridge-dashboard.out.log", "bridge-dashboard.err.log"]
    if platform == "linux":
        return ["bridge-dashboard.out.log", "bridge-dashboard.err.log"]
    if platform == "windows":
        if dedicated_id:
            base = f"%ProgramData%\\fake-ui-tunnel\\{safe_id(dedicated_id)}"
        else:
            base = f"%ProgramData%\\fake-ui-bridge\\{safe_id(bridge_id)}"
        return [f"{base}\\bridge.out.log", f"{base}\\bridge.err.log", "bridge-dashboard.out.log", "bridge-dashboard.err.log"]
    return ["bridge-dashboard.out.log", "bridge-dashboard.err.log"]


def dashboard_service(tunnel):
    target_host = tunnel.get("target_host") or "127.0.0.1"
    target_port = int(tunnel.get("target_port") or 0)
    public_domain = tunnel.get("public_domain") or ""
    is_private_tcp = tunnel.get("kind") == "private_tcp"
    return {
        "id": tunnel.get("id"),
        "name": tunnel.get("name") or tunnel.get("id"),
        "kind": tunnel.get("kind") or "public_https",
        "public_domain": public_domain,
        "public_url": "" if is_private_tcp or not public_domain else f"https://{public_domain}/",
        "local": f"{target_host}:{target_port}",
        "local_url": "" if is_private_tcp else f"http://{target_host}:{target_port}/",
        "target_host": target_host,
        "target_port": target_port,
        "portal_port": int(tunnel.get("portal_port") or 0),
    }


def dashboard_metadata(bundle_kind, identifier, platform, tunnels):
    platform = safe_id(platform).lower()
    safe_identifier = safe_id(identifier)
    first = tunnels[0] if tunnels else {}
    dedicated_id = safe_id(first.get("id")) if bundle_kind == "dedicated" else ""
    bridge_id = safe_identifier if bundle_kind == "shared" else dedicated_id
    return {
        "bundle_kind": bundle_kind,
        "bridge_id": bridge_id,
        "platform": platform,
        "dashboard": {"host": DASHBOARD_HOST, "port": DASHBOARD_PORT},
        "runtime": platform_runtime(platform, dedicated_id=dedicated_id, bridge_id=bridge_id),
        "logs": platform_logs(platform, dedicated_id=dedicated_id, bridge_id=bridge_id),
        "xray_config": {"path": "xray-bridge.json"},
        "services": [dashboard_service(tunnel) for tunnel in tunnels],
    }


def dashboard_script():
    return r'''#!/usr/bin/env python3
import argparse
import html
import json
import os
import re
import socket
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 19090


def load_metadata(base_dir):
    path = base_dir / "bridge-dashboard.json"
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def tcp_probe(host, port, timeout=0.15):
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return {"ok": True, "message": "reachable"}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


def command_probe(command, timeout=2.0):
    try:
        proc = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
    except FileNotFoundError:
        return {"ok": False, "message": f"{command[0]} not found"}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}
    text = (proc.stdout or "").strip()
    return {"ok": proc.returncode == 0, "message": text[:1200] if text else f"exit {proc.returncode}"}


def runtime_status(metadata):
    runtime = metadata.get("runtime") or {}
    kind = runtime.get("kind")
    name = runtime.get("name")
    if not name:
        return {"ok": False, "message": "runtime name is missing"}
    if kind == "manual":
        return {"ok": True, "message": "manual client mode"}
    if kind == "launchd":
        return command_probe(["launchctl", "print", f"gui/{os.getuid()}/{name}"])
    if kind == "systemd":
        return command_probe(["systemctl", "is-active", name])
    if kind == "scheduled_task":
        return command_probe(["schtasks", "/Query", "/TN", name])
    return {"ok": False, "message": f"unsupported runtime: {kind}"}


def xray_config_status(base_dir, metadata):
    rel_path = (metadata.get("xray_config") or {}).get("path") or "xray-bridge.json"
    path = base_dir / rel_path
    if not path.exists():
        return {"ok": False, "path": str(path), "message": "missing"}
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"ok": False, "path": str(path), "message": str(exc)}
    return {"ok": True, "path": str(path), "message": "valid json"}


def xray_config_preview(base_dir, metadata, limit=2600):
    rel_path = (metadata.get("xray_config") or {}).get("path") or "xray-bridge.json"
    path = base_dir / rel_path
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    return json.dumps(data, indent=2, ensure_ascii=False)[:limit]


def expand_log_path(base_dir, path):
    raw = str(path or "")
    if raw.startswith("~"):
        return Path(raw).expanduser()
    if raw.startswith("%ProgramData%"):
        return Path(os.environ.get("ProgramData", r"C:\ProgramData")) / raw[len("%ProgramData%\\"):]
    candidate = Path(raw)
    if candidate.is_absolute():
        return candidate
    return base_dir / raw


def tail_text(path, limit=4000):
    try:
        data = path.read_bytes()[-limit:]
    except FileNotFoundError:
        return {"path": str(path), "exists": False, "tail": ""}
    except Exception as exc:
        return {"path": str(path), "exists": False, "tail": str(exc)}
    return {"path": str(path), "exists": True, "tail": data.decode("utf-8", "replace")}


def collect_logs(metadata, base_dir):
    return [tail_text(expand_log_path(base_dir, path)) for path in metadata.get("logs") or []]


def collect_status(metadata, base_dir):
    services = []
    for service in metadata.get("services") or []:
        probe = tcp_probe(service.get("target_host", "127.0.0.1"), service.get("target_port", 0))
        item = dict(service)
        item["local_reachable"] = probe
        services.append(item)
    return {
        "metadata": metadata,
        "runtime": runtime_status(metadata),
        "xray_config": xray_config_status(base_dir, metadata),
        "services": services,
        "logs": collect_logs(metadata, base_dir),
        "config_preview": xray_config_preview(base_dir, metadata),
    }


def status_badge(ok):
    return "ok" if ok else "warn"


def redact_sensitive(value):
    text = str(value or "")
    text = re.sub(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}", "[redacted-uuid]", text)
    text = re.sub(r'("(?:privateKey|publicKey|shortId|shortIds|pairing_token)"\s*:\s*)("[^"]*"|\[[^\]]*\])', r'\1"[redacted-secret]"', text)
    text = re.sub(r"(?i)(pairing[_-]?token\s*[=:]\s*)[^\s\"']+", r"\1[redacted-secret]", text)
    text = re.sub(r"(?i)((?:private|public)[_-]?key\s*[=:]\s*)[^\s\"']+", r"\1[redacted-secret]", text)
    text = re.sub(r"(?i)(short[_-]?id\s*[=:]\s*)[0-9a-f]{6,32}", r"\1[redacted-secret]", text)
    return text


def esc(value):
    return html.escape(redact_sensitive(value))


def badge_html(ok, text):
    return f"<span class='status-badge {status_badge(bool(ok))}'>{esc(text or 'unknown')}</span>"


def render_dashboard(status):
    metadata = status.get("metadata") or {}
    runtime = status.get("runtime") or {}
    xray_config = status.get("xray_config") or {}
    services = status.get("services") or []
    logs = status.get("logs") or []
    dashboard = metadata.get("dashboard") or {}
    rows = []
    for service in services:
        probe = service.get("local_reachable") or {}
        public_url = service.get("public_url") or "-"
        local_url = service.get("local_url") or service.get("local") or "-"
        rows.append(
            "<tr>"
            f"<td><strong>{esc(service.get('name') or service.get('id') or '')}</strong><span>{esc(service.get('id') or '')}</span></td>"
            f"<td>{esc(service.get('kind') or '')}</td>"
            f"<td><code>{esc(local_url)}</code></td>"
            f"<td><code>{esc(public_url)}</code></td>"
            f"<td>{badge_html(bool(probe.get('ok')), probe.get('message') or '')}</td>"
            "</tr>"
        )
    runtime_name = (metadata.get("runtime") or {}).get("name") or ""
    restart_command = (metadata.get("runtime") or {}).get("restart_command") or ""
    log_command = (metadata.get("runtime") or {}).get("log_command") or ""
    log_blocks = []
    for item in logs:
        state = "found" if item.get("exists") else "missing"
        tail = item.get("tail") or ""
        log_blocks.append(
            f"<details><summary>{esc(item.get('path') or '')} · {esc(state)}</summary>"
            f"<pre>{esc(tail[-1600:])}</pre></details>"
        )
    service_count = len(services)
    public_count = len([item for item in services if item.get("public_url")])
    log_count = len([item for item in logs if item.get("exists")])
    config_preview = status.get("config_preview") or ""
    if not config_preview:
        config_preview = xray_config.get("message") or "No config preview available"
    html_text = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>fake-ui Bridge Dashboard</title>
  <style>
    :root {{ --bg: #f4f8fb; --surface: #ffffff; --surface-soft: #f8fbfd; --ink: #101828; --muted: #667085; --line: #dde6ee; --primary: #2563eb; --primary-soft: #eaf1ff; --accent: #14b8a6; --accent-soft: #e7faf7; --success: #12805c; --warning: #b7791f; --danger: #c2413b; --radius: 8px; --shadow: 0 10px 30px rgba(16, 24, 40, 0.08); }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: var(--ink); background: var(--bg); }}
    .app-shell {{ min-height: 100vh; display: grid; grid-template-columns: 236px minmax(0, 1fr); }}
    .side-nav {{ position: sticky; top: 0; height: 100vh; display: grid; grid-template-rows: auto 1fr auto; gap: 16px; padding: 16px 14px; background: rgba(255,255,255,.96); border-right: 1px solid var(--line); }}
    .brand {{ padding: 8px 10px 14px; border-bottom: 1px solid var(--line); }}
    .brand strong {{ display: block; font-size: 20px; }}
    .brand span, .nav-link, .section-kicker, td span {{ color: var(--muted); font-size: 12px; }}
    .nav-stack {{ display: grid; align-content: start; gap: 6px; }}
    .nav-link {{ display: flex; align-items: center; gap: 8px; min-height: 38px; padding: 0 10px; border-radius: var(--radius); text-decoration: none; color: var(--ink); font-weight: 700; }}
    .nav-link.active, .nav-link:hover {{ background: var(--primary-soft); color: var(--primary); }}
    .workspace {{ min-width: 0; }}
    .topbar {{ position: sticky; top: 0; z-index: 5; min-height: 64px; display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 10px 24px; background: rgba(255,255,255,.94); border-bottom: 1px solid var(--line); }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 24px; }}
    section {{ margin-bottom: 18px; }}
    .panel {{ background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius); box-shadow: var(--shadow); padding: 18px; }}
    h1, h2, h3, p {{ margin-top: 0; }}
    h1 {{ margin-bottom: 2px; font-size: 22px; }}
    h2 {{ margin-bottom: 12px; font-size: 16px; }}
    .metric-grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }}
    .metric {{ background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius); padding: 14px; }}
    .metric span {{ color: var(--muted); font-size: 12px; }}
    .metric strong {{ display: block; margin-top: 4px; font-size: 22px; }}
    .status-badge {{ display: inline-flex; align-items: center; min-height: 24px; padding: 0 8px; border-radius: 999px; font-weight: 800; font-size: 12px; }}
    .status-badge.ok {{ color: var(--success); background: #dcfce7; }}
    .status-badge.warn {{ color: var(--warning); background: #fff3cf; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ text-align: left; padding: 11px 8px; border-bottom: 1px solid var(--line); vertical-align: top; }}
    th {{ color: var(--muted); font-size: 12px; text-transform: uppercase; }}
    td strong, td span {{ display: block; }}
    code {{ background: var(--surface-soft); border: 1px solid var(--line); border-radius: 6px; padding: 2px 5px; }}
    pre {{ max-height: 260px; overflow: auto; background: #101828; color: #edf5ff; border-radius: var(--radius); padding: 12px; white-space: pre-wrap; font-size: 12px; }}
    summary {{ cursor: pointer; padding: 7px 0; font-weight: 700; }}
    .setup-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }}
    .setup-item {{ border: 1px solid var(--line); border-radius: var(--radius); padding: 12px; background: var(--surface-soft); }}
    .mono-line {{ word-break: break-all; }}
    @media (max-width: 860px) {{ .app-shell {{ grid-template-columns: 1fr; }} .side-nav {{ position: static; height: auto; grid-template-rows: auto; }} .nav-stack {{ display: flex; overflow-x: auto; }} .metric-grid, .setup-grid {{ grid-template-columns: 1fr; }} .topbar {{ align-items: flex-start; flex-direction: column; }} }}
  </style>
</head>
<body>
  <div class="app-shell">
    <aside class="side-nav">
      <div class="brand"><strong>fake-ui</strong><span>Bridge Agent</span></div>
      <nav class="nav-stack">
        <a class="nav-link active" href="#overview-section">Overview</a>
        <a class="nav-link" href="#services-section">Services</a>
        <a class="nav-link" href="#setup-section">Setup</a>
        <a class="nav-link" href="#logs-section">Logs</a>
        <a class="nav-link" href="#api-section">API</a>
      </nav>
      <div class="section-kicker">Local only · {esc(dashboard.get('host') or DEFAULT_HOST)}:{esc(dashboard.get('port') or DEFAULT_PORT)}</div>
    </aside>
    <div class="workspace">
      <header class="topbar">
        <div><h1>Bridge Agent</h1><span>{esc(metadata.get('bundle_kind', 'bridge'))} · {esc(metadata.get('platform', 'unknown'))} · {esc(metadata.get('bridge_id', ''))}</span></div>
        {badge_html(bool(runtime.get('ok')), runtime.get('message') or 'runtime unknown')}
      </header>
      <main>
        <section id="overview-section" class="overview-section">
          <div class="metric-grid">
            <div class="metric"><span>Runtime</span><strong>{esc('running' if runtime.get('ok') else 'check')}</strong></div>
            <div class="metric"><span>Config</span><strong>{esc(xray_config.get('message') or 'unknown')}</strong></div>
            <div class="metric"><span>Services</span><strong>{service_count}</strong></div>
            <div class="metric"><span>Public URLs</span><strong>{public_count}</strong></div>
          </div>
        </section>
        <section id="services-section" class="services-section panel">
          <h2>Services</h2>
          <table class="service-table">
            <thead><tr><th>Name</th><th>Type</th><th>Local</th><th>Public</th><th>Probe</th></tr></thead>
            <tbody>{''.join(rows) or '<tr><td colspan="5">No services configured</td></tr>'}</tbody>
          </table>
        </section>
        <section id="setup-section" class="setup-section panel">
          <h2>Setup</h2>
          <div class="setup-grid">
            <div class="setup-item"><span class="section-kicker">Service</span><p><code>{esc(runtime_name)}</code></p></div>
            <div class="setup-item"><span class="section-kicker">Restart</span><p class="mono-line"><code>{esc(restart_command or 'not available')}</code></p></div>
            <div class="setup-item"><span class="section-kicker">Logs</span><p class="mono-line"><code>{esc(log_command or 'not available')}</code></p></div>
            <div class="setup-item"><span class="section-kicker">Config</span><p><code>{esc(xray_config.get('path') or '')}</code> {badge_html(bool(xray_config.get('ok')), xray_config.get('message') or '')}</p></div>
          </div>
          <pre>{esc(config_preview)}</pre>
        </section>
        <section id="logs-section" class="logs-section panel">
          <h2>Logs</h2>
          <p class="section-kicker">{log_count} readable log file(s)</p>
          {''.join(log_blocks) or '<p>No logs configured</p>'}
        </section>
        <section id="api-section" class="api-section panel">
          <h2>API</h2>
          <p><code>GET /status.json</code></p>
        </section>
      </main>
    </div>
  </div>
</body>
</html>"""
    return html_text.encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    base_dir = Path(__file__).resolve().parent
    metadata = {}

    def log_message(self, fmt, *args):
        return

    def send_bytes(self, code, content_type, payload):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        path = urlparse(self.path).path
        status = collect_status(self.metadata, self.base_dir)
        if path == "/status.json":
            self.send_bytes(200, "application/json; charset=utf-8", json.dumps(status, ensure_ascii=False, indent=2).encode("utf-8"))
            return
        if path == "/":
            self.send_bytes(200, "text/html; charset=utf-8", render_dashboard(status))
            return
        self.send_bytes(404, "text/plain; charset=utf-8", b"not found")


def main():
    parser = argparse.ArgumentParser(description="fake-ui bridge local dashboard")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    if args.host != DEFAULT_HOST:
        raise SystemExit("dashboard is local-only; host must be 127.0.0.1")
    Handler.metadata = load_metadata(Handler.base_dir)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"fake-ui bridge dashboard: http://{args.host}:{args.port}/")
    server.serve_forever()


if __name__ == "__main__":
    main()
'''


def open_dashboard_sh():
    return f"""#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
PORT="${{FAKE_UI_BRIDGE_DASHBOARD_PORT:-{DASHBOARD_PORT}}}"
URL="http://{DASHBOARD_HOST}:$PORT/"
PYTHON="${{PYTHON:-}}"
if [ -z "$PYTHON" ]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON=python3
  elif command -v python >/dev/null 2>&1; then
    PYTHON=python
  else
    echo "未找到 Python。请先安装 Python 3。" >&2
    exit 1
  fi
fi
"$PYTHON" bridge-dashboard.py --host {DASHBOARD_HOST} --port "$PORT" > bridge-dashboard.out.log 2> bridge-dashboard.err.log &
sleep 1
if command -v open >/dev/null 2>&1; then
  open "$URL"
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$URL" >/dev/null 2>&1 || true
fi
echo "$URL"
"""


def open_dashboard_ps1():
    return f"""$ErrorActionPreference = "Stop"
$Port = if ($env:FAKE_UI_BRIDGE_DASHBOARD_PORT) {{ $env:FAKE_UI_BRIDGE_DASHBOARD_PORT }} else {{ "{DASHBOARD_PORT}" }}
$Url = "http://{DASHBOARD_HOST}:$Port/"
$Python = Get-Command python.exe -ErrorAction SilentlyContinue
if (-not $Python) {{
  $Python = Get-Command py.exe -ErrorAction SilentlyContinue
}}
if (-not $Python) {{
  throw "未找到 Python。请先安装 Python 3。"
}}
Start-Process -FilePath $Python.Source -ArgumentList @("bridge-dashboard.py", "--host", "{DASHBOARD_HOST}", "--port", $Port) -WorkingDirectory $PSScriptRoot
Start-Sleep -Seconds 1
Start-Process $Url
Write-Host $Url
"""


def add_dashboard_assets(tar, root, bundle_kind, identifier, platform, tunnels):
    metadata = dashboard_metadata(bundle_kind, identifier, platform, tunnels)
    add_text(tar, f"{root}/bridge-dashboard.json", json.dumps(metadata, indent=2, ensure_ascii=False))
    add_text(tar, f"{root}/bridge-dashboard.py", dashboard_script(), mode=0o755)
    if safe_id(platform).lower() == "windows":
        add_text(tar, f"{root}/open-dashboard.ps1", open_dashboard_ps1())
    else:
        add_text(tar, f"{root}/open-dashboard.sh", open_dashboard_sh(), mode=0o755)


def bootstrap_agent_script():
    return r'''#!/usr/bin/env python3
import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import ProxyHandler, Request, build_opener


BASE_DIR = Path(__file__).resolve().parent
PROFILE_PATH = BASE_DIR / "agent-profile.json"


def read_json(path):
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path, data):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def is_complete():
    required = ["xray-bridge.json", "bridge-dashboard.json", "agent-state.json"]
    return all((BASE_DIR / name).exists() for name in required)


def clear_pairing_token(profile):
    profile["pairing_token"] = ""
    write_json(PROFILE_PATH, profile)


def bootstrap_url(panel_url):
    base = str(panel_url or "").strip()
    if not base:
        raise SystemExit("agent-profile.json panel_url is required")
    return urljoin(base.rstrip("/") + "/", "/api/agents/bootstrap")


def request_bootstrap(profile):
    reserved = profile.get("reserved") or {}
    payload = {
        "schema": profile.get("schema"),
        "token_id": profile.get("token_id"),
        "pairing_token": profile.get("pairing_token"),
        "bridge_id": profile.get("bridge_id"),
        "bundle_kind": profile.get("bundle_kind"),
        "platform": profile.get("platform"),
        "agent_id": reserved.get("agent_id") or profile.get("agent_id"),
        "agent_name": profile.get("agent_name"),
        "capabilities": reserved.get("capabilities") or profile.get("capabilities") or [],
    }
    raw = json.dumps(payload).encode("utf-8")
    request = Request(
        bootstrap_url(profile.get("panel_url")),
        data=raw,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        opener = build_opener(ProxyHandler({}))
        with opener.open(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise SystemExit(f"bootstrap failed: HTTP {exc.code} {detail}") from exc
    except URLError as exc:
        raise SystemExit(f"bootstrap failed: {exc}") from exc


def main():
    if not PROFILE_PATH.exists():
        raise SystemExit("agent-profile.json is missing")
    profile = read_json(PROFILE_PATH)
    if is_complete():
        if str(profile.get("pairing_token") or "").strip():
            clear_pairing_token(profile)
        print("fake-ui agent bootstrap already complete")
        return
    if not str(profile.get("pairing_token") or "").strip():
        raise SystemExit("agent-profile.json pairing_token is missing")
    result = request_bootstrap(profile)
    if not result.get("ok"):
        raise SystemExit(f"bootstrap failed: {result.get('error') or 'unknown error'}")
    write_json(BASE_DIR / "xray-bridge.json", result.get("xray_config") or {})
    write_json(BASE_DIR / "bridge-dashboard.json", result.get("dashboard_metadata") or {})
    write_json(
        BASE_DIR / "agent-state.json",
        {
            "agent": result.get("agent") or {},
            "install": result.get("install") or {},
            "bridge_id": profile.get("bridge_id"),
            "bundle_kind": profile.get("bundle_kind"),
            "platform": profile.get("platform"),
        },
    )
    clear_pairing_token(profile)
    print("fake-ui agent bootstrap complete")


if __name__ == "__main__":
    main()
'''


def agent_profile(pairing, panel_url, bundle_kind, bridge_id, platform, agent_name):
    record = dict((pairing or {}).get("record") or {})
    capabilities = list(record.get("capabilities") or [])
    agent_id = record.get("agent_id", "")
    return {
        "schema": 1,
        "panel_url": str(panel_url or ""),
        "token_id": record.get("token_id", ""),
        "pairing_token": (pairing or {}).get("pairing_token", ""),
        "bridge_id": record.get("bridge_id") or safe_id(bridge_id),
        "bundle_kind": record.get("bundle_kind") or bundle_kind,
        "platform": record.get("platform") or safe_id(platform).lower(),
        "agent_name": str(agent_name or safe_id(bridge_id)),
        "dashboard": {"host": DASHBOARD_HOST, "port": DASHBOARD_PORT},
        "reserved": {"agent_id": agent_id, "capabilities": capabilities},
        "capabilities": capabilities,
        "agent_id": agent_id,
    }


def agent_profile_template(platform="linux"):
    return {
        "schema": 1,
        "panel_url": "https://your-panel.example.com",
        "token_id": "pair_example_token_id",
        "pairing_token": "replace-with-one-time-pairing-token",
        "bridge_id": "example-bridge",
        "bundle_kind": "dedicated",
        "platform": safe_id(platform).lower(),
        "agent_name": "Example bridge agent",
        "dashboard": {"host": DASHBOARD_HOST, "port": DASHBOARD_PORT},
        "reserved": {"agent_id": "", "capabilities": []},
        "capabilities": [],
        "agent_id": "",
    }


def add_pairing_assets(tar, root, pairing, panel_url, bundle_kind, bridge_id, platform, agent_name):
    profile = agent_profile(pairing, panel_url, bundle_kind, bridge_id, platform, agent_name)
    add_text(tar, f"{root}/agent-profile.json", json.dumps(profile, indent=2, ensure_ascii=False))
    add_text(tar, f"{root}/bootstrap-agent.py", bootstrap_agent_script(), mode=0o755)


def dedicated_linux_root(tunnel):
    return f"/opt/fake-ui-tunnel/{safe_id(tunnel.get('id'))}"


def dedicated_linux_service_text(tunnel):
    root = dedicated_linux_root(tunnel)
    return f"""[Unit]
Description=fake-ui tunnel {safe_id(tunnel.get('id'))}
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart={root}/xray run -c {root}/xray-bridge.json
Restart=always
RestartSec=3
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
"""


def dedicated_install_linux(tunnel):
    root = dedicated_linux_root(tunnel)
    service = dedicated_linux_service_id(tunnel)
    bootstrap = shell_bootstrap_snippet()
    return f"""#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "请使用 root 执行: sudo bash install-linux.sh" >&2
  exit 1
fi

ROOT="{root}"
SERVICE="/etc/systemd/system/{service}"
mkdir -p "$ROOT"
{bootstrap}\
cp "$(dirname "$0")/xray-bridge.json" "$ROOT/xray-bridge.json"
cp "$(dirname "$0")/{service}" "$SERVICE"

if [ -x "$ROOT/xray" ]; then
  :
elif command -v xray >/dev/null 2>&1; then
  ln -sf "$(command -v xray)" "$ROOT/xray"
else
  echo "未找到 xray。请先安装 Xray，或把 xray 二进制放到 $ROOT/xray" >&2
  exit 1
fi

"$ROOT/xray" run -test -c "$ROOT/xray-bridge.json"
systemctl daemon-reload
systemctl enable --now "{service}"
systemctl restart "{service}"
bash "$(dirname "$0")/status-linux.sh"
"""


def dedicated_uninstall_linux(tunnel):
    root = dedicated_linux_root(tunnel)
    service = dedicated_linux_service_id(tunnel)
    return f"""#!/usr/bin/env bash
set -euo pipefail
if [ "$(id -u)" -ne 0 ]; then
  echo "请使用 root 执行: sudo bash uninstall-linux.sh" >&2
  exit 1
fi
systemctl disable --now "{service}" >/dev/null 2>&1 || true
rm -f "/etc/systemd/system/{service}"
systemctl daemon-reload
rm -rf "{root}"
echo "已卸载 {service}"
"""


def dedicated_install_windows(tunnel):
    bid = safe_id(tunnel.get("id"))
    task = dedicated_windows_task_name(tunnel)
    bootstrap = powershell_bootstrap_snippet()
    return f"""$ErrorActionPreference = "Stop"
$Root = Join-Path $env:ProgramData "fake-ui-tunnel\\{bid}"
New-Item -ItemType Directory -Force -Path $Root | Out-Null
{bootstrap}\
Copy-Item -Force -Path (Join-Path $PSScriptRoot "xray-bridge.json") -Destination (Join-Path $Root "xray-bridge.json")
$Xray = Join-Path $Root "xray.exe"
if (-not (Test-Path $Xray)) {{
  $Found = Get-Command xray.exe -ErrorAction SilentlyContinue
  if ($Found) {{
    Copy-Item -Force -Path $Found.Source -Destination $Xray
  }} else {{
    throw "未找到 xray.exe。请把 xray.exe 放到 $Root"
  }}
}}
& $Xray run -test -c (Join-Path $Root "xray-bridge.json")
$Action = New-ScheduledTaskAction -Execute $Xray -Argument "run -c `"$Root\\xray-bridge.json`""
$Trigger = New-ScheduledTaskTrigger -AtStartup
$Principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest
Register-ScheduledTask -TaskName "{task}" -Action $Action -Trigger $Trigger -Principal $Principal -Force | Out-Null
Start-ScheduledTask -TaskName "{task}"
& (Join-Path $PSScriptRoot "status-windows.ps1")
"""


def dedicated_uninstall_windows(tunnel):
    bid = safe_id(tunnel.get("id"))
    task = dedicated_windows_task_name(tunnel)
    return f"""$ErrorActionPreference = "Stop"
Unregister-ScheduledTask -TaskName "{task}" -Confirm:$false -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force -Path (Join-Path $env:ProgramData "fake-ui-tunnel\\{bid}") -ErrorAction SilentlyContinue
Write-Host "已卸载 {task}"
"""


def build_bundle(tunnel, bridge_config, platform):
    platform = safe_id(platform).lower()
    if platform == "macos":
        return build_macos_bundle(tunnel, bridge_config)
    if platform not in {"linux", "windows"}:
        raise RuntimeError("bridge platform is invalid")

    root = bundle_root(tunnel, platform)
    content = io.BytesIO()
    with tarfile.open(fileobj=content, mode="w:gz") as tar:
        add_text(tar, f"{root}/xray-bridge.json", json.dumps(bridge_config, indent=2, ensure_ascii=False))
        add_text(tar, f"{root}/README.md", readme_text(tunnel, platform))
        add_dashboard_assets(tar, root, "dedicated", tunnel.get("id"), platform, [tunnel])
        if platform == "linux":
            service = dedicated_linux_service_id(tunnel)
            add_text(tar, f"{root}/{service}", dedicated_linux_service_text(tunnel))
            add_text(tar, f"{root}/install-linux.sh", dedicated_install_linux(tunnel), mode=0o755)
            add_text(tar, f"{root}/uninstall-linux.sh", dedicated_uninstall_linux(tunnel), mode=0o755)
            add_text(tar, f"{root}/status-linux.sh", agent_status_script([tunnel], platform), mode=0o755)
        else:
            add_text(tar, f"{root}/install-windows.ps1", dedicated_install_windows(tunnel))
            add_text(tar, f"{root}/uninstall-windows.ps1", dedicated_uninstall_windows(tunnel))
            add_text(tar, f"{root}/status-windows.ps1", agent_status_script([tunnel], platform))
    return content.getvalue()


def build_paired_bundle(tunnel, pairing, panel_url, platform):
    platform = safe_id(platform).lower()
    if platform not in {"macos", "linux", "windows"}:
        raise RuntimeError("bridge platform is invalid")
    if platform == "macos":
        root = bundle_dir(tunnel)
    else:
        root = bundle_root(tunnel, platform)
    content = io.BytesIO()
    with tarfile.open(fileobj=content, mode="w:gz") as tar:
        add_text(tar, f"{root}/README.md", readme_text(tunnel, platform))
        add_dashboard_assets(tar, root, "dedicated", tunnel.get("id"), platform, [tunnel])
        add_pairing_assets(
            tar,
            root,
            pairing,
            panel_url,
            "dedicated",
            tunnel.get("id"),
            platform,
            tunnel.get("name") or tunnel.get("id"),
        )
        if platform == "macos":
            add_text(tar, f"{root}/{service_id(tunnel)}.plist", plist_text(tunnel))
            add_text(tar, f"{root}/install-macos.sh", install_script(tunnel), mode=0o755)
            add_text(tar, f"{root}/uninstall-macos.sh", uninstall_script(tunnel), mode=0o755)
            add_text(tar, f"{root}/status-macos.sh", status_script(tunnel), mode=0o755)
        elif platform == "linux":
            service = dedicated_linux_service_id(tunnel)
            add_text(tar, f"{root}/{service}", dedicated_linux_service_text(tunnel))
            add_text(tar, f"{root}/install-linux.sh", dedicated_install_linux(tunnel), mode=0o755)
            add_text(tar, f"{root}/uninstall-linux.sh", dedicated_uninstall_linux(tunnel), mode=0o755)
            add_text(tar, f"{root}/status-linux.sh", agent_status_script([tunnel], platform), mode=0o755)
        else:
            add_text(tar, f"{root}/install-windows.ps1", dedicated_install_windows(tunnel))
            add_text(tar, f"{root}/uninstall-windows.ps1", dedicated_uninstall_windows(tunnel))
            add_text(tar, f"{root}/status-windows.ps1", agent_status_script([tunnel], platform))
    return content.getvalue()


def agent_service_id(bridge_id):
    return f"com.fakeui.bridge.{safe_id(bridge_id)}"


def agent_root(bridge_id, platform):
    return f"{safe_id(bridge_id)}-{safe_id(platform)}-bridge"


def agent_plist_text(bridge_id):
    sid = agent_service_id(bridge_id)
    bid = safe_id(bridge_id)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{sid}</string>
  <key>ProgramArguments</key>
  <array>
    <string>__HOME__/.fake-ui/bin/xray</string>
    <string>run</string>
    <string>-c</string>
    <string>__HOME__/.fake-ui/bridges/{bid}/xray-bridge.json</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>__HOME__/.fake-ui/bridges/{bid}/bridge.out.log</string>
  <key>StandardErrorPath</key>
  <string>__HOME__/.fake-ui/bridges/{bid}/bridge.err.log</string>
</dict>
</plist>
"""


def agent_install_macos(bridge_id):
    sid = agent_service_id(bridge_id)
    bid = safe_id(bridge_id)
    bootstrap = shell_bootstrap_snippet()
    return f"""#!/usr/bin/env bash
set -euo pipefail

ROOT="$HOME/.fake-ui"
BRIDGE_DIR="$ROOT/bridges/{bid}"
PLIST="$HOME/Library/LaunchAgents/{sid}.plist"

mkdir -p "$ROOT/bin" "$BRIDGE_DIR" "$HOME/Library/LaunchAgents"
{bootstrap}\
cp "$(dirname "$0")/xray-bridge.json" "$BRIDGE_DIR/xray-bridge.json"
cp "$(dirname "$0")/{sid}.plist" "$PLIST"
sed -i '' "s|__HOME__|$HOME|g" "$PLIST"

if [ ! -x "$ROOT/bin/xray" ]; then
  if command -v xray >/dev/null 2>&1; then
    ln -sf "$(command -v xray)" "$ROOT/bin/xray"
  else
    echo "未找到 xray。请先安装 Xray，或把 xray 二进制放到 $ROOT/bin/xray" >&2
    exit 1
  fi
fi

"$ROOT/bin/xray" run -test -c "$BRIDGE_DIR/xray-bridge.json"
launchctl bootout "gui/$(id -u)" "$PLIST" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl kickstart -k "gui/$(id -u)/{sid}"
"$(dirname "$0")/status-macos.sh"
"""


def agent_uninstall_macos(bridge_id):
    sid = agent_service_id(bridge_id)
    bid = safe_id(bridge_id)
    return f"""#!/usr/bin/env bash
set -euo pipefail
PLIST="$HOME/Library/LaunchAgents/{sid}.plist"
launchctl bootout "gui/$(id -u)" "$PLIST" >/dev/null 2>&1 || true
rm -f "$PLIST"
rm -rf "$HOME/.fake-ui/bridges/{bid}"
echo "已卸载 {sid}"
"""


def linux_service_text(bridge_id):
    bid = safe_id(bridge_id)
    return f"""[Unit]
Description=fake-ui shared bridge {bid}
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/opt/fake-ui-bridge/{bid}/xray run -c /opt/fake-ui-bridge/{bid}/xray-bridge.json
Restart=always
RestartSec=3
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
"""


def agent_install_linux(bridge_id):
    bid = safe_id(bridge_id)
    service = f"fake-ui-bridge-{bid}.service"
    bootstrap = shell_bootstrap_snippet()
    return f"""#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "请使用 root 执行: sudo bash install-linux.sh" >&2
  exit 1
fi

ROOT="/opt/fake-ui-bridge/{bid}"
SERVICE="/etc/systemd/system/{service}"
mkdir -p "$ROOT"
{bootstrap}\
cp "$(dirname "$0")/xray-bridge.json" "$ROOT/xray-bridge.json"
cp "$(dirname "$0")/{service}" "$SERVICE"

if [ -x "$ROOT/xray" ]; then
  :
elif command -v xray >/dev/null 2>&1; then
  ln -sf "$(command -v xray)" "$ROOT/xray"
else
  echo "未找到 xray。请先安装 Xray，或把 xray 二进制放到 $ROOT/xray" >&2
  exit 1
fi

"$ROOT/xray" run -test -c "$ROOT/xray-bridge.json"
systemctl daemon-reload
systemctl enable --now "{service}"
systemctl restart "{service}"
bash "$(dirname "$0")/status-linux.sh"
"""


def agent_uninstall_linux(bridge_id):
    bid = safe_id(bridge_id)
    service = f"fake-ui-bridge-{bid}.service"
    return f"""#!/usr/bin/env bash
set -euo pipefail
if [ "$(id -u)" -ne 0 ]; then
  echo "请使用 root 执行: sudo bash uninstall-linux.sh" >&2
  exit 1
fi
systemctl disable --now "{service}" >/dev/null 2>&1 || true
rm -f "/etc/systemd/system/{service}"
systemctl daemon-reload
rm -rf "/opt/fake-ui-bridge/{bid}"
echo "已卸载 {service}"
"""


def agent_install_windows(bridge_id):
    bid = safe_id(bridge_id)
    task = f"FakeUIBridge-{bid}"
    bootstrap = powershell_bootstrap_snippet()
    return f"""$ErrorActionPreference = "Stop"
$Root = Join-Path $env:ProgramData "fake-ui-bridge\\{bid}"
New-Item -ItemType Directory -Force -Path $Root | Out-Null
{bootstrap}\
Copy-Item -Force -Path (Join-Path $PSScriptRoot "xray-bridge.json") -Destination (Join-Path $Root "xray-bridge.json")
$Xray = Join-Path $Root "xray.exe"
if (-not (Test-Path $Xray)) {{
  $Found = Get-Command xray.exe -ErrorAction SilentlyContinue
  if ($Found) {{
    Copy-Item -Force -Path $Found.Source -Destination $Xray
  }} else {{
    throw "未找到 xray.exe。请把 xray.exe 放到 $Root"
  }}
}}
& $Xray run -test -c (Join-Path $Root "xray-bridge.json")
$Action = New-ScheduledTaskAction -Execute $Xray -Argument "run -c `"$Root\\xray-bridge.json`""
$Trigger = New-ScheduledTaskTrigger -AtStartup
$Principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest
Register-ScheduledTask -TaskName "{task}" -Action $Action -Trigger $Trigger -Principal $Principal -Force | Out-Null
Start-ScheduledTask -TaskName "{task}"
& (Join-Path $PSScriptRoot "status-windows.ps1")
"""


def agent_uninstall_windows(bridge_id):
    bid = safe_id(bridge_id)
    task = f"FakeUIBridge-{bid}"
    return f"""$ErrorActionPreference = "Stop"
Unregister-ScheduledTask -TaskName "{task}" -Confirm:$false -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force -Path (Join-Path $env:ProgramData "fake-ui-bridge\\{bid}") -ErrorAction SilentlyContinue
Write-Host "已卸载 {task}"
"""


def agent_status_script(tunnels, platform):
    lines = []
    for tunnel in tunnels:
        target_host = tunnel.get("target_host") or "127.0.0.1"
        target_port = int(tunnel.get("target_port") or 0)
        if tunnel.get("kind") == "private_tcp":
            lines.append(f"nc -z {target_host} {target_port} && echo \"local tcp ok: {target_host}:{target_port}\"")
        else:
            lines.append(f"curl -fsS http://{target_host}:{target_port}/ >/dev/null && echo \"local service ok: http://{target_host}:{target_port}/\"")
    checks = "\n".join(lines) or "echo \"no local checks\""
    if platform == "windows":
        ps_checks = []
        for tunnel in tunnels:
            target_host = tunnel.get("target_host") or "127.0.0.1"
            target_port = int(tunnel.get("target_port") or 0)
            if tunnel.get("kind") == "private_tcp":
                ps_checks.append(f"Test-NetConnection -ComputerName {target_host} -Port {target_port} | Format-List")
            else:
                ps_checks.append(f"Invoke-WebRequest -UseBasicParsing -Uri http://{target_host}:{target_port}/ | Out-Null; Write-Host \"local service ok: http://{target_host}:{target_port}/\"")
        return "\n".join(ps_checks) + "\n"
    return f"""#!/usr/bin/env bash
set -euo pipefail
{checks}
"""


def agent_readme_text(bridge_id, platform, tunnels):
    label = platform_label(platform)
    rows = "\n".join(
        f"- {item.get('id')}: {item.get('target_host')}:{item.get('target_port')} via :{item.get('portal_port')}"
        for item in tunnels
    )
    return f"""# fake-ui Shared {label} Bridge Agent

Bridge: {bridge_id}
Platform: {platform}

Services:

{rows}

Install:

{command_block(install_command(platform), platform)}

Local dashboard:

{command_block(dashboard_command(platform), platform)}

Open http://127.0.0.1:19090/

Status:

{command_block(status_command(platform), platform)}

Uninstall:

{command_block(uninstall_command(platform), platform)}
"""


def build_agent_bundle(bridge_id, tunnels, bridge_config, platform):
    platform = safe_id(platform).lower()
    if platform not in {"macos", "linux", "windows"}:
        raise RuntimeError("bridge platform is invalid")
    bid = safe_id(bridge_id)
    root = agent_root(bid, platform)
    content = io.BytesIO()
    with tarfile.open(fileobj=content, mode="w:gz") as tar:
        add_text(tar, f"{root}/xray-bridge.json", json.dumps(bridge_config, indent=2, ensure_ascii=False))
        add_text(tar, f"{root}/README.md", agent_readme_text(bid, platform, tunnels))
        add_dashboard_assets(tar, root, "shared", bid, platform, tunnels)
        if platform == "macos":
            add_text(tar, f"{root}/{agent_service_id(bid)}.plist", agent_plist_text(bid))
            add_text(tar, f"{root}/install-macos.sh", agent_install_macos(bid), mode=0o755)
            add_text(tar, f"{root}/uninstall-macos.sh", agent_uninstall_macos(bid), mode=0o755)
            add_text(tar, f"{root}/status-macos.sh", agent_status_script(tunnels, platform), mode=0o755)
        elif platform == "linux":
            service = f"fake-ui-bridge-{bid}.service"
            add_text(tar, f"{root}/{service}", linux_service_text(bid))
            add_text(tar, f"{root}/install-linux.sh", agent_install_linux(bid), mode=0o755)
            add_text(tar, f"{root}/uninstall-linux.sh", agent_uninstall_linux(bid), mode=0o755)
            add_text(tar, f"{root}/status-linux.sh", agent_status_script(tunnels, platform), mode=0o755)
        else:
            add_text(tar, f"{root}/install-windows.ps1", agent_install_windows(bid))
            add_text(tar, f"{root}/uninstall-windows.ps1", agent_uninstall_windows(bid))
            add_text(tar, f"{root}/status-windows.ps1", agent_status_script(tunnels, platform))
    return content.getvalue()


def build_paired_agent_bundle(bridge_id, tunnels, pairing, panel_url, platform):
    platform = safe_id(platform).lower()
    if platform not in {"macos", "linux", "windows"}:
        raise RuntimeError("bridge platform is invalid")
    bid = safe_id(bridge_id)
    root = agent_root(bid, platform)
    content = io.BytesIO()
    with tarfile.open(fileobj=content, mode="w:gz") as tar:
        add_text(tar, f"{root}/README.md", agent_readme_text(bid, platform, tunnels))
        add_dashboard_assets(tar, root, "shared", bid, platform, tunnels)
        add_pairing_assets(tar, root, pairing, panel_url, "shared", bid, platform, bid)
        if platform == "macos":
            add_text(tar, f"{root}/{agent_service_id(bid)}.plist", agent_plist_text(bid))
            add_text(tar, f"{root}/install-macos.sh", agent_install_macos(bid), mode=0o755)
            add_text(tar, f"{root}/uninstall-macos.sh", agent_uninstall_macos(bid), mode=0o755)
            add_text(tar, f"{root}/status-macos.sh", agent_status_script(tunnels, platform), mode=0o755)
        elif platform == "linux":
            service = f"fake-ui-bridge-{bid}.service"
            add_text(tar, f"{root}/{service}", linux_service_text(bid))
            add_text(tar, f"{root}/install-linux.sh", agent_install_linux(bid), mode=0o755)
            add_text(tar, f"{root}/uninstall-linux.sh", agent_uninstall_linux(bid), mode=0o755)
            add_text(tar, f"{root}/status-linux.sh", agent_status_script(tunnels, platform), mode=0o755)
        else:
            add_text(tar, f"{root}/install-windows.ps1", agent_install_windows(bid))
            add_text(tar, f"{root}/uninstall-windows.ps1", agent_uninstall_windows(bid))
            add_text(tar, f"{root}/status-windows.ps1", agent_status_script(tunnels, platform))
    return content.getvalue()
