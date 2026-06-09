# 更新日志

## v2.1.2

| 类型 | 内容 |
| --- | --- |
| 安全 | 修复 `/qr/` 管理员节点二维码未鉴权问题，非管理员无法生成管理员订阅节点二维码 |
| 安全 | `/api/login` 统一使用登录限速和审计，避免绕过页面登录保护 |
| 安全 | 注册申请不再把用户密码明文写入 SQLite，审批时使用已保存的 PBKDF2 hash 创建用户 |
| 部署 | 原生 Nginx 安装配置补齐 HSTS、nosniff、X-Frame-Options、Referrer-Policy 和 Permissions-Policy |
| 备份 | 备份恢复增加归档大小限制、SQLite integrity check，并将恢复后的数据库文件权限收敛为 `0600` |
| 文档 | 更新架构文档到当前 SQLite repository、`security.py` 和路由结构 |

## v2.1.1

| 类型 | 内容 |
| --- | --- |
| 安全 | 面板 session cookie 增加 `Secure`，继续保留 `HttpOnly` 和 `SameSite=Lax` |
| 安全 | 已登录 API 写操作要求 `X-CSRF-Token`，旧版不含 CSRF 的 session 直接失效并要求重新登录 |
| 安全 | 登录失败增加 IP+用户名维度限速，并把成功、失败、限速事件写入审计日志 |
| 安全 | Python 面板和 Nginx 模板补充安全响应头，包括 HSTS、CSP、X-Frame-Options、nosniff、Referrer-Policy 和 Permissions-Policy |
| 前端 | 登录/session 响应自动保存 CSRF Token，后续非 GET API 请求自动携带 |
| 文档 | 更新 SECURITY 和发布说明，明确生产环境仍需 HTTPS、反代安全头、备份加密和最小权限部署 |

## v2.1.0

| 类型 | 内容 |
| --- | --- |
| 数据 | 业务数据切换为 SQLite-only，移除 `FAKE_UI_STORE` 运行开关和旧 JSON fallback |
| 数据 | 删除 JSON 导入 SQLite、SQLite 回导 JSON 两个过渡脚本，v2.1.0 仅支持从 v2.0.1 的 SQLite 数据库继续升级 |
| 仓储 | 用户、套餐、订单、节点、注册审核、管理员资料、链接设置、支付方式和支付记录统一通过 SQLite repository 读写 |
| 订阅 | 修复已有用户购买不同套餐时被当作续费叠加的问题；不同套餐订单确认后会覆盖套餐、到期、额度和节点权限 |
| 备份 | 面板备份改为包含 `fake-ui.db`、WAL/SHM、认证文件和日志，不再把旧业务 JSON 当运行数据 |
| 部署 | 安装脚本和 Windows Compose 部署脚本直接初始化 SQLite，不再生成旧业务 JSON 后再迁移 |
| 文档 | README、安全说明和运维检查更新为 v2.1.0 SQLite-only 口径 |

## v2.0.1

| 类型 | 内容 |
| --- | --- |
| Hysteria2 | 恢复独立管理页，支持 HTTP/SOCKS5 出口配置、恢复直连、状态与日志展示 |
| 节点 | 修复节点编辑/刷新后前端不回填的问题，后端返回的出口 IP、国家和节点名称会立即同步到列表 |
| 前端 | 移动端底部导航纳入 Hysteria2、备份、审计等二级入口，GitHub 截图更新到最新 v2 状态 |
| 测试 | 修复 CI 中测试访问 `/root` 运行日志导致的权限失败，测试 fixture 改为临时目录隔离 |
| 部署 | 在新加坡 VPS 完成最新版安装验证，确认 Panel、Nginx、Xray Reality、Hysteria2 和静态资源正常 |
| 发布 | 新增 v2.0.1 Release notes，并打包 GitHub Release 源码归档 |

## v2.0.0

| 类型 | 内容 |
| --- | --- |
| 前端 | 重构为 ES modules，新增移动优先 shell、底部导航、用户订单/付款分区和管理员卡片化运营页 |
| 数据 | 新增 SQLite schema、repository、JSON 导入、SQLite 导出回 JSON 和 `FAKE_UI_STORE=sqlite` 可切换运行模式 |
| 缓存 | 新增线程安全 TTL cache，并提供管理员缓存状态和清理 API |
| 测试 | 新增 v2 API、数据库、缓存、前端结构和 demo 数据一致性测试 |
| 部署 | 新增新加坡测试环境破坏性重置脚本，默认拒绝执行，需显式 `FAKE_UI_ALLOW_TEST_RESET=singapore` |
| 文档 | 更新 README 首屏定位，标明 v2.0.0 商业化移动端、SQLite 和缓存能力 |

## v1.2.0

| 类型 | 内容 |
| --- | --- |
| 支付 | 增加加密货币收款模块，支持 USDT、USDC、ETH、BNB、BTC |
| 支付 | 套餐订单保持 USD 计价，付款金额按创建订单时锁定 |
| 支付 | 管理员只需配置收款地址，内置 EVM/BTC 默认链参数和公共查询端点 |
| 支付 | 支持二维码付款、TXID 兜底、自动链上验账和到账后自动开通/续费 |
| 支付 | EVM 自动扫账支持 RPC 失败切换、日志分段、自适应缩小查询区间和最小安全回看窗口 |
| 订单 | 用户侧订单按待付款、需要补 TXID、历史订单分区展示 |
| 管理 | 管理员支付记录使用管理语义，取消/完成订单不再显示客户付款动作 |
| 安全 | 支付模块不保存钱包私钥或助记词，只保存收款地址和链上查询配置 |
| 部署 | 增加 Windows 安全 Compose 部署脚本，避免 PowerShell/SSH 引号污染远端命令 |

## v1.1.0

| 类型 | 内容 |
| --- | --- |
| 开源化 | 增加 README、LICENSE、SECURITY、CONTRIBUTING 和 GitHub CI |
| 产品化 | 增加架构文档、运维手册、生产环境模板 |
| 安全 | 默认域名改为 `example.com` 占位，生产环境通过环境变量覆盖 |
| 工具 | 增加 Windows 和 Bash 本地测试脚本 |
