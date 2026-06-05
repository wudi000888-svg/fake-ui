# 更新日志

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
