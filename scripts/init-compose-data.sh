#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

mkdir -p \
  data/panel \
  data/xray/log \
  data/hysteria2 \
  data/letsencrypt \
  data/acme \
  data/nginx/log \
  data/backups/xray \
  data/backups/hysteria2

if [[ ! -f .env ]]; then
  cp .env.example .env
fi

cat > data/README.md <<'EOF'
# Runtime data

This directory is intentionally ignored by git.

Import a migration bundle with:

```bash
scripts/import-compose-data.sh /path/to/xray-proxy-panel-compose-state.tgz
```

The compose stack expects at least:

- data/panel/*.json and login/token files
- data/xray/config.json
- data/hysteria2/.env
- data/hysteria2/server.yaml
- data/letsencrypt/live/<domain>/fullchain.pem
EOF

echo "Compose data directories are ready under: $ROOT_DIR/data"
echo "Edit .env, then import an existing bundle or provide configs before starting the stack."

