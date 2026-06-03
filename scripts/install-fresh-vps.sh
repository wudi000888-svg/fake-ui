#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR"
XRAY_IMAGE_DEFAULT="ghcr.io/xtls/xray-core:latest"
ROOT_DOMAIN="${ROOT_DOMAIN:-}"
PANEL_DOMAIN="${PANEL_DOMAIN:-}"
HY2_DOMAIN="${HY2_DOMAIN:-}"
VLESS_DOMAIN="${VLESS_DOMAIN:-}"
LE_EMAIL="${LE_EMAIL:-}"
REALITY_SNI="${REALITY_SNI:-}"
AUTO_YES="${AUTO_YES:-0}"
DEPLOY_MODE="${DEPLOY_MODE:-docker}"
ALLOW_NATIVE_443_REWRITE="${ALLOW_NATIVE_443_REWRITE:-0}"
HY2_PORT="${HY2_PORT:-443}"
RENEW_CERT="${RENEW_CERT:-0}"
CERT_MODE="unknown"
CERT_FALLBACK_REASON=""

usage() {
  cat <<'EOF'
用法:
  sudo bash scripts/install-fresh-vps.sh

也可以用参数提前填写，适合重装后快速复刻:
  sudo bash scripts/install-fresh-vps.sh \
    --root-domain example.com \
    --panel-domain panel.example.com \
    --hy2-domain hy.example.com \
    --vless-domain vless.example.com \
    --email admin@example.com \
    --reality-sni www.cloudflare.com \
    --hy2-port 443 \
    --mode docker

参数:
  --root-domain      根域名，例如 example.com
  --panel-domain     面板域名，例如 panel.example.com
  --hy2-domain       Hysteria2 域名，例如 hy.example.com
  --vless-domain     VLESS Reality 地址域名，例如 vless.example.com
  --email            Let’s Encrypt 证书邮箱
  --reality-sni      Reality 分流 SNI，默认 www.cloudflare.com
  --hy2-port         Hysteria2 UDP 监听端口，默认 443
  --mode             部署模式：docker、native-nginx、internal，默认 docker
                     docker       容器 Nginx 接管 TCP 80/443
                     native-nginx 系统 Nginx 接管 TCP 80/443
                     internal     不接管公网 TCP 80/443，只启动内部服务并生成接入模板
  --allow-nginx-443-rewrite
                     native-nginx 模式下允许继续配置 stream 443。
                     如果原生 Nginx 已有 HTTPS 站点，请先确认不会冲突。
  --renew-cert       只重新申请正式证书，不重置面板数据。适合自签证书兜底后补签。
  -y, --yes          DNS 确认时自动继续
  -h, --help         显示帮助
EOF
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --root-domain|--domain)
        ROOT_DOMAIN="${2:-}"; shift 2 ;;
      --panel-domain|--panel)
        PANEL_DOMAIN="${2:-}"; shift 2 ;;
      --hy2-domain|--hy2)
        HY2_DOMAIN="${2:-}"; shift 2 ;;
      --vless-domain|--vless)
        VLESS_DOMAIN="${2:-}"; shift 2 ;;
      --email|--le-email)
        LE_EMAIL="${2:-}"; shift 2 ;;
      --reality-sni|--sni)
        REALITY_SNI="${2:-}"; shift 2 ;;
      --hy2-port)
        HY2_PORT="${2:-}"; shift 2 ;;
      --mode|--deploy-mode)
        DEPLOY_MODE="${2:-}"; shift 2 ;;
      --allow-nginx-443-rewrite)
        ALLOW_NATIVE_443_REWRITE=1; shift ;;
      --renew-cert)
        RENEW_CERT=1; shift ;;
      -y|--yes)
        AUTO_YES=1; shift ;;
      -h|--help)
        usage; exit 0 ;;
      *)
        echo "未知参数: $1" >&2
        usage
        exit 1 ;;
    esac
  done
}

load_existing_env() {
  if [[ ! -f .env ]]; then
    return
  fi
  local key value
  while IFS='=' read -r key value; do
    key="${key%%[[:space:]]*}"
    value="${value%$'\r'}"
    value="${value%\"}"
    value="${value#\"}"
    case "$key" in
      PANEL_DOMAIN) PANEL_DOMAIN="${PANEL_DOMAIN:-$value}" ;;
      HY2_DOMAIN) HY2_DOMAIN="${HY2_DOMAIN:-$value}" ;;
      ROOT_DOMAIN) ROOT_DOMAIN="${ROOT_DOMAIN:-$value}" ;;
      DEFAULT_VLESS_ADDRESS) VLESS_DOMAIN="${VLESS_DOMAIN:-$value}" ;;
      LE_EMAIL) LE_EMAIL="${LE_EMAIL:-$value}" ;;
      REALITY_SNI) REALITY_SNI="${REALITY_SNI:-$value}" ;;
      HY2_PORT)
        if [[ "$RENEW_CERT" == "1" && "$HY2_PORT" == "443" ]]; then
          HY2_PORT="$value"
        else
          HY2_PORT="${HY2_PORT:-$value}"
        fi ;;
      DEPLOY_MODE)
        if [[ "$RENEW_CERT" == "1" && "$DEPLOY_MODE" == "docker" ]]; then
          DEPLOY_MODE="$value"
        else
          DEPLOY_MODE="${DEPLOY_MODE:-$value}"
        fi ;;
      ALLOW_NATIVE_443_REWRITE)
        if [[ "$RENEW_CERT" == "1" && "$ALLOW_NATIVE_443_REWRITE" == "0" ]]; then
          ALLOW_NATIVE_443_REWRITE="$value"
        else
          ALLOW_NATIVE_443_REWRITE="${ALLOW_NATIVE_443_REWRITE:-$value}"
        fi ;;
    esac
  done <.env
}

