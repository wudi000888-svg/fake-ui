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
if [ -f "$SCRIPT_DIR/agent-profile.json" ] && [ -f "$SCRIPT_DIR/bootstrap-agent.py" ]; then
  "$PYTHON" "$SCRIPT_DIR/bootstrap-agent.py"
fi
if [ ! -f "$SCRIPT_DIR/xray-bridge.json" ]; then
  echo "未找到 xray-bridge.json。请先运行 bootstrap-agent.py 或放入静态配置。" >&2
  exit 1
fi
if [ -f "$SCRIPT_DIR/bridge-dashboard.py" ]; then
  "$PYTHON" - <<'PY'
import importlib.util
from pathlib import Path
base = Path.cwd()
spec = importlib.util.spec_from_file_location("bridge_dashboard", base / "bridge-dashboard.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
metadata = module.load_metadata(base)
try:
    result = module.apply_network_bypass(metadata, base)
    print(result.get("message", "已应用代理兼容"))
except Exception as exc:
    print(f"代理兼容保持默认：{exc}")
PY
fi
"""


def powershell_bootstrap_snippet():
    return """$Profile = Join-Path $PSScriptRoot "agent-profile.json"
$Bootstrap = Join-Path $PSScriptRoot "bootstrap-agent.py"
$Python = Get-Command python.exe -ErrorAction SilentlyContinue
if (-not $Python) {
  $Python = Get-Command py.exe -ErrorAction SilentlyContinue
}
if (-not $Python) {
  throw "未找到 Python。请先安装 Python 3。"
}
if ((Test-Path $Profile) -and (Test-Path $Bootstrap)) {
  & $Python.Source $Bootstrap
}
if (-not (Test-Path (Join-Path $PSScriptRoot "xray-bridge.json"))) {
  throw "未找到 xray-bridge.json。请先运行 bootstrap-agent.py 或放入静态配置。"
}
if (Test-Path (Join-Path $PSScriptRoot "bridge-dashboard.py")) {
  try {
    & $Python.Source -c "import importlib.util; from pathlib import Path; base=Path.cwd(); spec=importlib.util.spec_from_file_location('bridge_dashboard', base / 'bridge-dashboard.py'); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); print(m.apply_network_bypass(m.load_metadata(base), base).get('message', '已应用代理兼容'))"
  } catch {
    Write-Host "代理兼容保持默认：$($_.Exception.Message)"
  }
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
    return {"macos": "macOS", "linux": "Linux", "windows": "Windows", "auto": "通用"}.get(safe_id(platform).lower(), platform)


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
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 19090
IMPORT_FILENAMES = {"xray-bridge.json", "bridge-dashboard.json", "agent-profile.json"}


def allowed_host_header(value, port):
    host = str(value or "").strip()
    if not host:
        return True
    if host.startswith("["):
        end = host.find("]")
        name = host[:end + 1].lower() if end >= 0 else host.lower()
        suffix = host[end + 1:] if end >= 0 else ""
    else:
        name, sep, suffix = host.partition(":")
        name = name.lower()
        suffix = sep + suffix if sep else ""
    if name not in {"127.0.0.1", "localhost", "[::1]"}:
        return False
    if not suffix:
        return True
    return suffix == f":{int(port)}"


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


def platform_name(metadata):
    value = str((metadata or {}).get("platform") or "").strip().lower()
    if value in {"macos", "linux", "windows"}:
        return value
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform.startswith("win"):
        return "windows"
    return value or sys.platform


def xray_config_path(base_dir, metadata):
    rel_path = (metadata.get("xray_config") or {}).get("path") or "xray-bridge.json"
    return base_dir / rel_path


def route_probe(platform, address):
    address = str(address or "").strip()
    if not address:
        return {"ok": False, "message": "missing address"}
    if platform == "macos":
        return command_probe(["route", "-n", "get", address])
    if platform == "linux":
        return command_probe(["ip", "route", "get", address])
    if platform == "windows":
        command = (
            "$route = Find-NetRoute -RemoteIPAddress '" + address.replace("'", "''") + "' | "
            "Sort-Object -Property RouteMetric | Select-Object -First 1; "
            "if ($route) { $route.InterfaceAlias }"
        )
        return command_probe(["powershell", "-NoProfile", "-Command", command])
    return {"ok": False, "message": f"unsupported platform: {platform}"}


def dns_probe(platform):
    if platform == "macos":
        return command_probe(["scutil", "--dns"])
    if platform == "linux":
        probe = command_probe(["resolvectl", "dns"])
        if probe.get("ok"):
            return probe
        try:
            return {"ok": True, "message": Path("/etc/resolv.conf").read_text(encoding="utf-8")[:1200]}
        except Exception as exc:
            return {"ok": False, "message": str(exc)}
    if platform == "windows":
        return command_probe(["powershell", "-NoProfile", "-Command", "Get-DnsClientServerAddress | Format-Table -AutoSize"])
    return {"ok": False, "message": f"unsupported platform: {platform}"}


def parse_route_interface(message):
    text = str(message or "")
    for pattern in (r"\binterface:\s*([^\s]+)", r"\bdev\s+([^\s]+)"):
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) == 1 and len(lines[0]) <= 80:
        return lines[0]
    return ""


def is_tunnel_interface(name):
    value = str(name or "").strip().lower()
    return value.startswith(("utun", "tun", "tap", "wg", "ppp")) or any(
        token in value for token in ("wintun", "clash", "shadowrocket", "tailscale", "zerotier")
    )


def fake_dns_detected(message):
    text = str(message or "").lower()
    return "198.18." in text or "198.19." in text or "utun" in text or "fake-ip" in text


def physical_interfaces_from_ifconfig():
    probe = command_probe(["ifconfig"], timeout=2.0)
    if not probe.get("ok"):
        return []
    candidates = []
    blocks = re.split(r"\n(?=[a-zA-Z0-9_.-]+:\s)", probe.get("message") or "")
    for block in blocks:
        first = block.split(":", 1)[0].strip()
        if not first or is_tunnel_interface(first) or first.startswith(("lo", "awdl", "llw", "bridge", "gif", "stf", "anpi")):
            continue
        if "status: active" in block and re.search(r"\binet\s+\d+\.\d+\.\d+\.\d+", block):
            candidates.append(first)
    return sorted(candidates, key=lambda item: (0 if item == "en0" else 1, item))


def physical_interfaces_from_linux():
    probe = command_probe(["ip", "-o", "-4", "addr", "show", "scope", "global"], timeout=2.0)
    if not probe.get("ok"):
        return []
    interfaces = []
    for line in (probe.get("message") or "").splitlines():
        parts = line.split()
        if len(parts) >= 2:
            name = parts[1].rstrip(":")
            if not is_tunnel_interface(name) and not name.startswith(("lo", "docker", "br-", "veth")):
                interfaces.append(name)
    return sorted(set(interfaces))


def detect_recommended_interface(platform):
    override = str(os.getenv("FAKE_UI_BRIDGE_OUTBOUND_INTERFACE") or "").strip()
    if override:
        return override
    default_route = route_probe(platform, "1.1.1.1")
    routed = parse_route_interface(default_route.get("message"))
    if routed and not is_tunnel_interface(routed):
        return routed
    if platform == "macos":
        candidates = physical_interfaces_from_ifconfig()
        return candidates[0] if candidates else ""
    if platform == "linux":
        candidates = physical_interfaces_from_linux()
        return candidates[0] if candidates else ""
    return ""


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


def write_json_atomic(path, data):
    raw = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(raw, encoding="utf-8")
    tmp.replace(path)


def load_json_file(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def reverse_outbounds(config):
    return [
        item
        for item in (config or {}).get("outbounds") or []
        if item.get("protocol") == "vless" and str(item.get("tag") or "").startswith("tunnel-reverse")
    ]


def reverse_server_addresses(config):
    values = []
    for outbound in reverse_outbounds(config):
        settings = outbound.get("settings") or {}
        address = str(settings.get("address") or "").strip()
        if address and address not in values:
            values.append(address)
    return values


def configured_bypass_interfaces(config):
    values = []
    for outbound in reverse_outbounds(config):
        sockopt = (outbound.get("streamSettings") or {}).get("sockopt") or {}
        interface = str(sockopt.get("interface") or "").strip()
        if interface and interface not in values:
            values.append(interface)
    return values


def apply_outbound_interface(config, interface):
    if not isinstance(config, dict):
        return config, 0
    interface = str(interface or "").strip()
    if not interface:
        return config, 0
    changed = 0
    for outbound in reverse_outbounds(config):
        stream = outbound.setdefault("streamSettings", {})
        sockopt = stream.setdefault("sockopt", {})
        if sockopt.get("interface") != interface:
            sockopt["interface"] = interface
            changed += 1
    return config, changed


def collect_network_status(metadata, base_dir):
    platform = platform_name(metadata)
    config = load_json_file(xray_config_path(base_dir, metadata)) or {}
    addresses = reverse_server_addresses(config)
    address = addresses[0] if addresses else ""
    dns = dns_probe(platform)
    vps_route = route_probe(platform, address) if address else {"ok": False, "message": "missing reverse server address"}
    vps_interface = parse_route_interface(vps_route.get("message"))
    bypass_interfaces = configured_bypass_interfaces(config)
    recommended = detect_recommended_interface(platform) or (bypass_interfaces[0] if bypass_interfaces else "")
    tun_detected = fake_dns_detected(dns.get("message")) or is_tunnel_interface(vps_interface)
    configured = bool(bypass_interfaces and (not recommended or recommended in bypass_interfaces))
    return {
        "platform": platform,
        "reverse_address": address,
        "dns": {"ok": dns.get("ok"), "fake_ip": fake_dns_detected(dns.get("message")), "message": dns.get("message", "")[:1200]},
        "vps_route": {"ok": vps_route.get("ok"), "interface": vps_interface, "message": vps_route.get("message", "")[:1200]},
        "tun_detected": bool(tun_detected),
        "recommended_interface": recommended,
        "bridge_bypass": {"configured": configured, "interfaces": bypass_interfaces},
    }


def apply_network_bypass(metadata, base_dir, interface=""):
    platform = platform_name(metadata)
    target_interface = str(interface or "").strip() or detect_recommended_interface(platform)
    if not target_interface:
        raise RuntimeError("未找到可用于直连 VPS 的物理网卡")
    path = xray_config_path(base_dir, metadata)
    config = load_json_file(path)
    if not isinstance(config, dict):
        raise RuntimeError("xray-bridge.json 格式不正确")
    updated, changed = apply_outbound_interface(config, target_interface)
    if not reverse_outbounds(updated):
        raise RuntimeError("未找到 tunnel reverse 出站")
    write_json_atomic(path, updated)
    return {"ok": True, "interface": target_interface, "changed": changed, "message": f"已设置 Bridge 出站直连网卡：{target_interface}"}


def parse_host_port(value):
    raw = str(value or "").strip()
    if not raw:
        return "", 0
    host, sep, port = raw.rpartition(":")
    if not sep:
        return raw, 0
    try:
        return host or "127.0.0.1", int(port)
    except Exception:
        return host or "127.0.0.1", 0


def infer_public_domain(address):
    value = str(address or "").strip().lower().rstrip(".")
    if not value or value in {"127.0.0.1", "localhost"}:
        return ""
    if re.fullmatch(r"\d+(?:\.\d+){3}", value):
        return ""
    return value if "." in value else ""


def infer_public_domain_from_filename(filename):
    raw = Path(str(filename or "")).name.lower()
    if not raw:
        return ""
    raw = re.sub(r"\s+\(\d+\)(?=\.json$|$)", "", raw)
    raw = re.sub(r"\.json$", "", raw)
    raw = re.sub(r"[-_\s]+(?:xray[-_\s]+bridge|bridge[-_\s]+dashboard|agent[-_\s]+profile)$", "", raw)
    dotted = infer_public_domain(raw)
    if dotted:
        return dotted
    parts = [part for part in re.split(r"[-_\s]+", raw) if part]
    tlds = {
        "com",
        "net",
        "org",
        "io",
        "app",
        "dev",
        "top",
        "xyz",
        "cn",
        "hk",
        "sg",
        "us",
        "uk",
        "jp",
        "de",
        "fr",
    }
    indexes = [index for index, part in enumerate(parts) if part in tlds]
    if not indexes:
        return ""
    return infer_public_domain(".".join(parts[: indexes[-1] + 1]))


def service_id_from_tag(tag, fallback):
    raw = str(tag or "")
    prefixes = ["tunnel-local-service-", "tunnel-local-service", "tunnel-reverse-out-", "tunnel-reverse-out"]
    for prefix in prefixes:
        if raw == prefix.rstrip("-"):
            return fallback
        if raw.startswith(prefix):
            clean = raw[len(prefix):].strip("-")
            return clean or fallback
    return fallback


def apply_public_domain(service, public_domain):
    domain = infer_public_domain(public_domain)
    if not domain:
        return service
    item = dict(service)
    generic_id = not item.get("id") or re.fullmatch(r"service-\d+", str(item.get("id") or ""))
    if generic_id:
        item["id"] = domain.replace(".", "-")
    if not item.get("name") or re.fullmatch(r"service-\d+", str(item.get("name") or "")):
        item["name"] = domain
    item["kind"] = "public_https"
    item["public_domain"] = domain
    item["public_url"] = f"https://{domain}/"
    return item


def infer_dashboard_services_from_xray_config(config, source_filename=""):
    outbounds = list((config or {}).get("outbounds") or [])
    reverse_by_inbound = {}
    reverse_by_suffix = {}
    for outbound in outbounds:
        settings = outbound.get("settings") or {}
        reverse = settings.get("reverse") or {}
        reverse_in = str(reverse.get("tag") or "").strip()
        tag = str(outbound.get("tag") or "")
        if reverse_in:
            reverse_by_inbound[reverse_in] = outbound
        if tag.startswith("tunnel-reverse-out-"):
            reverse_by_suffix[tag[len("tunnel-reverse-out-"):]] = outbound
        elif tag == "tunnel-reverse-out":
            reverse_by_suffix[""] = outbound
    route_by_outbound = {}
    for rule in ((config or {}).get("routing") or {}).get("rules") or []:
        outbound_tag = str(rule.get("outboundTag") or "")
        inbound_tags = rule.get("inboundTag") or []
        if isinstance(inbound_tags, str):
            inbound_tags = [inbound_tags]
        for inbound_tag in inbound_tags:
            route_by_outbound[outbound_tag] = str(inbound_tag or "")
    services = []
    for index, outbound in enumerate(outbounds):
        tag = str(outbound.get("tag") or "")
        if not tag.startswith("tunnel-local-service"):
            continue
        settings = outbound.get("settings") or {}
        host, port = parse_host_port(settings.get("redirect"))
        suffix = tag[len("tunnel-local-service"):].strip("-")
        reverse_in = route_by_outbound.get(tag)
        reverse = reverse_by_inbound.get(reverse_in) or reverse_by_suffix.get(suffix) or reverse_by_suffix.get("")
        reverse_settings = (reverse or {}).get("settings") or {}
        public_domain = infer_public_domain(reverse_settings.get("address"))
        service_id = service_id_from_tag(tag, public_domain.replace(".", "-") if public_domain else f"service-{index + 1}")
        services.append(
            {
                "id": service_id,
                "name": public_domain or service_id,
                "kind": "public_https" if public_domain else "private_tcp",
                "public_domain": public_domain,
                "public_url": f"https://{public_domain}/" if public_domain else "",
                "local": f"{host}:{port}" if port else host,
                "local_url": f"http://{host}:{port}/" if port else "",
                "target_host": host or "127.0.0.1",
                "target_port": int(port or 0),
                "portal_port": 0,
            }
        )
    filename_domain = infer_public_domain_from_filename(source_filename)
    if filename_domain and len(services) == 1 and not services[0].get("public_domain"):
        services[0] = apply_public_domain(services[0], filename_domain)
    return services


def validate_dashboard_metadata(content):
    if not isinstance(content, dict) or not isinstance(content.get("dashboard"), dict):
        raise RuntimeError("bridge-dashboard.json 格式不正确")
    if not isinstance(content.get("runtime"), dict):
        raise RuntimeError("bridge-dashboard.json 缺少 runtime")
    services = content.get("services")
    if services is not None and not isinstance(services, list):
        raise RuntimeError("bridge-dashboard.json services 格式不正确")


def validate_agent_profile(content):
    if not isinstance(content, dict) or content.get("schema") != 1:
        raise RuntimeError("agent-profile.json 格式不正确")
    if not content.get("panel_url") or not content.get("token_id"):
        raise RuntimeError("agent-profile.json 缺少配对信息")


def preserve_local_network_overrides(imported_config, existing_config):
    if not isinstance(imported_config, dict) or not isinstance(existing_config, dict):
        return imported_config
    existing_by_tag = {str(item.get("tag") or ""): item for item in reverse_outbounds(existing_config)}
    if not existing_by_tag:
        return imported_config
    merged = json.loads(json.dumps(imported_config))
    for outbound in reverse_outbounds(merged):
        existing = existing_by_tag.get(str(outbound.get("tag") or ""))
        if not existing:
            continue
        existing_settings = existing.get("settings") or {}
        imported_settings = outbound.setdefault("settings", {})
        existing_address = str(existing_settings.get("address") or "").strip()
        imported_address = str(imported_settings.get("address") or "").strip()
        if existing_address and existing_address != imported_address:
            imported_settings["address"] = existing_address
        existing_sockopt = (existing.get("streamSettings") or {}).get("sockopt")
        if existing_sockopt:
            outbound.setdefault("streamSettings", {})["sockopt"] = existing_sockopt
    return merged


def merge_metadata_services(metadata, services):
    merged = dict(metadata or {})
    if not isinstance(merged.get("dashboard"), dict):
        merged["dashboard"] = {"host": DEFAULT_HOST, "port": DEFAULT_PORT}
    existing_services = [item for item in merged.get("services") or [] if isinstance(item, dict)]
    by_id = {str(item.get("id") or ""): item for item in existing_services if item.get("id")}
    by_target = {
        (str(item.get("target_host") or "127.0.0.1"), int(item.get("target_port") or 0)): item
        for item in existing_services
        if item.get("target_port")
    }
    enriched = []
    for service in services or []:
        item = dict(service)
        existing = by_id.get(str(item.get("id") or "")) or by_target.get(
            (str(item.get("target_host") or "127.0.0.1"), int(item.get("target_port") or 0))
        )
        if existing:
            if not item.get("public_domain") and existing.get("public_domain"):
                item = apply_public_domain(item, existing.get("public_domain"))
            if not item.get("portal_port") and existing.get("portal_port"):
                item["portal_port"] = int(existing.get("portal_port") or 0)
            if (not item.get("name") or re.fullmatch(r"service-\d+", str(item.get("name") or ""))) and existing.get("name"):
                item["name"] = existing.get("name")
            if not item.get("kind") and existing.get("kind"):
                item["kind"] = existing.get("kind")
        enriched.append(item)
    merged["services"] = enriched
    if merged["services"]:
        first = merged["services"][0]
        merged["bridge_id"] = merged.get("bridge_id") or first.get("id") or "manual-bridge"
    return merged


def import_json_file(base_dir, filename, content):
    clean = str(filename or "").strip()
    if clean not in IMPORT_FILENAMES:
        raise RuntimeError("只支持导入 xray-bridge.json、bridge-dashboard.json 或 agent-profile.json")
    if not isinstance(content, dict):
        raise RuntimeError("导入内容必须是 JSON 对象")
    if clean == "bridge-dashboard.json":
        validate_dashboard_metadata(content)
    if clean == "agent-profile.json":
        validate_agent_profile(content)
    if clean == "xray-bridge.json":
        existing = load_json_file(base_dir / clean)
        content = preserve_local_network_overrides(content, existing)
    write_json_atomic(base_dir / clean, content)
    return clean


def restart_runtime(metadata, base_dir):
    runtime = metadata.get("runtime") or {}
    command = str(runtime.get("restart_command") or "").strip()
    if not command:
        raise RuntimeError("未配置重启命令")
    try:
        proc = subprocess.run(
            command,
            cwd=base_dir,
            shell=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=20,
        )
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "").strip() if isinstance(exc.stdout, str) else ""
        raise RuntimeError(f"重启命令超时：{output[:800]}") from exc
    except Exception as exc:
        raise RuntimeError(str(exc)) from exc
    output = (proc.stdout or "").strip()
    if proc.returncode != 0:
        detail = output[:1200] if output else f"exit {proc.returncode}"
        raise RuntimeError(f"重启失败：{detail}")
    message = output[:1200] if output else "重启命令已执行"
    return {"ok": True, "message": message}


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
        "network": collect_network_status(metadata, base_dir),
        "services": services,
        "logs": collect_logs(metadata, base_dir),
    }


