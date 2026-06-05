param(
  [string]$HostAlias = "fake-ui-sg",
  [string]$RemoteDir = "/opt/fake-airport",
  [switch]$SkipTests,
  [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$RemoteDir = $RemoteDir.TrimEnd("/")
if (-not $RemoteDir.StartsWith("/")) {
  throw "RemoteDir must be an absolute Linux path"
}

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

function Write-Utf8NoBomLfFile {
  param(
    [Parameter(Mandatory = $true)][string]$Path,
    [Parameter(Mandatory = $true)][string]$Content
  )
  $normalized = $Content -replace "`r`n", "`n"
  $encoding = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::WriteAllText($Path, $normalized, $encoding)
}

function Invoke-Checked {
  param(
    [Parameter(Mandatory = $true)][scriptblock]$Command,
    [Parameter(Mandatory = $true)][string]$Label
  )
  Write-Host "[$Label]"
  & $Command
  if ($LASTEXITCODE -ne 0) {
    throw "$Label failed with exit code $LASTEXITCODE"
  }
}

$Commit = (git rev-parse --short HEAD).Trim()
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$TempDir = Join-Path ([System.IO.Path]::GetTempPath()) "fake-ui-deploy-$Commit-$Stamp"
New-Item -ItemType Directory -Path $TempDir -Force | Out-Null
$Archive = Join-Path $TempDir "fake-airport-$Commit.tar"
$RemoteArchive = "/tmp/fake-airport-$Commit.tar"
$RemoteScript = "/tmp/deploy-fake-airport-$Commit.sh"
$LocalScript = Join-Path $TempDir "deploy-fake-airport-$Commit.sh"

try {
  if (-not $SkipTests) {
    Invoke-Checked { powershell -NoProfile -ExecutionPolicy Bypass -File scripts\test-local.ps1 } "local tests"
  }

  Invoke-Checked { git archive --format=tar -o $Archive HEAD } "create archive"
  Invoke-Checked { scp $Archive "${HostAlias}:$RemoteArchive" } "upload archive"

  $DeployScript = @"
set -euo pipefail

REMOTE_DIR='$RemoteDir'
COMMIT='$Commit'
REMOTE_ARCHIVE='$RemoteArchive'
WORK_DIR="/tmp/fake-airport-`$COMMIT"
BACKUP_DIR="/root/fake-airport-backups"

mkdir -p "`$BACKUP_DIR"
ts=`$(date +%Y%m%d-%H%M%S)
tar --exclude='./data/backups' -czf "`$BACKUP_DIR/fake-airport-before-`$COMMIT-`$ts.tgz" -C "`$REMOTE_DIR" .

rm -rf "`$WORK_DIR"
mkdir -p "`$WORK_DIR"
tar -tf "`$REMOTE_ARCHIVE" >/dev/null
tar -xf "`$REMOTE_ARCHIVE" -C "`$WORK_DIR"

python3 - <<'PY'
import shutil
from pathlib import Path

src = Path('/tmp/fake-airport-$Commit').resolve()
dst = Path('$RemoteDir').resolve()
skip = {'data', '.env', 'generated'}

if not src.is_dir():
    raise SystemExit(f'missing source: {src}')
if str(dst) != '$RemoteDir' or not dst.is_dir():
    raise SystemExit(f'bad target: {dst}')

for item in dst.iterdir():
    if item.name in skip:
        continue
    if item.is_dir() and not item.is_symlink():
        shutil.rmtree(item)
    else:
        item.unlink()

for item in src.iterdir():
    if item.name in skip:
        continue
    target = dst / item.name
    if item.is_dir() and not item.is_symlink():
        shutil.copytree(item, target, symlinks=True)
    else:
        shutil.copy2(item, target, follow_symlinks=False)
PY

rm -rf "`$WORK_DIR" "`$REMOTE_ARCHIVE"
printf 'deployed_source=local-head\ncommit=%s\ndeployed_at=%s\n' "`$COMMIT" "`$(date -Iseconds)" > "`$REMOTE_DIR/.deployed-version"

cd "`$REMOTE_DIR"
touch .env
python3 - <<'PY'
from pathlib import Path

path = Path(".env")
wanted = {
    "FAKE_UI_VERSION": "2.0.1",
    "FAKE_UI_STORE": "sqlite",
    "FAKE_UI_DB": "/data/panel/fake-ui.db",
}
lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
seen = set()
out = []
for line in lines:
    key = line.split("=", 1)[0].strip() if "=" in line else ""
    if key in wanted:
        out.append(f"{key}={wanted[key]}")
        seen.add(key)
    else:
        out.append(line)
for key, value in wanted.items():
    if key not in seen:
        out.append(f"{key}={value}")
path.write_text("\n".join(out).strip() + "\n", encoding="utf-8")
PY
python3 scripts/migrate-json-to-sqlite.py --data-dir data/panel --db data/panel/fake-ui.db
python3 -m pytest -q
"@

  if (-not $SkipBuild) {
    $DeployScript += @"

docker compose up -d --build panel
for i in `$(seq 1 30); do
  state=`$(docker inspect -f '{{.State.Health.Status}}' xray-proxy-panel 2>/dev/null || true)
  echo "panel-health=`$state"
  [ "`$state" = healthy ] && break
  sleep 2
done
test "`$(docker inspect -f '{{.State.Health.Status}}' xray-proxy-panel)" = healthy
"@
  }

  $DeployScript += @"

cat "`$REMOTE_DIR/.deployed-version"
docker compose ps
"@

  Write-Utf8NoBomLfFile -Path $LocalScript -Content $DeployScript
  Invoke-Checked { scp $LocalScript "${HostAlias}:$RemoteScript" } "upload deploy script"
  Invoke-Checked { ssh $HostAlias "bash $RemoteScript; status=`$?; rm -f $RemoteScript; exit `$status" } "remote deploy"
}
finally {
  Remove-Item -LiteralPath $TempDir -Recurse -Force -ErrorAction SilentlyContinue
}
