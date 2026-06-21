#!/usr/bin/env python3
import argparse
import io
import json
import tarfile
import zipfile
from pathlib import Path


def root_dir():
    return Path(__file__).resolve().parents[1]


def load_bridge_bundle_module():
    import sys

    baseline = root_dir() / "baseline"
    if str(baseline) not in sys.path:
        sys.path.insert(0, str(baseline))
    import tunnel_bridge_bundle

    return tunnel_bridge_bundle


def example_bridge_config():
    return {
        "log": {"loglevel": "warning"},
        "inbounds": [],
        "outbounds": [
            {
                "tag": "tunnel-reverse-out",
                "protocol": "vless",
                "settings": {
                    "vnext": [
                        {
                            "address": "your-vps-domain.example.com",
                            "port": 443,
                            "users": [
                                {
                                    "id": "00000000-0000-4000-8000-000000000000",
                                    "encryption": "none",
                                    "flow": "xtls-rprx-vision",
                                }
                            ],
                        }
                    ],
                    "reverse": {"tag": "tunnel-reverse-in"},
                },
                "streamSettings": {
                    "network": "tcp",
                    "security": "reality",
                    "realitySettings": {
                        "serverName": "www.cloudflare.com",
                        "publicKey": "replace-with-panel-public-key",
                        "shortId": "replace",
                        "fingerprint": "chrome",
                    },
                },
            },
            {
                "tag": "tunnel-local-service",
                "protocol": "freedom",
                "settings": {"redirect": "127.0.0.1:3000"},
            },
        ],
        "routing": {
            "rules": [
                {
                    "type": "field",
                    "inboundTag": ["tunnel-reverse-in"],
                    "outboundTag": "tunnel-local-service",
                }
            ]
        },
    }


def client_metadata(module, platform):
    return {
        "bundle_kind": "client-template",
        "bridge_id": "client-template",
        "platform": platform,
        "dashboard": {"host": module.DASHBOARD_HOST, "port": module.DASHBOARD_PORT},
        "runtime": {
            "kind": "manual",
            "name": "fake-ui bridge client",
            "restart_command": "stop then start bridge with the platform script",
            "log_command": "open bridge-client.out.log and bridge-client.err.log",
        },
        "logs": ["bridge-client.out.log", "bridge-client.err.log", "bridge-dashboard.out.log", "bridge-dashboard.err.log"],
        "xray_config": {"path": "xray-bridge.json"},
        "services": [
            {
                "id": "imported-service",
                "name": "Imported service",
                "kind": "public_https",
                "public_domain": "",
                "public_url": "",
                "local": "127.0.0.1:3000",
                "local_url": "http://127.0.0.1:3000/",
                "target_host": "127.0.0.1",
                "target_port": 3000,
                "portal_port": 0,
            }
        ],
    }


def readme(platform, version):
    if platform == "windows":
        install = "PowerShell"
        open_cmd = "powershell -ExecutionPolicy Bypass -File .\\open-dashboard.ps1"
        start_cmd = "powershell -ExecutionPolicy Bypass -File .\\start-bridge.ps1"
        stop_cmd = "powershell -ExecutionPolicy Bypass -File .\\stop-bridge.ps1"
    else:
        install = "bash"
        open_cmd = "bash open-dashboard.sh"
        start_cmd = "bash start-bridge.sh"
        stop_cmd = "bash stop-bridge.sh"
    return f"""# fake-ui Bridge Client v{version}

这是独立发布的本机 bridge client。它和 VPS 上的 fake-ui 面板分开发布，包内不包含任何客户域名、UUID、私钥或真实 Xray 配置。

使用流程：

1. 从 fake-ui 面板导入或下载你的 `xray-bridge.json`。
2. 把配置文件放到本目录，覆盖示例文件名为 `xray-bridge.json`。
3. 确保本机已安装 Xray，或把 `xray` / `xray.exe` 放到本目录。
4. 启动 bridge。
5. 打开本地控制台 `http://127.0.0.1:19090/`。

启动：

```{install}
{start_cmd}
```

停止：

```{install}
{stop_cmd}
```

打开本地控制台：

```{install}
{open_cmd}
```

示例配置 `xray-bridge.example.json` 只能用于展示字段结构，不能直接连接服务器。真实配置必须从 fake-ui 面板导入。
"""