need_root() {
  if [[ "$(id -u)" != "0" ]]; then
    echo "请使用 root 运行：sudo bash scripts/install-fresh-vps.sh" >&2
    exit 1
  fi
}

ask() {
  local var="$1"
  local prompt="$2"
  local default="${3:-}"
  local current="${!var:-}"
  local value
  if [[ -n "$current" ]]; then
    printf -v "$var" "%s" "$current"
    echo "$prompt: $current"
    return
  fi
  if [[ -n "$default" ]]; then
    read -r -p "$prompt [$default]: " value
    value="${value:-$default}"
  else
    while true; do
      read -r -p "$prompt: " value
      [[ -n "$value" ]] && break
      echo "不能为空。"
    done
  fi
  printf -v "$var" "%s" "$value"
}

normalize_domain() {
  local value="$1"
  value="${value#http://}"
  value="${value#https://}"
  value="${value%%/*}"
  value="${value%.}"
  printf '%s' "$value" | tr '[:upper:]' '[:lower:]'
}

validate_domain() {
  local label="$1"
  local value="$2"
  if [[ ! "$value" =~ ^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$ ]]; then
    echo "$label 格式不正确: $value" >&2
    exit 1
  fi
}

normalize_and_validate_inputs() {
  ROOT_DOMAIN="$(normalize_domain "$ROOT_DOMAIN")"
  PANEL_DOMAIN="$(normalize_domain "$PANEL_DOMAIN")"
  HY2_DOMAIN="$(normalize_domain "$HY2_DOMAIN")"
  VLESS_DOMAIN="$(normalize_domain "$VLESS_DOMAIN")"
  REALITY_SNI="${REALITY_SNI:-www.cloudflare.com}"
  REALITY_SNI="$(normalize_domain "$REALITY_SNI")"

  validate_domain "根域名" "$ROOT_DOMAIN"
  validate_domain "面板域名" "$PANEL_DOMAIN"
  validate_domain "Hysteria2 域名" "$HY2_DOMAIN"
  validate_domain "VLESS 域名" "$VLESS_DOMAIN"
  validate_domain "Reality SNI" "$REALITY_SNI"
  if [[ ! "$LE_EMAIL" =~ ^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$ ]]; then
    echo "Let’s Encrypt 邮箱格式不正确: $LE_EMAIL" >&2
    exit 1
  fi
  if [[ ! "$HY2_PORT" =~ ^[0-9]+$ ]] || (( HY2_PORT < 1 || HY2_PORT > 65535 )); then
    echo "Hysteria2 端口不正确: $HY2_PORT" >&2
    exit 1
  fi
  case "$DEPLOY_MODE" in
    docker|native-nginx|internal) ;;
    *)
      echo "部署模式不正确: $DEPLOY_MODE，可选 docker、native-nginx、internal" >&2
      exit 1 ;;
  esac
}

compose() {
  docker compose "$@"
}

port_process_hint() {
  local proto="$1"
  local port="$2"
  ss "-ln${proto}p" 2>/dev/null | awk -v p=":$port" '$0 ~ p {print; found=1} END {exit found ? 0 : 1}' || true
}

detect_native_nginx() {
  NATIVE_NGINX_INSTALLED="no"
  NATIVE_NGINX_ENABLED="no"
  NATIVE_NGINX_ACTIVE="no"
  if command -v nginx >/dev/null 2>&1; then
    NATIVE_NGINX_INSTALLED="yes"
  fi
  if command -v systemctl >/dev/null 2>&1 && systemctl is-enabled --quiet nginx 2>/dev/null; then
    NATIVE_NGINX_ENABLED="yes"
  fi
  if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet nginx 2>/dev/null; then
    NATIVE_NGINX_ACTIVE="yes"
  elif pgrep -x nginx >/dev/null 2>&1; then
    NATIVE_NGINX_ACTIVE="yes"
  fi
}

