# 贡献指南

感谢你愿意参与这个项目。为了让面板长期可维护，请按下面的方式提交改动。

## 本地检查

提交前至少运行：

```bash
python -m pytest -q
bash scripts/test-local.sh
```

Windows 用户也可以运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-local.ps1
```

## 代码边界

| 目录/模块 | 说明 |
| --- | --- |
| `baseline/http_*.py` | 页面和 API 路由，不直接写 Xray/HY2 配置 |
| `baseline/api_*.py` | 管理端和用户端 API 逻辑 |
| `baseline/xray_*.py` | Xray 配置生成、校验、重启、回滚 |
| `baseline/hy2_*.py` | Hysteria2 配置生成、校验、重启、回滚 |
| `baseline/subscription_*.py` | 订阅、二维码、客户端格式输出 |
| `tests/` | 回归测试，新增功能需要补对应测试 |

## 提交流程

1. 先开 Issue 或在说明里写清楚变更目标。
2. 保持改动小而清晰，避免把重构和功能混在一个提交里。
3. 不提交真实运行数据、密钥、域名、代理账号。
4. 涉及配置写入和服务重启的改动，必须说明失败回滚路径。
