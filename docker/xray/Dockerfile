ARG XRAY_IMAGE=ghcr.io/xtls/xray-core:latest
FROM ${XRAY_IMAGE} AS xray-source

FROM alpine:3.20

RUN mkdir -p /usr/local/share/xray /etc/xray /var/log/xray

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

ENV XRAY_LOCATION_ASSET=/usr/local/share/xray

ENTRYPOINT ["xray"]
CMD ["run", "-config", "/etc/xray/config.json"]