preflight_entry_check() {
  local tcp443
  local tcp80
  local udp_hy2
  local effective_mode
  local warning
  detect_native_nginx
  tcp80="$(port_process_hint t 80)"
  tcp443="$(port_process_hint t 443)"
  udp_hy2="$(port_process_hint u "$HY2_PORT")"
  effective_mode="$DEPLOY_MODE"
  warning=""

  if [[ "$DEPLOY_MODE" == "docker" && "$NATIVE_NGINX_INSTALLED" == "yes" && "$NATIVE_NGINX_ACTIVE" == "yes" ]]; then
    effective_mode="native-nginx"
    ALLOW_NATIVE_443_REWRITE=1
    warning+="检测到原生 Nginx 已安装且运行中，脚本将自动改用 native-nginx 模式；TCP 443 将由原生 Nginx 接管，Hysteria2 使用 UDP $HY2_PORT。"$'\n'
  fi

  if [[ -n "$tcp443" ]]; then
    if grep -qi "nginx" <<<"$tcp443"; then
      if [[ "$DEPLOY_MODE" == "docker" ]]; then
        effective_mode="native-nginx"
        warning+="检测到原生 Nginx 占用 TCP 443，脚本将自动改用 native-nginx 模式；Hysteria2 仍默认使用 UDP $HY2_PORT。"$'\n'
      fi
    elif [[ "$DEPLOY_MODE" == "docker" ]]; then
      warning+="TCP 443 已被非 Nginx 程序占用，docker 模式不能继续。请停掉占用程序，或改用 --mode internal。"$'\n'
    fi
  fi

  if [[ -n "$udp_hy2" ]]; then
    warning+="UDP $HY2_PORT 已被占用，Hysteria2 不能共享 UDP 端口。请停掉占用程序，或改用 --hy2-port 8443。"$'\n'
  fi

  cat <<EOF

============================================================
部署前预检
============================================================
公网 IP: ${PUBLIC_IP:-未知}
根域名: $ROOT_DOMAIN
面板域名: $PANEL_DOMAIN
VLESS 域名: $VLESS_DOMAIN
Hysteria2 域名: $HY2_DOMAIN
Hysteria2 UDP 端口: $HY2_PORT
Reality SNI: $REALITY_SNI
证书邮箱: $LE_EMAIL

原生 Nginx:
  已安装: $NATIVE_NGINX_INSTALLED
  已启用: $NATIVE_NGINX_ENABLED
  运行中: $NATIVE_NGINX_ACTIVE

端口占用:
  TCP 80:
${tcp80:-  未检测到占用}
  TCP 443:
${tcp443:-  未检测到占用}
  UDP $HY2_PORT:
${udp_hy2:-  未检测到占用}

将采用部署模式: $effective_mode

注意事项:
  1. DNS 必须提前解析到本机公网 IP，并且 Cloudflare 请使用「仅 DNS」。
  2. TCP 443 用于面板 HTTPS / VLESS Reality 分流。
  3. UDP $HY2_PORT 用于 Hysteria2，UDP 端口不能通过 Nginx 共享。
  4. native-nginx 模式会生成并应用 Nginx 配置；如已有复杂站点，请先备份配置。
  5. 脚本会启用 BBR、写入运行配置、生成管理员密码，并启动 Docker Compose 服务。
EOF
  if [[ -n "$warning" ]]; then
    printf '\n预检提示:\n%s' "$warning"
  fi
  echo "============================================================"

  if [[ -n "$udp_hy2" ]]; then
    exit 1
  fi
  if [[ -n "$tcp443" && "$effective_mode" == "docker" ]]; then
    exit 1
  fi
  DEPLOY_MODE="$effective_mode"
  if [[ "$DEPLOY_MODE" == "native-nginx" && -n "$tcp443" && "$ALLOW_NATIVE_443_REWRITE" != "1" ]]; then
    ALLOW_NATIVE_443_REWRITE=1
  fi
}

enable_bbr() {
  for f in /etc/sysctl.conf /etc/sysctl.d/99-sysctl.conf; do
    if [[ -f "$f" ]] && grep -Eq '^net\.ipv4\.ip_forward\s*=\s*0' "$f"; then
      cp "$f" "$f.bak.$(date +%Y%m%d%H%M%S)"
      sed -i -E 's/^net\.ipv4\.ip_forward\s*=\s*0/# net.ipv4.ip_forward = 0 # disabled by xray-proxy-panel installer/' "$f"
    fi
  done
  cat >/etc/sysctl.d/zz-xray-proxy-panel.conf <<'EOF'
net.core.default_qdisc=fq
net.ipv4.tcp_congestion_control=bbr
net.ipv4.ip_forward=1
EOF
  sysctl --system >/dev/null || true
  sysctl -w net.ipv4.ip_forward=1 >/dev/null || true
}

configure_docker_dns() {
  mkdir -p /etc/docker
  if [[ -f /etc/docker/daemon.json ]] && ! grep -q '"dns"' /etc/docker/daemon.json; then
    cp /etc/docker/daemon.json "/etc/docker/daemon.json.bak.$(date +%Y%m%d%H%M%S)"
  fi
  cat >/etc/docker/daemon.json <<'EOF'
{
  "dns": ["183.60.83.19", "183.60.82.98", "223.5.5.5", "1.1.1.1", "8.8.8.8"]
}
EOF
  if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet docker 2>/dev/null; then
    systemctl restart docker
  fi
}

install_docker() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    return
  fi
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y ca-certificates curl docker.io docker-compose
  systemctl enable --now docker
  if ! docker compose version >/dev/null 2>&1; then
    mkdir -p /usr/local/lib/docker/cli-plugins
    curl -fsSL -o /usr/local/lib/docker/cli-plugins/docker-compose https://github.com/docker/compose/releases/download/v2.33.1/docker-compose-linux-x86_64
    chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
  fi
}

install_native_nginx() {
  if [[ "$DEPLOY_MODE" != "native-nginx" ]]; then
    return
  fi
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y nginx-full certbot
  systemctl enable --now nginx
}

write_env() {
  cat >.env <<EOF
ROOT_DOMAIN=$ROOT_DOMAIN
PANEL_DOMAIN=$PANEL_DOMAIN
HY2_DOMAIN=$HY2_DOMAIN
PUBLIC_BASE_URL=https://$PANEL_DOMAIN
DEFAULT_VLESS_ADDRESS=$VLESS_DOMAIN
DEFAULT_VLESS_NAME=VLESS_Reality_$VLESS_DOMAIN
DEFAULT_HY2_NAME=HY2_$HY2_DOMAIN
HY2_MASQUERADE_URL=https://$ROOT_DOMAIN
QR_CMD=qrencode
HY2_PORT=$HY2_PORT
REALITY_SNI=$REALITY_SNI
XRAY_REALITY_PORT=8443
LE_EMAIL=$LE_EMAIL
DEPLOY_MODE=$DEPLOY_MODE
ALLOW_NATIVE_443_REWRITE=$ALLOW_NATIVE_443_REWRITE
TZ=Asia/Hong_Kong
XRAY_IMAGE=ghcr.io/xtls/xray-core:latest
PANEL_IMAGE=xray-proxy-panel:local
HYSTERIA_IMAGE=tobyxdd/hysteria:latest
NGINX_IMAGE=nginx:1.27-alpine
CERTBOT_IMAGE=certbot/certbot:latest
EOF
}

