import io
import json
import re
import tarfile


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


def install_script(tunnel):
    node_id = tunnel.get("id")
    sid = service_id(tunnel)
    return f"""#!/usr/bin/env bash
set -euo pipefail

ROOT="$HOME/.fake-ui"
TUNNEL_DIR="$ROOT/tunnels/{node_id}"
PLIST="$HOME/Library/LaunchAgents/{sid}.plist"

mkdir -p "$ROOT/bin" "$TUNNEL_DIR" "$HOME/Library/LaunchAgents"
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


def readme_text(tunnel):
    if tunnel.get("kind") == "private_tcp":
        return f"""# fake-ui Mac Bridge

Tunnel: {tunnel.get('name') or tunnel.get('id')}
Type: private TCP
Local service: {tunnel.get('target_host')}:{tunnel.get('target_port')}
VPS portal: 127.0.0.1:{tunnel.get('portal_port')}

Install:

```bash
bash install-macos.sh
```

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

```bash
bash status-macos.sh
```

Uninstall:

```bash
bash uninstall-macos.sh
```
"""
    return f"""# fake-ui Mac Bridge

Tunnel: {tunnel.get('name') or tunnel.get('id')}
Public URL: https://{tunnel.get('public_domain') or tunnel.get('server_address')}/
Local service: http://{tunnel.get('target_host')}:{tunnel.get('target_port')}/

Install:

```bash
bash install-macos.sh
```

Status:

```bash
bash status-macos.sh
```

Uninstall:

```bash
bash uninstall-macos.sh
```
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
        add_text(tar, f"{root}/README.md", readme_text(tunnel))
    return content.getvalue()


def dedicated_linux_service_id(tunnel):
    return f"fake-ui-tunnel-{safe_id(tunnel.get('id'))}.service"


def dedicated_windows_task_name(tunnel):
    return f"FakeUITunnel-{safe_id(tunnel.get('id'))}"


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
    return f"""#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "请使用 root 执行: sudo bash install-linux.sh" >&2
  exit 1
fi

ROOT="{root}"
SERVICE="/etc/systemd/system/{service}"
mkdir -p "$ROOT"
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
    return f"""$ErrorActionPreference = "Stop"
$Root = Join-Path $env:ProgramData "fake-ui-tunnel\\{bid}"
New-Item -ItemType Directory -Force -Path $Root | Out-Null
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
        add_text(tar, f"{root}/README.md", readme_text(tunnel))
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
    return f"""#!/usr/bin/env bash
set -euo pipefail

ROOT="$HOME/.fake-ui"
BRIDGE_DIR="$ROOT/bridges/{bid}"
PLIST="$HOME/Library/LaunchAgents/{sid}.plist"

mkdir -p "$ROOT/bin" "$BRIDGE_DIR" "$HOME/Library/LaunchAgents"
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
    return f"""#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "请使用 root 执行: sudo bash install-linux.sh" >&2
  exit 1
fi

ROOT="/opt/fake-ui-bridge/{bid}"
SERVICE="/etc/systemd/system/{service}"
mkdir -p "$ROOT"
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
    return f"""$ErrorActionPreference = "Stop"
$Root = Join-Path $env:ProgramData "fake-ui-bridge\\{bid}"
New-Item -ItemType Directory -Force -Path $Root | Out-Null
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
    rows = "\n".join(
        f"- {item.get('id')}: {item.get('target_host')}:{item.get('target_port')} via :{item.get('portal_port')}"
        for item in tunnels
    )
    return f"""# fake-ui Shared Bridge Agent

Bridge: {bridge_id}
Platform: {platform}

Services:

{rows}

Install with the platform-specific install script in this bundle.
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
