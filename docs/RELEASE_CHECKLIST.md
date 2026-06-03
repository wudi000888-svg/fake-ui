# 发布检查清单

## 开源发布前

| 状态 | 检查项 |
| --- | --- |
| [ ] | `rg -n "真实域名|真实账号|真实密码|私钥|token" .` 无敏感信息 |
| [ ] | `data/`、`.env`、证书、迁移包未进入 Git |
| [ ] | `bash scripts/test-local.sh` 或 `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-local.ps1` 通过 |
| [ ] | `python -m pytest -q` 通过 |
| [ ] | README、MIGRATION、SECURITY、CONTRIBUTING 可读 |
| [ ] | `.env.example` 和 `.env.production.example` 只包含占位值 |

## 生产上线前

| 状态 | 检查项 |
| --- | --- |
| [ ] | 已备份面板目录、Xray 配置、Hysteria2 配置 |
| [ ] | systemd 或 `.env` 已写入真实生产域名 |
| [ ] | 临时端口启动面板并测试 `/login`、`/api/session`、`/api/users`、`/api/nodes` |
| [ ] | Xray 配置校验通过 |
| [ ] | Hysteria2 配置校验通过 |
| [ ] | 重启后面板、Xray、Hysteria2 状态正常 |