def status_badge(ok):
    return "ok" if ok else "warn"


def redact_sensitive(value):
    text = str(value or "")
    text = re.sub(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", "[redacted-uuid]", text)
    text = re.sub(r'("(?:privateKey|publicKey|shortId|shortIds|pairing_token)"\s*:\s*)("[^"]*"|\[[^\]]*\])', r'\1"[redacted-secret]"', text)
    text = re.sub(r"(?i)(pairing[_-]?token\s*[=:]\s*)[^\s\"']+", r"\1[redacted-secret]", text)
    text = re.sub(r"(?i)((?:private|public)[_-]?key\s*[=:]\s*)[^\s\"']+", r"\1[redacted-secret]", text)
    text = re.sub(r"(?i)(short[_-]?id\s*[=:]\s*)[0-9a-f]{6,32}", r"\1[redacted-secret]", text)
    return text


def esc(value):
    return html.escape(redact_sensitive(value))


def badge_html(ok, text):
    return f"<span class='status-badge {status_badge(bool(ok))}'>{esc(text or 'unknown')}</span>"


def runtime_label(runtime):
    if runtime.get("ok"):
        return "运行中"
    message = str(runtime.get("message") or "")
    if "missing" in message.lower():
        return "未配置"
    return "需检查"


def config_label(xray_config):
    if xray_config.get("ok"):
        return "配置有效"
    message = str(xray_config.get("message") or "")
    if message == "missing":
        return "缺少配置"
    return "配置需检查"


def probe_label(probe):
    if probe.get("ok"):
        return "可达"
    return "不可达"


def render_dashboard(status):
    metadata = status.get("metadata") or {}
    runtime = status.get("runtime") or {}
    xray_config = status.get("xray_config") or {}
    network = status.get("network") or {}
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
            f"<td>{badge_html(bool(probe.get('ok')), probe_label(probe))}</td>"
            "</tr>"
        )
    runtime_meta = metadata.get("runtime") or {}
    runtime_name = runtime_meta.get("name") or ""
    restart_command = runtime_meta.get("restart_command") or ""
    log_command = runtime_meta.get("log_command") or ""
    log_blocks = []
    for item in logs:
        state = "存在" if item.get("exists") else "未找到"
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
        config_preview = xray_config.get("message") or "暂无配置预览"
    runtime_text = runtime_label(runtime)
    config_text = config_label(xray_config)
    bypass = network.get("bridge_bypass") or {}
    tun_text = "检测到本地代理/TUN" if network.get("tun_detected") else "未检测到 TUN 接管"
    bypass_text = "Bridge 已直连" if bypass.get("configured") else "Bridge 未设置直连"
    route_interface = (network.get("vps_route") or {}).get("interface") or "-"
    recommended_interface = network.get("recommended_interface") or "-"
    reverse_address = network.get("reverse_address") or "-"
    bypass_interfaces = ", ".join(bypass.get("interfaces") or []) or "-"
    html_text = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>fake-ui Bridge 本地控制台</title>
  <style>
    :root {{ --bg: #f4f8fb; --surface: #ffffff; --surface-soft: #f8fbfd; --ink: #101828; --muted: #667085; --line: #dde6ee; --primary: #2563eb; --primary-soft: #eaf1ff; --accent: #14b8a6; --accent-soft: #e7faf7; --success: #12805c; --warning: #b7791f; --danger: #c2413b; --radius: 8px; --shadow: 0 10px 30px rgba(16, 24, 40, 0.08); }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: var(--ink); background: var(--bg); }}
    .app-shell {{ min-height: 100vh; display: grid; grid-template-columns: 236px minmax(0, 1fr); }}
    .side-nav {{ position: sticky; top: 0; height: 100vh; display: grid; grid-template-rows: auto 1fr auto; gap: 16px; padding: 16px 14px; background: rgba(255,255,255,.96); border-right: 1px solid var(--line); }}
    .brand {{ padding: 8px 10px 14px; border-bottom: 1px solid var(--line); }}
    .brand strong {{ display: block; font-size: 20px; }}
    .brand span, .nav-link, .section-kicker, td span, .hint {{ color: var(--muted); font-size: 12px; }}
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
    .button-row {{ display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }}
    .btn {{ appearance: none; border: 1px solid var(--primary); background: var(--primary); color: white; border-radius: var(--radius); min-height: 36px; padding: 0 12px; font-weight: 800; cursor: pointer; }}
    .btn.secondary {{ background: var(--surface); color: var(--primary); }}
    input[type=file] {{ max-width: 100%; }}
	    .notice {{ margin-top: 10px; min-height: 22px; font-weight: 700; color: var(--muted); }}
	    .notice.warn {{ color: var(--warning); }}
	    .notice.ok {{ color: var(--success); }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ text-align: left; padding: 11px 8px; border-bottom: 1px solid var(--line); vertical-align: top; }}
    th {{ color: var(--muted); font-size: 12px; }}
    td strong, td span {{ display: block; }}
    code {{ background: var(--surface-soft); border: 1px solid var(--line); border-radius: 6px; padding: 2px 5px; }}
    pre {{ max-height: 260px; overflow: auto; background: #101828; color: #edf5ff; border-radius: var(--radius); padding: 12px; white-space: pre-wrap; font-size: 12px; }}
    summary {{ cursor: pointer; padding: 7px 0; font-weight: 700; }}
    .setup-grid, .guide-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }}
    .setup-item, .guide-item {{ border: 1px solid var(--line); border-radius: var(--radius); padding: 12px; background: var(--surface-soft); }}
    .mono-line {{ word-break: break-all; }}
    ol, ul {{ margin-bottom: 0; padding-left: 20px; }}
    @media (max-width: 860px) {{ .app-shell {{ grid-template-columns: 1fr; }} .side-nav {{ position: static; height: auto; grid-template-rows: auto; }} .nav-stack {{ display: flex; overflow-x: auto; }} .metric-grid, .setup-grid, .guide-grid {{ grid-template-columns: 1fr; }} .topbar {{ align-items: flex-start; flex-direction: column; }} }}
  </style>
</head>
<body>
  <div class="app-shell">
    <aside class="side-nav">
      <div class="brand"><strong>fake-ui</strong><span>Bridge 本地控制台</span></div>
      <nav class="nav-stack">
        <a class="nav-link active" href="#overview-section">概览</a>
        <a class="nav-link" href="#services-section">服务状态</a>
        <a class="nav-link" href="#import-section">导入配置</a>
        <a class="nav-link" href="#instructions-section">使用说明</a>
        <a class="nav-link" href="#debug-section">日志/调试</a>
        <a class="nav-link" href="#api-section">API</a>
      </nav>
      <div class="section-kicker">仅本机访问 · {esc(dashboard.get('host') or DEFAULT_HOST)}:{esc(dashboard.get('port') or DEFAULT_PORT)}</div>
    </aside>
    <div class="workspace">
      <header class="topbar">
        <div><h1>Bridge Agent</h1><span>{esc(metadata.get('bundle_kind', 'bridge'))} · {esc(metadata.get('platform', 'unknown'))} · {esc(metadata.get('bridge_id', ''))}</span></div>
        {badge_html(bool(runtime.get('ok')), runtime_text)}
      </header>
      <main>
        <section id="overview-section" class="overview-section">
          <div class="panel control-panel">
            <h2>本机控制</h2>
            <div class="button-row">
	              <button class="btn" type="button" onclick="restartBridge()">重启 Bridge</button>
	              <button class="btn secondary" type="button" onclick="applyNetworkBypass()">应用代理兼容</button>
	              <button class="btn secondary" type="button" onclick="location.reload()">刷新状态</button>
	            </div>
	            <div id="restart-result" class="notice">导入或更新配置后，点击重启 Bridge 让新配置生效。</div>
	            <div id="network-result" class="notice">Shadowrocket/Clash TUN 开启时，可先应用代理兼容再重启 Bridge。</div>
	          </div>
	          <div class="metric-grid">
	            <div class="metric"><span>运行状态</span><strong>{esc(runtime_text)}</strong></div>
	            <div class="metric"><span>Xray 配置</span><strong>{esc(config_text)}</strong></div>
	            <div class="metric"><span>本地服务</span><strong>{service_count}</strong></div>
	            <div class="metric"><span>代理兼容</span><strong>{esc(bypass_text)}</strong></div>
	          </div>
	        </section>
	        <section id="network-section" class="network-section panel">
	          <h2>本地代理兼容</h2>
	          <div class="setup-grid">
	            <div class="setup-item"><span class="section-kicker">检测结果</span><p>{badge_html(not network.get('tun_detected') or bypass.get('configured'), tun_text)}</p></div>
	            <div class="setup-item"><span class="section-kicker">VPS 地址</span><p class="mono-line"><code>{esc(reverse_address)}</code></p></div>
	            <div class="setup-item"><span class="section-kicker">当前路由网卡</span><p><code>{esc(route_interface)}</code></p></div>
	            <div class="setup-item"><span class="section-kicker">建议直连网卡</span><p><code>{esc(recommended_interface)}</code></p></div>
	            <div class="setup-item"><span class="section-kicker">Bridge 已配置网卡</span><p><code>{esc(bypass_interfaces)}</code></p></div>
	            <div class="setup-item"><span class="section-kicker">说明</span><p class="hint">这里仅调整 Bridge 到 VPS 的出站链路，不会修改 Shadowrocket 或系统代理。</p></div>
	          </div>
	        </section>
	        <section id="services-section" class="services-section panel">
          <h2>服务状态</h2>
          <table class="service-table">
            <thead><tr><th>服务</th><th>类型</th><th>本机地址</th><th>公网地址</th><th>探测</th></tr></thead>
            <tbody>{''.join(rows) or '<tr><td colspan="5">暂无服务配置</td></tr>'}</tbody>
          </table>
        </section>
        <section id="import-section" class="import-section panel">
          <h2>导入配置</h2>
          <p class="hint">选择 fake-ui 面板导出的 JSON，或配对 Agent 包里的配置文件。支持 <code>xray-bridge.json</code>、<code>bridge-dashboard.json</code>、<code>agent-profile.json</code>。</p>
          <div class="button-row">
            <label class="hint" for="import-file">选择 JSON 文件</label>
            <input id="import-file" type="file" accept=".json,application/json">
            <button class="btn" type="button" onclick="importConfig('xray-bridge.json')">导入 Xray 配置</button>
            <button class="btn secondary" type="button" onclick="importConfig('bridge-dashboard.json')">导入控制台配置</button>
            <button class="btn secondary" type="button" onclick="importConfig('agent-profile.json')">导入配对 Profile</button>
          </div>
          <div id="import-result" class="notice">导入后如 Xray 已在运行，请重启 bridge 让新配置生效。</div>
        </section>
        <section id="instructions-section" class="instructions-section panel">
          <h2>使用说明</h2>
          <div class="guide-grid">
            <div class="guide-item">
              <h3>推荐方式：配对 Agent</h3>
              <ol>
                <li>在 fake-ui 面板的“内网穿透”里生成配对 Agent 包。</li>
                <li>解压后运行安装脚本，客户端会自动拉取配置。</li>
                <li>打开本页确认“运行状态”和“本地服务”均正常。</li>
              </ol>
            </div>
            <div class="guide-item">
              <h3>手动方式：导入 JSON</h3>
              <ol>
                <li>从面板导出 <code>xray-bridge.json</code>。</li>
                <li>在本页“导入配置”选择文件并点击导入。</li>
                <li>运行 <code>bash stop-bridge.sh && bash start-bridge.sh</code>。</li>
              </ol>
            </div>
            <div class="guide-item">
              <h3>常用命令</h3>
              <p class="mono-line"><code>cd ~/.fake-ui/bridge-client-v3.0.1</code></p>
              <p class="mono-line"><code>bash open-dashboard.sh</code> 打开本页</p>
              <p class="mono-line"><code>bash start-bridge.sh</code> 启动 bridge</p>
              <p class="mono-line"><code>bash stop-bridge.sh</code> 停止 bridge</p>
            </div>
            <div class="guide-item">
              <h3>常见问题</h3>
              <ul>
	                <li>公网 502：先看本地服务是否可达。</li>
	                <li>开着 Shadowrocket/Clash 后测试异常：在“本地代理兼容”里应用直连网卡，再重启 Bridge。</li>
	                <li>配置无效：重新从面板导出或重新配对。</li>
                <li>服务不可达：确认本机应用监听了对应端口。</li>
                <li>本页打不开：确认只访问 <code>127.0.0.1:19090</code>。</li>
              </ul>
            </div>
          </div>
        </section>
        <section id="debug-section" class="debug-section panel">
          <h2>日志/调试</h2>
          <details><summary>运行时详情</summary><pre>{esc(runtime.get('message') or '暂无运行时输出')}</pre></details>
          <details><summary>安装信息</summary>
            <div class="setup-grid">
              <div class="setup-item"><span class="section-kicker">服务</span><p><code>{esc(runtime_name)}</code></p></div>
              <div class="setup-item"><span class="section-kicker">重启命令</span><p class="mono-line"><code>{esc(restart_command or '暂无')}</code></p></div>
              <div class="setup-item"><span class="section-kicker">日志命令</span><p class="mono-line"><code>{esc(log_command or '暂无')}</code></p></div>
              <div class="setup-item"><span class="section-kicker">配置文件</span><p><code>{esc(xray_config.get('path') or '')}</code> {badge_html(bool(xray_config.get('ok')), config_text)}</p></div>
            </div>
          </details>
          <details><summary>配置预览</summary><pre>{esc(config_preview)}</pre></details>
          <p class="section-kicker">{log_count} 个日志文件可读</p>
          {''.join(log_blocks) or '<p>暂无日志配置</p>'}
        </section>
        <section id="api-section" class="api-section panel">
          <h2>API</h2>
          <p><code>GET /status.json</code></p>
          <p><code>POST /api/import</code></p>
	          <p><code>POST /api/restart</code></p>
	          <p><code>POST /api/network/fix</code></p>
	        </section>
      </main>
    </div>
  </div>
  <script>
    async function importConfig(filename) {{
      const input = document.getElementById('import-file');
      const result = document.getElementById('import-result');
      if (!input.files || !input.files.length) {{ result.textContent = '请先选择 JSON 文件。'; return; }}
      try {{
        const text = await input.files[0].text();
        const content = JSON.parse(text);
        const response = await fetch('/api/import', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ filename, source_filename: input.files[0].name, content }})
        }});
        const payload = await response.json();
        if (!response.ok || !payload.ok) throw new Error(payload.error || '导入失败');
        result.textContent = `已导入 ${{payload.filename}}，请按需重启 bridge。`;
      }} catch (error) {{
        result.textContent = `导入失败：${{error.message}}`;
      }}
    }}
	    async function restartBridge() {{
      const result = document.getElementById('restart-result');
      result.textContent = '正在重启 Bridge...';
      try {{
        const response = await fetch('/api/restart', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{}})
        }});
        const payload = await response.json();
        if (!response.ok || !payload.ok) throw new Error(payload.error || '重启失败');
        result.textContent = payload.message || '重启命令已执行，正在刷新状态...';
        window.setTimeout(() => location.reload(), 1200);
      }} catch (error) {{
	        result.textContent = `重启失败：${{error.message}}`;
	      }}
	    }}
	    async function applyNetworkBypass() {{
	      const result = document.getElementById('network-result');
	      result.textContent = '正在应用代理兼容...';
	      try {{
	        const response = await fetch('/api/network/fix', {{
	          method: 'POST',
	          headers: {{ 'Content-Type': 'application/json' }},
	          body: JSON.stringify({{}})
	        }});
	        const payload = await response.json();
	        if (!response.ok || !payload.ok) throw new Error(payload.error || '应用失败');
	        result.textContent = payload.message || '已应用代理兼容，请重启 Bridge。';
	        window.setTimeout(() => location.reload(), 1200);
	      }} catch (error) {{
	        result.textContent = `应用失败：${{error.message}}`;
	      }}
	    }}
	  </script>
