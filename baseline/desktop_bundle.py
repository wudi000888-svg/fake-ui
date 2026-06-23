import io
import zipfile

import desktop_config_builder


def shell_script(action):
    if action == "start":
        return """#!/usr/bin/env bash
set -euo pipefail
hysteria -c hysteria-desktop.yaml client &
echo $! > .hysteria-desktop.pid
echo "Hysteria2 UDP forwarding started. Import wireguard.conf in WireGuard next."
"""
    if action == "stop":
        return """#!/usr/bin/env bash
set -euo pipefail
if [ -f .hysteria-desktop.pid ]; then
  kill "$(cat .hysteria-desktop.pid)" >/dev/null 2>&1 || true
  rm -f .hysteria-desktop.pid
fi
echo "Hysteria2 UDP forwarding stopped."
"""
    return """#!/usr/bin/env bash
set -euo pipefail
echo "Install Hysteria2 and WireGuard, then run ./start.sh and import wireguard.conf."
"""


def powershell_script(action):
    if action == "start":
        return """$ErrorActionPreference = "Stop"
Start-Process hysteria.exe -ArgumentList "-c hysteria-desktop.yaml client" -WindowStyle Hidden
Write-Host "Hysteria2 UDP forwarding started. Import wireguard.conf in WireGuard next."
"""
    if action == "stop":
        return """Get-Process hysteria -ErrorAction SilentlyContinue | Stop-Process -Force
Write-Host "Hysteria2 UDP forwarding stopped."
"""
    return """Write-Host "Install Hysteria2 and WireGuard, then run .\\start-windows.ps1 and import wireguard.conf."
"""


def build_bundle(device):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("hysteria-desktop.yaml", desktop_config_builder.hysteria_client_config(device))
        archive.writestr("wireguard.conf", desktop_config_builder.wireguard_config(device))
        archive.writestr("vps-wireguard-example.conf", desktop_config_builder.server_wireguard_config())
        archive.writestr("README.md", desktop_config_builder.usage_notes(device))
        archive.writestr("macos/install.sh", shell_script("install"))
        archive.writestr("macos/start.sh", shell_script("start"))
        archive.writestr("macos/stop.sh", shell_script("stop"))
        archive.writestr("linux/install.sh", shell_script("install"))
        archive.writestr("linux/start.sh", shell_script("start"))
        archive.writestr("linux/stop.sh", shell_script("stop"))
        archive.writestr("windows/install-windows.ps1", powershell_script("install"))
        archive.writestr("windows/start-windows.ps1", powershell_script("start"))
        archive.writestr("windows/stop-windows.ps1", powershell_script("stop"))
    return buffer.getvalue()
