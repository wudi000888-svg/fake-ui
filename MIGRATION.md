# Docker Compose 无损迁移说明

这套 Compose 方案把服务拆成四个容器：`panel`、`xray`、`hysteria2`、`nginx`。运行数据全部落在 `data/`，迁移时只需要搬项目目录和导出的状态包。

## 数据边界

| 目录/文件 | 作用 | 是否含敏感信息 |
|---|---|---|
| `data/panel` | 管理员、用户、套餐、订单、订阅 token、审计日志 | 是 |
| `data/xray/config.json` | Xray Reality 入站、路由、用户 UUID、出口节点配置 | 是 |
| `data/hysteria2/.env` | Hysteria2 域名、管理员密码等 | 是 |
| `data/hysteria2/server.yaml` | Hysteria2 用户、TLS、出站代理、流量统计配置 | 是 |
| `data/letsencrypt` | TLS 证书和续签记录 | 是 |
| `data/backups` | 面板自动回滚备份 | 是 |

## 从现有 VPS 导出

在当前 VPS 上进入项目目录或上传本项目后执行：

```bash
sudo bash scripts/export-live-data.sh
```

脚本会生成类似：

```bash
/root/xray-proxy-panel-compose-state-YYYYMMDD-HHMMSS.tgz
```

这个包包含用户、节点、订阅、Xray、Hysteria2、证书和当前 Nginx/Systemd 快照。权限默认 `600`，不要发到公开仓库。

## 在新 VPS 导入

```bash
git clone <your-repo> /opt/xray-proxy-panel-compose
cd /opt/xray-proxy-panel-compose
bash scripts/init-compose-data.sh
bash scripts/import-compose-data.sh /root/xray-proxy-panel-compose-state-xxxx.tgz
cp .env.example .env
```

检查 `.env`：

```bash
PANEL_DOMAIN=panel.example.com
HY2_DOMAIN=hy2.example.com
REALITY_SNI=www.cloudflare.com
XRAY_REALITY_PORT=8443
XRAY_IMAGE=ghcr.io/xtls/xray-core:latest
```

做静态测试：

```bash
bash scripts/smoke-test.sh
```

如果没有证书，先启动 Nginx 的 80 端口或使用已有证书，再执行：

```bash
docker compose --profile certbot run --rm certbot
```

## 同一台 VPS 切换到 Compose

同机切换需要维护窗口，因为旧服务和新容器会抢 `80/tcp`、`443/tcp`、`443/udp`、`9100/tcp`。

```bash
cd /opt/xray-proxy-panel-compose
bash scripts/smoke-test.sh

systemctl stop nginx xray xray-proxy-panel
docker compose -f /opt/hysteria2/docker-compose.yml down

START_STACK=1 bash scripts/smoke-test.sh
docker compose ps
```

确认面板、VLESS、Hysteria2、订阅都正常后，再禁用旧 systemd：

```bash
systemctl disable nginx xray xray-proxy-panel
```

## 回滚

如果切换后异常：

```bash
cd /opt/xray-proxy-panel-compose
docker compose down

systemctl start xray xray-proxy-panel nginx
docker compose -f /opt/hysteria2/docker-compose.yml up -d
```

## 证书续签

Compose 已提供 `certbot-renew`，可以用宿主机 cron 定期跑：

```bash
0 3 * * * cd /opt/xray-proxy-panel-compose && docker compose --profile certbot run --rm certbot-renew && docker restart xray-proxy-nginx hysteria2
```