</body>
</html>"""
    return html_text.encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    base_dir = Path(__file__).resolve().parent
    metadata = {}
    dashboard_port = DEFAULT_PORT

    def log_message(self, fmt, *args):
        return

    def send_bytes(self, code, content_type, payload):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def send_json(self, code, payload):
        self.send_bytes(code, "application/json; charset=utf-8", json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))

    def do_GET(self):
        if not allowed_host_header(self.headers.get("Host", ""), self.dashboard_port):
            self.send_bytes(403, "text/plain; charset=utf-8", b"forbidden")
            return
        path = urlparse(self.path).path
        status = collect_status(type(self).metadata, self.base_dir)
        if path == "/status.json":
            self.send_bytes(200, "application/json; charset=utf-8", json.dumps(status, ensure_ascii=False, indent=2).encode("utf-8"))
            return
        if path == "/":
            status["config_preview"] = xray_config_preview(self.base_dir, self.metadata)
            self.send_bytes(200, "text/html; charset=utf-8", render_dashboard(status))
            return
        self.send_bytes(404, "text/plain; charset=utf-8", b"not found")

    def do_POST(self):
        if not allowed_host_header(self.headers.get("Host", ""), self.dashboard_port):
            self.send_bytes(403, "text/plain; charset=utf-8", b"forbidden")
            return
        path = urlparse(self.path).path
        if path == "/api/restart":
            try:
                result = restart_runtime(type(self).metadata, self.base_dir)
                self.send_json(200, result)
            except Exception as exc:
                self.send_json(400, {"ok": False, "error": str(exc)})
            return
        if path == "/api/network/fix":
            try:
                length = int(self.headers.get("Content-Length") or "0")
                payload = {}
                if length > 0:
                    if length > 1024 * 1024:
                        raise RuntimeError("请求体过大")
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                result = apply_network_bypass(type(self).metadata, self.base_dir, (payload or {}).get("interface", ""))
                self.send_json(200, result)
            except Exception as exc:
                self.send_json(400, {"ok": False, "error": str(exc)})
            return
        if path != "/api/import":
            self.send_bytes(404, "text/plain; charset=utf-8", b"not found")
            return
        try:
            length = int(self.headers.get("Content-Length") or "0")
            if length <= 0 or length > 2 * 1024 * 1024:
                raise RuntimeError("请求体为空或过大")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            filename = import_json_file(self.base_dir, payload.get("filename"), payload.get("content"))
            metadata_updated = False
            if filename == "xray-bridge.json":
                services = infer_dashboard_services_from_xray_config(
                    payload.get("content") or {},
                    payload.get("source_filename") or payload.get("original_filename") or "",
                )
                if services:
                    type(self).metadata = merge_metadata_services(type(self).metadata, services)
                    write_json_atomic(self.base_dir / "bridge-dashboard.json", type(self).metadata)
                    metadata_updated = True
            if filename == "bridge-dashboard.json":
                type(self).metadata = load_metadata(self.base_dir)
            result = {"ok": True, "filename": filename}
            if metadata_updated:
                result["metadata_updated"] = True
            self.send_json(200, result)
        except Exception as exc:
            self.send_json(400, {"ok": False, "error": str(exc)})


def main():
    parser = argparse.ArgumentParser(description="fake-ui bridge local dashboard")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    if args.host != DEFAULT_HOST:
        raise SystemExit("dashboard is local-only; host must be 127.0.0.1")
    Handler.metadata = load_metadata(Handler.base_dir)
    Handler.dashboard_port = args.port
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
import os
import platform
import re
import subprocess
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


def command_output(command, timeout=2.0):
    try:
        proc = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
    except Exception:
        return ""
    return proc.stdout or ""


def is_tunnel_interface(name):
    value = str(name or "").strip().lower()
    return value.startswith(("utun", "tun", "tap", "wg", "ppp")) or any(
        token in value for token in ("wintun", "clash", "shadowrocket", "tailscale", "zerotier")
    )


def parse_route_interface(text):
    for pattern in (r"\binterface:\s*([^\s]+)", r"\bdev\s+([^\s]+)"):
        match = re.search(pattern, text or "")
        if match:
            return match.group(1)
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    if len(lines) == 1 and len(lines[0]) <= 80:
        return lines[0]
    return ""


def current_platform():
    system = platform.system().lower()
    if system == "darwin":
        return "macos"
    if system == "linux":
        return "linux"
    if system.startswith("win"):
        return "windows"
    return system


def detect_outbound_interface():
    override = str(os.getenv("FAKE_UI_BRIDGE_OUTBOUND_INTERFACE") or "").strip()
    if override:
        return override
    current = current_platform()
    if current == "macos":
        routed = parse_route_interface(command_output(["route", "-n", "get", "1.1.1.1"]))
        if routed and not is_tunnel_interface(routed):
            return routed
        text = command_output(["ifconfig"])
        candidates = []
        for block in re.split(r"\n(?=[a-zA-Z0-9_.-]+:\s)", text):
            name = block.split(":", 1)[0].strip()
            if not name or is_tunnel_interface(name) or name.startswith(("lo", "awdl", "llw", "bridge", "gif", "stf", "anpi")):
                continue
            if "status: active" in block and re.search(r"\binet\s+\d+\.\d+\.\d+\.\d+", block):
                candidates.append(name)
        return (sorted(candidates, key=lambda item: (0 if item == "en0" else 1, item)) or [""])[0]
    if current == "linux":
        routed = parse_route_interface(command_output(["ip", "route", "get", "1.1.1.1"]))
        if routed and not is_tunnel_interface(routed):
            return routed
        text = command_output(["ip", "-o", "-4", "addr", "show", "scope", "global"])
        for line in text.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                name = parts[1].rstrip(":")
                if not is_tunnel_interface(name) and not name.startswith(("lo", "docker", "br-", "veth")):
                    return name
    return ""


def reverse_outbounds(config):
    return [
        item
        for item in (config or {}).get("outbounds") or []
        if item.get("protocol") == "vless" and str(item.get("tag") or "").startswith("tunnel-reverse")
    ]


def apply_local_network_bypass(config):
    interface = detect_outbound_interface()
    if not interface or not isinstance(config, dict):
        return config
    for outbound in reverse_outbounds(config):
        outbound.setdefault("streamSettings", {}).setdefault("sockopt", {})["interface"] = interface
    return config


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
    write_json(BASE_DIR / "xray-bridge.json", apply_local_network_bypass(result.get("xray_config") or {}))
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
    record_platform = str(record.get("platform") or "").strip().lower()
    profile_platform = "auto" if record_platform in {"auto", "universal"} else (record_platform or safe_id(platform).lower())
    return {
        "schema": 1,
        "panel_url": str(panel_url or ""),
        "token_id": record.get("token_id", ""),
        "pairing_token": (pairing or {}).get("pairing_token", ""),
        "bridge_id": record.get("bridge_id") or safe_id(bridge_id),
        "bundle_kind": record.get("bundle_kind") or bundle_kind,
        "platform": profile_platform,
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


def add_pairing_assets(tar, root, pairing, panel_url, bundle_kind, bridge_id, platform, agent_name, profile_platform=None):
    profile = agent_profile(pairing, panel_url, bundle_kind, bridge_id, profile_platform or platform, agent_name)
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


def universal_agent_readme_text(identifier, bundle_kind, tunnels):
    rows = "\n".join(
        f"- {item.get('id')}: {item.get('target_host')}:{item.get('target_port')} via :{item.get('portal_port')}"
        for item in tunnels
    )
    return f"""# fake-ui Bridge Agent