init_dirs() {
  mkdir -p \
    data/panel \
    data/xray/log \
    data/hysteria2 \
    data/letsencrypt \
    data/acme \
    data/nginx/log \
    data/backups/xray \
    data/backups/hysteria2
}

xray_keys() {
  XRAY_IMAGE="$XRAY_IMAGE_DEFAULT"
  docker pull "$XRAY_IMAGE" >/dev/null
  local keys
  keys="$(docker run --rm "$XRAY_IMAGE" x25519)"
  REALITY_PRIVATE_KEY="$(printf '%s\n' "$keys" | awk -F': *' '/PrivateKey|Private key/ {print $2; exit}')"
  REALITY_PUBLIC_KEY="$(printf '%s\n' "$keys" | awk -F': *' '/Password \(PublicKey\)|PublicKey|Public key/ {print $2; exit}')"
  REALITY_SHORT_ID="$(openssl rand -hex 8)"
  if [[ -z "$REALITY_PRIVATE_KEY" || -z "$REALITY_PUBLIC_KEY" ]]; then
    echo "$keys"
    echo "Reality keypair 生成失败。" >&2
    exit 1
  fi
}

write_runtime_json() {
  ADMIN_PASS="$(openssl rand -base64 18 | tr -d '\n' | tr '/+' 'Aa' | cut -c1-18)"
  HY_PASS="$(openssl rand -base64 24 | tr -d '\n' | tr '/+' 'Bb' | cut -c1-24)"
  SESSION_SECRET="$(openssl rand -hex 32)"

  PANEL_DIR="$APP_DIR/data/panel" \
  PUBLIC_BASE_URL="https://$PANEL_DOMAIN" \
  PANEL_DOMAIN="$PANEL_DOMAIN" \
  HY2_DOMAIN="$HY2_DOMAIN" \
  DEFAULT_VLESS_ADDRESS="$VLESS_DOMAIN" \
  DEFAULT_VLESS_NAME="VLESS_Reality_$VLESS_DOMAIN" \
  DEFAULT_HY2_NAME="HY2_$HY2_DOMAIN" \
  HY2_MASQUERADE_URL="https://$ROOT_DOMAIN" \
  ADMIN_PASS="$ADMIN_PASS" \
  SESSION_SECRET="$SESSION_SECRET" \
  python3 - <<'PY'
import json
import os
import sys

sys.path.insert(0, "baseline")
import admin_profile
import auth_store
import node_catalog
import plans_store

auth_store.save_auth({
    "session_secret": os.environ["SESSION_SECRET"],
    "users": {
        "admin": {
            "role": "admin",
            "password": auth_store.make_password_hash(os.environ["ADMIN_PASS"]),
        }
    },
})
plans_store.load_plans()
node_catalog.load_catalog()
admin_profile.load_profile()
for path, data in {
    "data/panel/users.json": {"version": 1, "users": {}},
    "data/panel/orders.json": {"version": 1, "orders": []},
    "data/panel/registrations.json": {"version": 1, "pending": [], "resets": []},
}.items():
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
PY

  cat >data/panel/link_settings.json <<EOF
{
  "vless_address": "$VLESS_DOMAIN",
  "vless_port": 443,
  "vless_name": "VLESS_Reality_$VLESS_DOMAIN",
  "hy2_name": "HY2_$HY2_DOMAIN"
}
EOF

  cat >data/hysteria2/.env <<EOF
HY_DOMAIN=$HY2_DOMAIN
HY_PORT=$HY2_PORT
HY_PASSWORD=$HY_PASS
EOF

  cat >data/xray/config.json <<EOF
{
  "log": {"loglevel": "warning", "access": "/var/log/xray/access.log", "error": "/var/log/xray/error.log"},
  "api": {"tag": "api", "services": ["StatsService"]},
  "stats": {},
  "policy": {
    "levels": {"0": {"statsUserUplink": true, "statsUserDownlink": true}},
    "system": {"statsInboundUplink": true, "statsInboundDownlink": true, "statsOutboundUplink": true, "statsOutboundDownlink": true}
  },
  "inbounds": [
    {
      "tag": "vless-reality-in",
      "listen": "0.0.0.0",
      "port": 8443,
      "protocol": "vless",
      "settings": {"clients": [], "decryption": "none"},
      "streamSettings": {
        "network": "tcp",
        "security": "reality",
        "realitySettings": {
          "show": false,
          "dest": "$REALITY_SNI:443",
          "xver": 0,
          "serverNames": ["$REALITY_SNI"],
          "privateKey": "$REALITY_PRIVATE_KEY",
          "shortIds": ["$REALITY_SHORT_ID"]
        }
      },
      "sniffing": {"enabled": true, "destOverride": ["http", "tls", "quic"]}
    },
    {"tag": "api", "listen": "127.0.0.1", "port": 10085, "protocol": "dokodemo-door", "settings": {"address": "127.0.0.1"}}
  ],
  "outbounds": [
    {"tag": "direct", "protocol": "freedom", "settings": {"domainStrategy": "UseIPv4"}},
    {"tag": "block", "protocol": "blackhole"}
  ],
  "routing": {
    "domainStrategy": "IPIfNonMatch",
    "rules": [
      {"type": "field", "inboundTag": ["api"], "outboundTag": "api"},
      {"type": "field", "ip": ["geoip:private"], "outboundTag": "block"},
      {"type": "field", "protocol": ["bittorrent"], "outboundTag": "block"},
      {"type": "field", "inboundTag": ["vless-reality-in"], "outboundTag": "direct"}
    ]
  }
}
EOF

  cat >data/panel/xray-proxy-panel-login.txt <<EOF
Panel URL: https://$PANEL_DOMAIN/login
Username: admin
Password: $ADMIN_PASS
EOF

  cat >data/DEPLOY-SECRETS.txt <<EOF
Panel URL: https://$PANEL_DOMAIN/login
Admin username: admin
Admin password: $ADMIN_PASS
HY2 admin password: $HY_PASS
VLESS public key: $REALITY_PUBLIC_KEY
VLESS short id: $REALITY_SHORT_ID
Reality SNI: $REALITY_SNI
VLESS address: $VLESS_DOMAIN:443
Hysteria2 address: $HY2_DOMAIN:$HY2_PORT
EOF

  chmod 600 data/panel/*.json data/hysteria2/.env data/DEPLOY-SECRETS.txt data/panel/xray-proxy-panel-login.txt
}

compile_and_validate() {
  python3 - <<'PY'
from pathlib import Path
import py_compile
for p in sorted(Path("baseline").glob("*.py")):
    py_compile.compile(str(p), doraise=True)
print("Python 编译通过")
PY
  docker run --rm -v "$APP_DIR/data/xray:/etc/xray" "$XRAY_IMAGE" run -test -config /etc/xray/config.json
}

write_native_nginx_templates() {
  mkdir -p generated/nginx
  cat >generated/nginx/panel-http-acme.conf <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name $PANEL_DOMAIN $HY2_DOMAIN;

    location ^~ /.well-known/acme-challenge/ {
        root $APP_DIR/data/acme;
        default_type text/plain;
    }

    location / {
        return 301 https://\$host\$request_uri;
    }
}
EOF

  cat >generated/nginx/panel-local-https.conf <<EOF
map \$http_upgrade \$connection_upgrade {
    default upgrade;
    '' close;
}

server {
    listen 127.0.0.1:10000 ssl http2;
    server_name $PANEL_DOMAIN;

    ssl_certificate $APP_DIR/data/letsencrypt/live/$PANEL_DOMAIN/fullchain.pem;
    ssl_certificate_key $APP_DIR/data/letsencrypt/live/$PANEL_DOMAIN/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_session_timeout 1d;
    ssl_session_cache shared:SSL:10m;

    client_max_body_size 20m;

    location / {
        proxy_pass http://127.0.0.1:9100;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection \$connection_upgrade;
        proxy_read_timeout 300s;
    }
}
EOF

  cat >generated/nginx/stream-443.conf <<EOF
stream {
    map \$ssl_preread_server_name \$xray_proxy_panel_stream_backend {
        $REALITY_SNI xray_proxy_panel_reality;
        default xray_proxy_panel_web_https;
    }

    upstream xray_proxy_panel_reality {
        server 127.0.0.1:8443;
    }

    upstream xray_proxy_panel_web_https {
        server 127.0.0.1:10000;
    }

    server {
        listen 443 reuseport;
        listen [::]:443 reuseport;
        proxy_pass \$xray_proxy_panel_stream_backend;
        ssl_preread on;
        proxy_connect_timeout 10s;
        proxy_timeout 3600s;
    }
}
EOF
}

apply_native_nginx_http_only() {
  cp generated/nginx/panel-http-acme.conf /etc/nginx/conf.d/xray-proxy-panel-acme.conf
  nginx -t
  systemctl reload nginx
}

copy_native_certs() {
  mkdir -p "data/letsencrypt/live/$PANEL_DOMAIN"
  cp -Lf "/etc/letsencrypt/live/$PANEL_DOMAIN/fullchain.pem" "data/letsencrypt/live/$PANEL_DOMAIN/fullchain.pem"
  cp -Lf "/etc/letsencrypt/live/$PANEL_DOMAIN/privkey.pem" "data/letsencrypt/live/$PANEL_DOMAIN/privkey.pem"
  cp -Lf "/etc/letsencrypt/live/$PANEL_DOMAIN/chain.pem" "data/letsencrypt/live/$PANEL_DOMAIN/chain.pem" || true
  cp -Lf "/etc/letsencrypt/live/$PANEL_DOMAIN/cert.pem" "data/letsencrypt/live/$PANEL_DOMAIN/cert.pem" || true
}

reload_entry_after_cert() {
  if [[ "$DEPLOY_MODE" == "docker" ]]; then
    docker restart xray-proxy-nginx >/dev/null 2>&1 || true
  elif [[ "$DEPLOY_MODE" == "native-nginx" ]]; then
    systemctl reload nginx >/dev/null 2>&1 || true
  fi
}

link_hy2_cert_to_panel_cert() {
  mkdir -p "data/letsencrypt/live/$HY2_DOMAIN"
  if [[ "$HY2_DOMAIN" != "$PANEL_DOMAIN" ]]; then
    ln -sf "../$PANEL_DOMAIN/fullchain.pem" "data/letsencrypt/live/$HY2_DOMAIN/fullchain.pem"
    ln -sf "../$PANEL_DOMAIN/privkey.pem" "data/letsencrypt/live/$HY2_DOMAIN/privkey.pem"
    ln -sf "../$PANEL_DOMAIN/chain.pem" "data/letsencrypt/live/$HY2_DOMAIN/chain.pem" || true
    ln -sf "../$PANEL_DOMAIN/cert.pem" "data/letsencrypt/live/$HY2_DOMAIN/cert.pem" || true
  fi
}

generate_self_signed_cert() {
  local reason="${1:-Let’s Encrypt 证书申请失败}"
  local cert_dir="data/letsencrypt/live/$PANEL_DOMAIN"
  local tmp_conf
  CERT_MODE="self-signed"
  CERT_FALLBACK_REASON="$reason"
  mkdir -p "$cert_dir" "data/letsencrypt/live/$HY2_DOMAIN"
  tmp_conf="$(mktemp)"
  cat >"$tmp_conf" <<EOF
[req]
default_bits = 2048
prompt = no
default_md = sha256
distinguished_name = dn
x509_extensions = v3_req

[dn]
CN = $PANEL_DOMAIN

[v3_req]
subjectAltName = @alt_names

[alt_names]
DNS.1 = $PANEL_DOMAIN
DNS.2 = $HY2_DOMAIN
DNS.3 = $ROOT_DOMAIN
EOF
  openssl req -x509 -nodes -newkey rsa:2048 -days 365 \
    -keyout "$cert_dir/privkey.pem" \
    -out "$cert_dir/fullchain.pem" \
    -config "$tmp_conf" >/dev/null 2>&1
  cp "$cert_dir/fullchain.pem" "$cert_dir/cert.pem"
  cp "$cert_dir/fullchain.pem" "$cert_dir/chain.pem"
  rm -f "$tmp_conf"
  link_hy2_cert_to_panel_cert
  chmod 600 "$cert_dir/privkey.pem" "$cert_dir/fullchain.pem" "$cert_dir/cert.pem" "$cert_dir/chain.pem" 2>/dev/null || true
  echo "SELF_SIGNED" >data/letsencrypt/CERT_MODE
  cat >data/letsencrypt/SELF_SIGNED_NOTICE.txt <<EOF
当前使用自签证书。
原因: $reason

影响:
- 面板可以启动，但浏览器会提示证书不受信任。
- Hysteria2 客户端可能需要开启 allowInsecure / insecure 才能测试。
- 生产环境建议尽快补签 Let’s Encrypt 正式证书。

DNS/端口修复后执行:
sudo bash $APP_DIR/scripts/install-fresh-vps.sh --renew-cert \\
  --root-domain $ROOT_DOMAIN \\
  --panel-domain $PANEL_DOMAIN \\
  --hy2-domain $HY2_DOMAIN \\
  --vless-domain $VLESS_DOMAIN \\
  --email $LE_EMAIL \\
  --reality-sni $REALITY_SNI \\
  --hy2-port $HY2_PORT \\
  --mode $DEPLOY_MODE \\
  --yes
EOF
}

apply_native_nginx_final() {
  cp generated/nginx/panel-http-acme.conf /etc/nginx/conf.d/xray-proxy-panel-acme.conf
  cp generated/nginx/panel-local-https.conf /etc/nginx/conf.d/xray-proxy-panel-local-https.conf

  mkdir -p /etc/nginx/stream-conf.d
  if ! grep -R "stream-conf.d/\\*.conf" /etc/nginx/nginx.conf >/dev/null 2>&1; then
    cat >/etc/nginx/conf.d/xray-proxy-panel-stream-warning.conf <<'EOF'
# stream 配置不能放在 http 的 conf.d 中。
# 安装脚本已生成 /etc/nginx/stream-conf.d/xray-proxy-panel-stream.conf。
# 请确认 /etc/nginx/nginx.conf 的顶层包含：
# include /etc/nginx/stream-conf.d/*.conf;
EOF
  fi
  cp generated/nginx/stream-443.conf /etc/nginx/stream-conf.d/xray-proxy-panel-stream.conf

  if [[ "$ALLOW_NATIVE_443_REWRITE" != "1" ]]; then
    cat <<EOF

已生成原生 Nginx stream 配置，但未自动启用最终 443 分流。
原因：未传入 --allow-nginx-443-rewrite，避免破坏已有 HTTPS 站点。

请检查:
  $APP_DIR/generated/nginx/stream-443.conf
  /etc/nginx/stream-conf.d/xray-proxy-panel-stream.conf

确认可以由原生 Nginx 接管 TCP 443 后，重新运行并追加:
  --mode native-nginx --allow-nginx-443-rewrite
EOF
    return
  fi

  if ! grep -R "stream-conf.d/\\*.conf" /etc/nginx/nginx.conf >/dev/null 2>&1; then
    cp /etc/nginx/nginx.conf "/etc/nginx/nginx.conf.bak.$(date +%Y%m%d%H%M%S)"
    printf '\ninclude /etc/nginx/stream-conf.d/*.conf;\n' >>/etc/nginx/nginx.conf
  fi
  nginx -t
  systemctl reload nginx
}

compose_up_entry() {
  if [[ "$DEPLOY_MODE" == "docker" ]]; then
    compose up -d nginx
  else
    compose up -d xray panel
  fi
}

start_for_certbot() {
  if [[ "$DEPLOY_MODE" == "internal" ]]; then
    compose build panel xray
    compose up -d xray panel
    write_native_nginx_templates
    return
  fi
  mkdir -p "data/letsencrypt/live/$PANEL_DOMAIN"
  if [[ ! -f "data/letsencrypt/live/$PANEL_DOMAIN/fullchain.pem" ]]; then
    generate_self_signed_cert "安装预启动占位证书，等待正式证书申请。"
  fi
  link_hy2_cert_to_panel_cert
  compose build panel xray
  if [[ "$DEPLOY_MODE" == "docker" ]]; then
    compose up -d nginx
  else
    compose up -d xray panel
    write_native_nginx_templates
    if [[ "$DEPLOY_MODE" == "native-nginx" ]]; then
      install_native_nginx
      apply_native_nginx_http_only
    fi
  fi
}

issue_cert() {
  if [[ "$DEPLOY_MODE" == "internal" ]]; then
    echo "internal 模式不自动签发证书，请按 generated/nginx/ 中模板接入现有网关后自行签发。"
    return
  fi
  rm -rf "data/letsencrypt/live/$PANEL_DOMAIN" "data/letsencrypt/live/$HY2_DOMAIN" \
    "data/letsencrypt/archive/$PANEL_DOMAIN" "data/letsencrypt/archive/$HY2_DOMAIN" \
    "data/letsencrypt/renewal/$PANEL_DOMAIN.conf" "data/letsencrypt/renewal/$HY2_DOMAIN.conf"
  generate_self_signed_cert "证书申请前的临时占位证书，保证 Nginx 可以启动。"
  compose_up_entry
  sleep 2
  rm -rf "data/letsencrypt/live/$PANEL_DOMAIN" "data/letsencrypt/live/$HY2_DOMAIN" \
    "data/letsencrypt/archive/$PANEL_DOMAIN" "data/letsencrypt/archive/$HY2_DOMAIN" \
    "data/letsencrypt/renewal/$PANEL_DOMAIN.conf" "data/letsencrypt/renewal/$HY2_DOMAIN.conf"
  local rc=0
  if [[ "$DEPLOY_MODE" == "docker" ]]; then
    compose run --rm certbot certonly --webroot -w /var/www/certbot \
      -d "$PANEL_DOMAIN" -d "$HY2_DOMAIN" \
      --email "$LE_EMAIL" --agree-tos --no-eff-email --non-interactive || rc=$?
  else
    certbot certonly --webroot -w "$APP_DIR/data/acme" \
      -d "$PANEL_DOMAIN" -d "$HY2_DOMAIN" \
      --email "$LE_EMAIL" --agree-tos --no-eff-email --non-interactive || rc=$?
    if [[ "$rc" == "0" ]]; then
      copy_native_certs
    fi
  fi

  if [[ "$rc" != "0" ]]; then
    echo
    echo "Let’s Encrypt 正式证书申请失败，错误码: $rc"
    echo "脚本将生成自签证书作为兜底，保证面板和服务可以先启动。"
    generate_self_signed_cert "Let’s Encrypt 申请失败，错误码: $rc。常见原因是 DNS 未生效、Cloudflare 未设为仅 DNS、TCP 80 不通或端口被占用。"
    reload_entry_after_cert
    return
  fi

  CERT_MODE="letsencrypt"
  CERT_FALLBACK_REASON=""
  echo "LETSENCRYPT" >data/letsencrypt/CERT_MODE
  rm -f data/letsencrypt/SELF_SIGNED_NOTICE.txt
  link_hy2_cert_to_panel_cert
  reload_entry_after_cert
}

generate_hy2_config() {
  if [[ "$DEPLOY_MODE" == "docker" ]]; then
    compose up -d xray panel nginx
  else
    compose up -d xray panel
  fi
  sleep 10
  docker exec -i xray-proxy-panel python3 - <<'PY'
import sys
from pathlib import Path

sys.path.insert(0, "/app")

import hy2_config_builder
Path("/data/hysteria2/server.yaml").write_text(hy2_config_builder.build_config("direct"), encoding="utf-8")
print("Hysteria2 配置已生成")
PY
}

sync_node_exit_names() {
  docker exec -i xray-proxy-panel python3 /app/sync_node_exit_names.py
}

final_start_and_check() {
  if [[ "$DEPLOY_MODE" == "docker" ]]; then
    compose up -d xray panel nginx hysteria2
  else
    compose up -d xray panel hysteria2
    if [[ "$DEPLOY_MODE" == "native-nginx" ]]; then
      apply_native_nginx_final
    fi
  fi
  sleep 15
  docker exec xray-proxy-panel python3 /app/enforce_users.py
  sleep 5
  sync_node_exit_names
  docker exec xray-proxy-panel python3 /app/enforce_users.py
  sleep 5

  if [[ "$DEPLOY_MODE" == "internal" ]]; then
    curl -fsS "http://127.0.0.1:9100/login" >/dev/null
    curl -fsS "http://127.0.0.1:9100/assets/app.js" >/dev/null
    curl -fsS "http://127.0.0.1:9100/api/session" >/dev/null
    return
  fi

  local token
  token="$(python3 -c 'import json; print(json.load(open("data/panel/admin_profile.json"))["user"]["sub_token"])')"

  curl -k -fsS "https://$PANEL_DOMAIN/login" >/dev/null
  curl -k -fsS "https://$PANEL_DOMAIN/assets/app.js" >/dev/null
  curl -k -fsS "https://$PANEL_DOMAIN/api/session" >/dev/null
  local count
  count="$(curl -k -fsS "https://$PANEL_DOMAIN/sub/$token/raw" | grep -E '^(vless|hysteria2)://' | wc -l)"
  if [[ "$count" -lt 2 ]]; then
    echo "订阅节点数量异常：$count" >&2
    exit 1
  fi
}

renew_cert_only() {
  if [[ ! -f .env ]]; then
    echo "未找到 .env。请在已安装的项目目录中运行 --renew-cert，或先完整安装一次。" >&2
    exit 1
  fi
  write_env
  init_dirs
  install_docker
  if [[ "$DEPLOY_MODE" == "native-nginx" ]]; then
    install_native_nginx
    write_native_nginx_templates
    apply_native_nginx_http_only
  else
    compose build panel xray
  fi
  issue_cert
  if [[ "$DEPLOY_MODE" == "docker" ]]; then
    compose up -d nginx hysteria2 panel xray
  elif [[ "$DEPLOY_MODE" == "native-nginx" ]]; then
    compose up -d hysteria2 panel xray
    apply_native_nginx_final
  fi
  print_summary
  exit 0
}

print_summary() {
  local bbr
  bbr="$(sysctl -n net.ipv4.tcp_congestion_control 2>/dev/null || true)"
  cat <<EOF

============================================================
部署完成
============================================================
面板地址: https://$PANEL_DOMAIN/login
管理员账号: admin
管理员密码: ${ADMIN_PASS:-见 $APP_DIR/data/DEPLOY-SECRETS.txt}

VLESS 地址: $VLESS_DOMAIN:443
VLESS Reality SNI: $REALITY_SNI
VLESS PublicKey: ${REALITY_PUBLIC_KEY:-见 $APP_DIR/data/DEPLOY-SECRETS.txt}
VLESS ShortID: ${REALITY_SHORT_ID:-见 $APP_DIR/data/DEPLOY-SECRETS.txt}
Hysteria2 域名: $HY2_DOMAIN:$HY2_PORT
BBR: $bbr
部署模式: $DEPLOY_MODE
证书模式: ${CERT_MODE:-unknown}

敏感信息已保存到:
$APP_DIR/data/DEPLOY-SECRETS.txt

入口说明:
  docker 模式       TCP 80/443 由容器 Nginx 接管，UDP 443 由 Hysteria2 接管
  native-nginx 模式 TCP 80/443 由系统 Nginx 接管，UDP 443 由 Hysteria2 接管
  internal 模式     不接管公网 TCP 80/443，仅生成 generated/nginx/ 接入模板

常用命令:
cd $APP_DIR
docker compose ps
docker compose logs --tail=100 panel
docker exec xray-proxy-panel python3 /app/enforce_users.py
============================================================
EOF
  if [[ "${CERT_MODE:-}" == "self-signed" ]]; then
    cat <<EOF

============================================================
证书兜底提示
============================================================
当前使用的是自签证书，不是 Let’s Encrypt 正式证书。
原因: ${CERT_FALLBACK_REASON:-证书申请失败或预启动占位证书仍在使用。}

你现在可以先访问面板，但浏览器会提示证书不受信任:
  https://$PANEL_DOMAIN/login

移动端 Hysteria2 如果需要临时测试，客户端可能需要开启:
  allowInsecure / insecure / 跳过证书验证

等 DNS 生效、Cloudflare 改成「仅 DNS」、TCP 80/443 放通后，执行下面命令补签正式证书:

sudo bash $APP_DIR/scripts/install-fresh-vps.sh --renew-cert \\
  --root-domain $ROOT_DOMAIN \\
  --panel-domain $PANEL_DOMAIN \\
  --hy2-domain $HY2_DOMAIN \\
  --vless-domain $VLESS_DOMAIN \\
  --email $LE_EMAIL \\
  --reality-sni $REALITY_SNI \\
  --hy2-port $HY2_PORT \\
  --mode $DEPLOY_MODE \\
  --yes
============================================================
EOF
  fi
}

parse_args "$@"
need_root
load_existing_env

PUBLIC_IP="$(curl -4sS --connect-timeout 8 https://api.ipify.org || true)"
echo "检测到当前 VPS 公网 IP: ${PUBLIC_IP:-未知}"
echo
echo "请确认 DNS 已解析到本机公网 IP。建议记录："
echo "  panel.example.com  A  ${PUBLIC_IP:-你的VPS IP}"
echo "  hy.example.com     A  ${PUBLIC_IP:-你的VPS IP}"
echo "  vless.example.com  A  ${PUBLIC_IP:-你的VPS IP}"
echo "  example.com        A  ${PUBLIC_IP:-你的VPS IP}"
echo

if [[ "$RENEW_CERT" == "1" && -z "$ROOT_DOMAIN" && -n "$PANEL_DOMAIN" ]]; then
  ROOT_DOMAIN="${PANEL_DOMAIN#*.}"
fi
ask ROOT_DOMAIN "请输入根域名，例如 example.com"
ROOT_DOMAIN="$(normalize_domain "$ROOT_DOMAIN")"
validate_domain "根域名" "$ROOT_DOMAIN"
ask PANEL_DOMAIN "请输入面板域名" "panel.$ROOT_DOMAIN"
ask HY2_DOMAIN "请输入 Hysteria2 域名" "hy.$ROOT_DOMAIN"
ask VLESS_DOMAIN "请输入 VLESS Reality 地址域名" "vless.$ROOT_DOMAIN"
ask LE_EMAIL "请输入 Let’s Encrypt 邮箱" "admin@$ROOT_DOMAIN"
ask REALITY_SNI "请输入 Reality 分流 SNI" "www.cloudflare.com"
ask HY2_PORT "请输入 Hysteria2 UDP 端口" "443"
normalize_and_validate_inputs

if [[ "$RENEW_CERT" == "1" ]]; then
  renew_cert_only
fi

cat <<EOF

请再次确认 DNS：
  $ROOT_DOMAIN -> ${PUBLIC_IP:-你的VPS IP}
  $PANEL_DOMAIN -> ${PUBLIC_IP:-你的VPS IP}
  $HY2_DOMAIN -> ${PUBLIC_IP:-你的VPS IP}
  $VLESS_DOMAIN -> ${PUBLIC_IP:-你的VPS IP}
并确认这些记录是「仅 DNS」，不要开 CDN 代理。

端口说明：
  TCP 443 可由容器 Nginx 或原生 Nginx 接管，用于面板/VLESS 分流。
  UDP $HY2_PORT 默认给 Hysteria2 使用；如果已有其他 UDP $HY2_PORT 服务，请换 --hy2-port。
EOF

preflight_entry_check

if [[ "$AUTO_YES" != "1" ]]; then
  read -r -p "确认以上 DNS、端口和部署模式无误，输入 yes 开始安装: " CONFIRM
  if [[ "$CONFIRM" != "yes" ]]; then
    echo "已取消。"
    exit 1
  fi
else
  echo "已使用 --yes，跳过预检手动确认。"
fi

enable_bbr
configure_docker_dns
install_docker
configure_docker_dns
write_env
init_dirs
xray_keys
write_runtime_json
compile_and_validate
start_for_certbot
issue_cert
generate_hy2_config
final_start_and_check
print_summary
