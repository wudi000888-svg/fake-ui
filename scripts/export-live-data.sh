#!/usr/bin/env bash
set -Eeuo pipefail

OUT="${1:-/root/xray-proxy-panel-compose-state-$(date +%Y%m%d-%H%M%S).tgz}"
PANEL_DIR="${PANEL_DIR:-/opt/xray-proxy-panel}"
XRAY_CONFIG="${XRAY_CONFIG:-/usr/local/etc/xray/config.json}"
HY2_DIR="${HY2_DIR:-/opt/hysteria2}"
LETSENCRYPT_DIR="${LETSENCRYPT_DIR:-/etc/letsencrypt}"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

mkdir -p \
  "$TMP/data/panel" \
  "$TMP/data/xray" \
  "$TMP/data/hysteria2" \
  "$TMP/data/letsencrypt" \
  "$TMP/data/acme" \
  "$TMP/data/nginx" \
  "$TMP/data/backups/xray" \
  "$TMP/data/backups/hysteria2" \
  "$TMP/snapshot"

copy_file() {
  local src="$1"
  local dst="$2"
  if [[ -f "$src" ]]; then
    mkdir -p "$(dirname "$dst")"
    cp -a "$src" "$dst"
  fi
}

copy_dir_contents() {
  local src="$1"
  local dst="$2"
  if [[ -d "$src" ]]; then
    mkdir -p "$dst"
    cp -a "$src"/. "$dst"/
  fi
}

panel_files=(
  auth.json
  users.json
  link_settings.json
  plans.json
  orders.json
  nodes.json
  admin_profile.json
  registrations.json
  sub_token.txt
  hy2_traffic_secret.txt
  audit.log
  subscription_access.log
  xray-proxy-panel-login.txt
  xray-proxy-panel-user-login.txt
  xray-proxy-panel-airport-users.txt
)

for f in "${panel_files[@]}"; do
  copy_file "$PANEL_DIR/$f" "$TMP/data/panel/$f"
done

copy_file /root/xray-proxy-panel-login.txt "$TMP/data/panel/xray-proxy-panel-login.txt"
copy_file /root/xray-proxy-panel-user-login.txt "$TMP/data/panel/xray-proxy-panel-user-login.txt"
copy_file /root/xray-proxy-panel-airport-users.txt "$TMP/data/panel/xray-proxy-panel-airport-users.txt"

copy_file "$XRAY_CONFIG" "$TMP/data/xray/config.json"
copy_dir_contents "$(dirname "$XRAY_CONFIG")/log" "$TMP/data/xray/log"
copy_file "$HY2_DIR/.env" "$TMP/data/hysteria2/.env"
copy_file "$HY2_DIR/server.yaml" "$TMP/data/hysteria2/server.yaml"
copy_dir_contents "$LETSENCRYPT_DIR" "$TMP/data/letsencrypt"

copy_dir_contents /etc/nginx "$TMP/snapshot/nginx"
copy_file /etc/systemd/system/xray.service "$TMP/snapshot/systemd/xray.service"
copy_file /etc/systemd/system/xray-proxy-panel.service "$TMP/snapshot/systemd/xray-proxy-panel.service"

cat > "$TMP/MANIFEST.txt" <<EOF
exported_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
source_host=$(hostname)
panel_dir=$PANEL_DIR
xray_config=$XRAY_CONFIG
hy2_dir=$HY2_DIR
letsencrypt_dir=$LETSENCRYPT_DIR
EOF

tar -C "$TMP" -czf "$OUT" data snapshot MANIFEST.txt
chmod 600 "$OUT"

echo "Exported compose migration bundle:"
echo "$OUT"