Bridge: {identifier}
Mode: {bundle_kind}

Services:

{rows}

这个安装包同时包含 macOS、Linux、Windows 三端脚本。客户只需要下载这一份，然后按自己的系统执行对应命令。

macOS:

```bash
bash install-macos.sh
```

Linux:

```bash
sudo bash install-linux.sh
```

Windows:

```PowerShell
powershell -ExecutionPolicy Bypass -File .\\install-windows.ps1
```

安装完成后打开本地控制台：

```bash
bash open-dashboard.sh
```

Windows 可运行：

```PowerShell
powershell -ExecutionPolicy Bypass -File .\\open-dashboard.ps1
```

控制台地址：http://127.0.0.1:19090/
"""


def universal_root(identifier):
    return f"{safe_id(identifier)}-agent-bridge"


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


def build_universal_paired_agent_bundle(bridge_id, tunnels, pairing, panel_url):
    bid = safe_id(bridge_id)
    root = universal_root(bid)
    content = io.BytesIO()
    with tarfile.open(fileobj=content, mode="w:gz") as tar:
        add_text(tar, f"{root}/README.md", universal_agent_readme_text(bid, "shared", tunnels))
        add_dashboard_assets(tar, root, "shared", bid, "auto", tunnels)
        add_pairing_assets(tar, root, pairing, panel_url, "shared", bid, "macos", bid, profile_platform="auto")
        add_text(tar, f"{root}/{agent_service_id(bid)}.plist", agent_plist_text(bid))
        add_text(tar, f"{root}/install-macos.sh", agent_install_macos(bid), mode=0o755)
        add_text(tar, f"{root}/uninstall-macos.sh", agent_uninstall_macos(bid), mode=0o755)
        add_text(tar, f"{root}/status-macos.sh", agent_status_script(tunnels, "macos"), mode=0o755)
        service = f"fake-ui-bridge-{bid}.service"
        add_text(tar, f"{root}/{service}", linux_service_text(bid))
        add_text(tar, f"{root}/install-linux.sh", agent_install_linux(bid), mode=0o755)
        add_text(tar, f"{root}/uninstall-linux.sh", agent_uninstall_linux(bid), mode=0o755)
        add_text(tar, f"{root}/status-linux.sh", agent_status_script(tunnels, "linux"), mode=0o755)
        add_text(tar, f"{root}/install-windows.ps1", agent_install_windows(bid))
        add_text(tar, f"{root}/uninstall-windows.ps1", agent_uninstall_windows(bid))
        add_text(tar, f"{root}/status-windows.ps1", agent_status_script(tunnels, "windows"))
        add_text(tar, f"{root}/open-dashboard.ps1", open_dashboard_ps1())
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


def build_universal_paired_bundle(tunnel, pairing, panel_url):
    node_id = safe_id(tunnel.get("id"))
    root = universal_root(node_id)
    content = io.BytesIO()
    with tarfile.open(fileobj=content, mode="w:gz") as tar:
        add_text(tar, f"{root}/README.md", universal_agent_readme_text(node_id, "dedicated", [tunnel]))
        add_dashboard_assets(tar, root, "dedicated", tunnel.get("id"), "auto", [tunnel])
        add_pairing_assets(
            tar,
            root,
            pairing,
            panel_url,
            "dedicated",
            tunnel.get("id"),
            "macos",
            tunnel.get("name") or tunnel.get("id"),
            profile_platform="auto",
        )
        add_text(tar, f"{root}/{service_id(tunnel)}.plist", plist_text(tunnel))
        add_text(tar, f"{root}/install-macos.sh", install_script(tunnel), mode=0o755)
        add_text(tar, f"{root}/uninstall-macos.sh", uninstall_script(tunnel), mode=0o755)
        add_text(tar, f"{root}/status-macos.sh", status_script(tunnel), mode=0o755)
        service = dedicated_linux_service_id(tunnel)
        add_text(tar, f"{root}/{service}", dedicated_linux_service_text(tunnel))
        add_text(tar, f"{root}/install-linux.sh", dedicated_install_linux(tunnel), mode=0o755)
        add_text(tar, f"{root}/uninstall-linux.sh", dedicated_uninstall_linux(tunnel), mode=0o755)
        add_text(tar, f"{root}/status-linux.sh", agent_status_script([tunnel], "linux"), mode=0o755)
        add_text(tar, f"{root}/install-windows.ps1", dedicated_install_windows(tunnel))
        add_text(tar, f"{root}/uninstall-windows.ps1", dedicated_uninstall_windows(tunnel))
        add_text(tar, f"{root}/status-windows.ps1", agent_status_script([tunnel], "windows"))
        add_text(tar, f"{root}/open-dashboard.ps1", open_dashboard_ps1())
    return content.getvalue()
