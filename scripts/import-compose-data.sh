#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 /path/to/xray-proxy-panel-compose-state.tgz [project-dir]" >&2
  exit 2
fi

BUNDLE="$1"
ROOT_DIR="${2:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

if [[ ! -f "$BUNDLE" ]]; then
  echo "Bundle not found: $BUNDLE" >&2
  exit 1
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

mkdir -p "$ROOT_DIR/data"
tar -xzf "$BUNDLE" -C "$TMP"

if [[ ! -d "$TMP/data" ]]; then
  echo "Invalid bundle: missing data/ directory" >&2
  exit 1
fi

(cd "$TMP/data" && tar -cf - .) | (cd "$ROOT_DIR/data" && tar -xf -)

chmod 600 "$ROOT_DIR"/data/panel/*login*.txt 2>/dev/null || true
chmod 600 "$ROOT_DIR"/data/panel/hy2_traffic_secret.txt 2>/dev/null || true
chmod 600 "$ROOT_DIR"/data/hysteria2/.env 2>/dev/null || true
chmod 644 "$ROOT_DIR"/data/xray/config.json 2>/dev/null || true
chmod 644 "$ROOT_DIR"/data/hysteria2/server.yaml 2>/dev/null || true

echo "Imported runtime data into: $ROOT_DIR/data"
echo "Run scripts/smoke-test.sh before cutover."