def shell_start_script():
    return """#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
XRAY="${XRAY:-./xray}"
if [ ! -x "$XRAY" ]; then
  if command -v xray >/dev/null 2>&1; then
    XRAY="$(command -v xray)"
  else
    echo "未找到 xray。请安装 Xray，或把 xray 二进制放到当前目录。" >&2
    exit 1
  fi
fi
if [ ! -f xray-bridge.json ]; then
  echo "未找到 xray-bridge.json。请先从 fake-ui 面板导入配置。" >&2
  exit 1
fi
"$XRAY" run -test -c xray-bridge.json
nohup "$XRAY" run -c xray-bridge.json > bridge-client.out.log 2> bridge-client.err.log &
echo $! > bridge-client.pid
echo "fake-ui bridge client started: $(cat bridge-client.pid)"
"""


def shell_stop_script():
    return """#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ -f bridge-client.pid ]; then
  kill "$(cat bridge-client.pid)" >/dev/null 2>&1 || true
  rm -f bridge-client.pid
fi
echo "fake-ui bridge client stopped"
"""


def powershell_start_script():
    return """$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$Xray = Join-Path $PSScriptRoot "xray.exe"
if (-not (Test-Path $Xray)) {
  $Found = Get-Command xray.exe -ErrorAction SilentlyContinue
  if ($Found) {
    $Xray = $Found.Source
  } else {
    throw "未找到 xray.exe。请安装 Xray，或把 xray.exe 放到当前目录。"
  }
}
if (-not (Test-Path (Join-Path $PSScriptRoot "xray-bridge.json"))) {
  throw "未找到 xray-bridge.json。请先从 fake-ui 面板导入配置。"
}
& $Xray run -test -c (Join-Path $PSScriptRoot "xray-bridge.json")
$Process = Start-Process -FilePath $Xray -ArgumentList @("run", "-c", (Join-Path $PSScriptRoot "xray-bridge.json")) -RedirectStandardOutput (Join-Path $PSScriptRoot "bridge-client.out.log") -RedirectStandardError (Join-Path $PSScriptRoot "bridge-client.err.log") -PassThru
Set-Content -Path (Join-Path $PSScriptRoot "bridge-client.pid") -Value $Process.Id
Write-Host "fake-ui bridge client started: $($Process.Id)"
"""


def powershell_stop_script():
    return """$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$PidFile = Join-Path $PSScriptRoot "bridge-client.pid"
if (Test-Path $PidFile) {
  $BridgePid = Get-Content $PidFile | Select-Object -First 1
  Stop-Process -Id $BridgePid -Force -ErrorAction SilentlyContinue
  Remove-Item $PidFile -Force
}
Write-Host "fake-ui bridge client stopped"
"""


def files_for_platform(platform, version):
    module = load_bridge_bundle_module()
    files = {
        "README.md": readme(platform, version),
        "bridge-dashboard.py": module.dashboard_script(),
        "bridge-dashboard.json": json.dumps(client_metadata(module, platform), indent=2, ensure_ascii=False),
        "xray-bridge.example.json": json.dumps(example_bridge_config(), indent=2, ensure_ascii=False),
    }
    if platform == "windows":
        files.update(
            {
                "open-dashboard.ps1": module.open_dashboard_ps1(),
                "start-bridge.ps1": powershell_start_script(),
                "stop-bridge.ps1": powershell_stop_script(),
            }
        )
    else:
        files.update(
            {
                "open-dashboard.sh": module.open_dashboard_sh(),
                "start-bridge.sh": shell_start_script(),
                "stop-bridge.sh": shell_stop_script(),
            }
        )
    return files


def write_zip(output, files):
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, text in files.items():
            archive.writestr(f"fake-ui-bridge-client/{name}", text)


def write_tar_gz(output, files):
    with tarfile.open(output, "w:gz", format=tarfile.PAX_FORMAT) as archive:
        for name, text in files.items():
            raw = text.encode("utf-8")
            info = tarfile.TarInfo(f"fake-ui-bridge-client/{name}")
            info.size = len(raw)
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            if name.endswith(".sh") or name == "bridge-dashboard.py":
                info.mode = 0o755
            else:
                info.mode = 0o644
            archive.addfile(info, io.BytesIO(raw))


def package(output_dir, version):
    output_dir = Path(output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = []
    for platform in ("macos", "linux", "windows"):
        files = files_for_platform(platform, version)
        if platform == "linux":
            output = output_dir / f"fake-ui-bridge-client-v{version}-{platform}.tar.gz"
            write_tar_gz(output, files)
        else:
            output = output_dir / f"fake-ui-bridge-client-v{version}-{platform}.zip"
            write_zip(output, files)
        outputs.append(output)
    return outputs


def main():
    parser = argparse.ArgumentParser(description="Package the standalone fake-ui bridge client.")
    parser.add_argument("output_dir", help="Directory for release assets")
    parser.add_argument("--version", default="0.1.0")
    args = parser.parse_args()
    for output in package(args.output_dir, args.version):
        print(output)


if __name__ == "__main__":
    main()
