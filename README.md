# 虚假机场

一个轻量的代理管理面板，用于管理 VLESS Reality、Hysteria2、用户、套餐、订单、订阅、节点出口和流量限制。

> 本仓库不包含运行态数据、证书、真实域名、用户密码、订阅 token 或服务端私钥。所有运行数据都应放在 `data/` 或服务器环境变量中。

## 适合谁

| 场景 | 说明 |
|---|---|
| 单台 VPS 运营 | 支持一台机器编排多个 VLESS/Hysteria2 节点 |
| 多出口实验 | VLESS 节点可切换直连、HTTP 上游、SOCKS5 上游 |
| 轻量面板 | JSON 存储，无需数据库，适合小规模自托管 |
| 原生 Nginx 共存 | 支持自动检测原生 Nginx，并通过 SNI 分流共用 TCP 443 |

## 端口模型

| 入口 | 默认归属 | 说明 |
|---|---|---|
| TCP 80 | Nginx | HTTP 跳转和 ACME 证书验证 |
| TCP 443 | Nginx stream | 面板 HTTPS / VLESS Reality SNI 分流 |
| UDP 443 | Hysteria2 | Hysteria2 节点入口 |
| 127.0.0.1:9100 | Panel | 面板后端 |
| 127.0.0.1:10000 | Nginx | 面板本地 HTTPS |
| 8443 | Xray | VLESS Reality 内部入口 |

## 功能

| 功能 | 说明 |
|---|---|
| 用户管理 | 创建、禁用、续期、限额、重置订阅 |
| 节点管理 | 多 VLESS 节点、Hysteria2 节点、出口 IP/国家展示 |
| 出口编排 | VLESS 支持直连、HTTP 上游、SOCKS5 上游 |
| 订阅 | 通用 base64、raw URI、Mihomo/Clash.Meta |
| 运营 | 套餐、订单、注册审核、找回密码、审计日志 |
| 安全 | JSON 原子写入、配置校验、失败回滚、订阅访问限流 |
| 部署 | 支持宿主机运行，也提供 Docker Compose 迁移方案 |

## 项目结构

| 路径 | 说明 |
|---|---|
| `baseline/panel.py` | 服务入口 |
| `baseline/web_handler.py` | HTTP 总分发 |
| `baseline/http_*_routes.py` | HTTP 路由层 |
| `baseline/api*.py` | API 路由和权限层 |
| `baseline/xray_*` | Xray 配置生成、校验、重启、状态 |
| `baseline/hy2_*` | Hysteria2 配置生成、重启、状态 |
| `baseline/*_store.py` | JSON 数据存储 |
| `baseline/frontend/` | 前端 SPA 静态资源 |
| `tests/` | pytest 回归测试 |
| `docker/` | Nginx/Xray 容器模板 |
| `scripts/` | 初始化、迁移、测试脚本 |
| `data/` | 运行态数据，已 gitignore |

## 快速开始

全新 VPS 一键部署：

```bash
sudo bash scripts/install-fresh-vps.sh
```

脚本会提示填写根域名、面板域名、Hysteria2 域名、VLESS 域名和证书邮箱，并自动启用 BBR、生成运行态、签发证书、启动 Docker Compose，最后输出管理员账号密码。

也可以提前传入域名参数，适合重装系统后直接复刻：

```bash
sudo bash scripts/install-fresh-vps.sh \
  --root-domain example.com \
  --panel-domain panel.example.com \
  --hy2-domain hy.example.com \
  --vless-domain vless.example.com \
  --email admin@example.com \
  --reality-sni www.cloudflare.com
```

如果 DNS 已确认解析完成，可以追加 `--yes` 跳过二次确认。

部署模式：

| 模式 | 命令参数 | 说明 |
|---|---|---|
| Docker 入口 | `--mode docker` | 默认模式，容器 Nginx 接管 TCP 80/443，Hysteria2 接管 UDP 443 |
| 原生 Nginx 入口 | `--mode native-nginx` | 系统 Nginx 接管 TCP 80/443，Docker 只跑面板、Xray、Hysteria2 |
| 内部服务 | `--mode internal` | 不接管公网 TCP 80/443，只启动内部服务并生成 `generated/nginx/` 接入模板 |

如果原生 Nginx 已经有 HTTPS 站点，必须确认 443 分流方式后再使用：

```bash
sudo bash scripts/install-fresh-vps.sh \
  --mode native-nginx \
  --allow-nginx-443-rewrite \
  --root-domain example.com \
  --panel-domain panel.example.com \
  --hy2-domain hy.example.com \
  --vless-domain vless.example.com \
  --email admin@example.com
```

兼容原生 Nginx 时，TCP 443 可以由系统 Nginx 的 `stream ssl_preread` 分流；UDP 443 仍由 Hysteria2 使用，不能与其他 UDP 443 服务共享。

如果脚本检测到原生 Nginx 已经占用 TCP 443，会提示并自动优先使用 `native-nginx` 兼容方式；Hysteria2 仍默认使用 UDP 443。只有当 UDP 443 也被占用时，才需要改 Hysteria2 端口：

```bash
sudo bash scripts/install-fresh-vps.sh \
  --mode native-nginx \
  --hy2-port 8443 \
  --root-domain example.com \
  --panel-domain panel.example.com \
  --hy2-domain hy.example.com \
  --vless-domain vless.example.com \
  --email admin@example.com
```

```bash
cp .env.example .env
bash scripts/init-compose-data.sh
# 导入已有运行态数据，或手动准备 data/xray/config.json 和 data/hysteria2/server.yaml
bash scripts/import-compose-data.sh /path/to/state.tgz
bash scripts/smoke-test.sh
```

生产部署前请把 `.env.production.example` 复制为 `.env`，并用自己的域名、证书路径和服务命令覆盖占位值。

## 本地测试

```bash
python -m pytest -q
bash scripts/test-local.sh
```

Windows 可以直接运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-local.ps1
```

## 重要安全说明

| 内容 | 处理方式 |
|---|---|
| `.env` | 不提交 |
| `data/` | 不提交 |
| 证书和私钥 | 不提交 |
| 用户数据和订阅 token | 不提交 |
| 导出的迁移包 | 不提交 |

## 迁移

详见 [MIGRATION.md](MIGRATION.md)。

## 更多文档

| 文档 | 内容 |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 模块边界和请求流 |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | 本地测试、Docker、生产上线检查 |
| [SECURITY.md](SECURITY.md) | 敏感信息和安全建议 |
| [CONTRIBUTING.md](CONTRIBUTING.md) | 贡献和测试规范 |
