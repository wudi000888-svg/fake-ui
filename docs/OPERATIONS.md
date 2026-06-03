# 运维手册

## 本地测试

| 检查 | 命令 |
| --- | --- |
| 编译全部 Python 文件 | `bash scripts/test-local.sh` 或 `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-local.ps1` |
| 单元测试 | `python -m pytest -q` |
| PowerShell 一键测试 | `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-local.ps1` |
| Bash 一键测试 | `bash scripts/test-local.sh` |

## Docker Compose 部署流程

全新 VPS 推荐直接运行：

```bash
sudo bash scripts/install-fresh-vps.sh
```

运行前请先把脚本提示的域名 A 记录解析到 VPS 公网 IP，并关闭 CDN/代理模式。

1. 复制配置模板：

```bash
cp .env.example .env
```

2. 修改 `.env` 中的域名、邮箱、端口、证书和服务参数。

3. 启动：

```bash
docker compose up -d --build
```

4. 查看状态：

```bash
docker compose ps
docker compose logs --tail=100 panel
```

## 生产上线检查

| 阶段 | 检查项 |
| --- | --- |
| 上线前 | 备份面板目录、Xray 配置、Hysteria2 配置 |
| 上线前 | 远端 `bash scripts/test-local.sh` |
| 上线前 | 远端 `python3 -m pytest -q` |
| 上线前 | 临时端口启动面板，测试 `/login`、`/api/session`、`/api/users`、`/api/nodes` |
| 上线 | 重启 `xray-proxy-panel` |
| 上线后 | 检查面板 HTTPS、Xray active、Hysteria2 running |

## 生产环境变量

开源仓库默认使用 `example.com` 占位值。生产环境必须覆盖：

| 变量 | 说明 |
| --- | --- |
| `PANEL_DOMAIN` | 面板域名 |
| `HY2_DOMAIN` | Hysteria2 域名 |
| `PUBLIC_BASE_URL` | 面板公开访问地址 |
| `DEFAULT_VLESS_ADDRESS` | 默认 VLESS 地址 |
| `DEFAULT_VLESS_NAME` | 默认 VLESS 节点名 |
| `DEFAULT_HY2_NAME` | 默认 Hysteria2 节点名 |
| `HY2_MASQUERADE_URL` | Hysteria2 伪装站点 |

systemd 部署时建议使用 override 文件注入环境变量，避免把生产域名写死到代码。

## 回滚策略

| 对象 | 回滚方式 |
| --- | --- |
| 面板代码 | 从上线前 tar 备份恢复项目目录 |
| Xray 配置 | 使用 `XRAY_BACKUP_DIR` 中最近的配置恢复 |
| Hysteria2 配置 | 使用 `HY2_BACKUP_DIR` 中最近的配置恢复 |
| Docker Compose 状态 | 使用 `scripts/import-compose-data.sh` 导入导出的状态包 |
