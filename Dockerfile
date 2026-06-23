ARG XRAY_IMAGE=ghcr.io/xtls/xray-core:latest
FROM ${XRAY_IMAGE} AS xray-source

FROM python:3.12-alpine

RUN set -eux; \
    for repo in \
      https://mirrors.cloud.tencent.com/alpine/v3.23/main \
      https://mirrors.cloud.tencent.com/alpine/v3.23/community \
      https://mirrors.aliyun.com/alpine/v3.23/main \
      https://mirrors.aliyun.com/alpine/v3.23/community \
      https://dl-cdn.alpinelinux.org/alpine/v3.23/main \
      https://dl-cdn.alpinelinux.org/alpine/v3.23/community; do \
      echo "$repo"; \
    done >/etc/apk/repositories; \
    for i in 1 2 3 4 5; do \
      apk add --no-cache ca-certificates curl docker-cli iproute2 tzdata util-linux wireguard-tools && break; \
      if [ "$i" = "5" ]; then exit 1; fi; \
      sleep 3; \
    done; \
    mkdir -p /app /data/panel /data/xray /data/hysteria2 /data/backups /usr/local/share/xray /var/log/xray; \
    addgroup -S panel; \
    adduser -S -G panel panel

COPY --from=xray-source / /tmp/xray-root

RUN set -eux; \
    xray_src="$(find /tmp/xray-root -type f -name xray | head -n 1)"; \
    if [ -z "$xray_src" ]; then echo "xray binary not found in XRAY_IMAGE" >&2; exit 1; fi; \
    install -m 755 "$xray_src" /usr/local/bin/xray; \
    for asset in geoip.dat geosite.dat; do \
      asset_src="$(find /tmp/xray-root -type f -name "$asset" | head -n 1)"; \
      if [ -n "$asset_src" ]; then cp "$asset_src" "/usr/local/share/xray/$asset"; fi; \
    done; \
    rm -rf /tmp/xray-root

WORKDIR /app
COPY baseline/ /app/
COPY requirements.txt /app/requirements.txt

RUN python3 -m pip install --no-cache-dir -r /app/requirements.txt

RUN find /app -name "__pycache__" -type d -prune -exec rm -rf {} + \
    && chmod +x /app/enforce_users.py /app/quota_collect.py

ENV PYTHONUNBUFFERED=1 \
    XRAY_LOCATION_ASSET=/usr/local/share/xray \
    PANEL_APP_DIR=/app

EXPOSE 9100

HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:9100/login', timeout=4).read()" >/dev/null || exit 1

CMD ["python3", "/app/panel.py"]
