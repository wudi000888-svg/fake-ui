#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -f .env ]]; then
  cp .env.example .env
fi

required=(
  data/xray/config.json
  data/hysteria2/.env
  data/hysteria2/server.yaml
)

for f in "${required[@]}"; do
  if [[ ! -f "$f" ]]; then
    echo "Missing required runtime file: $f" >&2
    exit 1
  fi
done

docker compose config >/dev/null
docker compose build panel xray >/dev/null
docker compose run --rm --no-deps panel sh -c 'python3 -m py_compile /app/*.py' >/dev/null
docker compose run --rm --no-deps panel xray run -test -config /data/xray/config.json >/dev/null

if [[ "${START_STACK:-0}" == "1" ]]; then
  docker compose up -d
  sleep 5
  docker compose ps
  curl -fsS http://127.0.0.1:9100/login >/dev/null
  docker exec xray-proxy-panel python3 /app/enforce_users.py >/dev/null
  echo "Stack started and panel/enforce smoke checks passed."
else
  echo "Static compose checks passed. Set START_STACK=1 only during a cutover window to start services."
fi
