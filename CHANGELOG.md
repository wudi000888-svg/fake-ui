# 更新日志

## v3.0.1

| 类型 | 内容 |
| --- | --- |
| 配对 Agent | 新增 dedicated/shared 内网穿透配对 Agent 包，面板生成短期一次性 token，本地后端首次运行时主动 bootstrap 拉取配置 |
| 本地客户端 | `bootstrap-agent.py` 会写入 `xray-bridge.json`、`bridge-dashboard.json` 和 `agent-state.json`，成功后清空 `agent-profile.json` 中的 token |
| 本地控制台 | Bridge dashboard 升级为 fake-ui 风格本地应用，保留 `127.0.0.1:19090` local-only 边界，并展示 runtime、服务、setup、日志和状态 API |
| 安全 | 配对 token 只 hash 存储；dashboard 渲染日志和配置预览时脱敏 UUID、Reality key、short ID 和 pairing token |
| 兼容 | 原有静态安装包、JSON 导出和共享 Agent 流程保留；面板按钮区分配对 Agent 和手动静态包 |

## v3.0.0

| 类型 | 内容 |
| --- | --- |
| 内网穿透 | 新增通用内网穿透管理页，支持任意客户域名映射到 macOS、Linux 或 Windows 后端本地服务，不再绑定固定域名后缀 |
| 自动化 | 面板保存穿透节点时自动分配 portal 端口、生成独立 UUID、email、portal tag 和 reverse tag，并校验与普通代理用户 UUID 不复用 |
| VPS | 应用穿透时自动更新 Xray Reality portal 配置、生成 Nginx HTTP/HTTPS 反代、通过 certbot 签发域名证书并 reload Nginx |
| 后端 Agent | 每个服务可导出 macOS launchd、Linux systemd 或 Windows Scheduled Task 安装包，包含 Xray 配置、安装、卸载和状态检查脚本 |
| 高级模式 | 支持“单机器共享 bridge”，同一后端机器上的多个服务可以合并到一个 Xray Agent 进程，SSH 等救援入口仍可保持独立 |
| 架构 | 默认采用单服务单 bridge 模式，普通代理用户继续使用 `panel-user:<username>`，穿透 bridge 使用 `tunnel:<id>` |
| 升级 | 应用穿透配置时会自动禁用旧版 `fake-ui-tunnel-*.conf` 单域名 Nginx 配置，避免旧 upstream 抢占新域名导致 502 |

## v2.3.1

| 类型 | 内容 |
| --- | --- |
| 部署 | Docker daemon 默认 DNS 从国内解析器改为 `1.1.1.1`、`8.8.8.8`、`9.9.9.9` 和 `208.67.222.222`，降低容器内节点解析被 DNS 污染影响的概率 |
| 部署 | 安装脚本、Docker Compose 默认版本、Windows 部署脚本和前端兜底版本号更新为 `v2.3.1` |
| 升级 | 从 v2.3.0 直接升级无需数据库迁移；如旧服务器已生成 `/etc/docker/daemon.json`，重新运行安装/部署流程会写入新的容器 DNS 并重启 Docker |

## v2.3.0

| 类型 | 内容 |
| --- | --- |
| 账号 | 已登录普通用户可在用户中心修改自己的面板登录密码，后端校验当前密码并继续使用 PBKDF2-SHA256 存储 |
| 账号 | 管理员可在系统设置页修改当前管理员登录密码，不需要直接改 `.env` 或认证文件 |
| 前端 | 登录后的账号入口改为头像菜单，保留个人资料、订阅管理和退出登录入口 |
| 桌面端 | 侧边栏底部从“退出”改为“收起/展开”控制，支持收起为 88px 图标栏 |
| 移动端 | 移除移动底部导航，改为顶部菜单按钮和侧边抽屉，避免小屏底部遮挡内容 |
| 移动端 | 修复窗口缩小后侧边栏“收起”按钮失效的问题，小屏下点击会关闭抽屉，桌面下点击才折叠侧栏 |
| 布局 | 修复 319px 等窄屏横向溢出，侧栏、顶部栏、账号菜单和主内容宽度在移动端保持稳定 |
| 测试 | 增加前端结构回归测试，覆盖移动抽屉、账号菜单、侧栏折叠、无底部导航和自助改密入口 |
| 升级 | 从 v2.2.0 直接升级无需数据库迁移；运行态 `.env`、`data/` 和 `generated/` 继续保留在服务器 |

## v2.2.0

| 类型 | 内容 |
| --- | --- |
| 管理端 | 管理首页升级为商业运营仪表盘，新增用户、流量、节点、订单和面板状态指标卡 |
| 可视化 | 新增前端 Canvas 折线图和环形图，展示近 24 小时流量趋势、套餐分布、用户流量排行和节点流量分布 |
| 数据 | SQLite 新增 `traffic_samples` 表和聚合 repository，用于保存 Xray/Hysteria2 采集样本，并默认保留 90 天样本 |
| API | 新增管理员指标接口：overview、traffic、top users、nodes、plans，并接入 `/api/dashboard` |
| 采集 | 配额采集同步写入流量样本；指标暂时不可用时不再清零已有 baseline，避免恢复后重复计量 |
| 用户 | 管理员用户列表展示今日流量、剩余额度和流量进度条，便于快速识别高消耗账号 |
| 前端 | 图表失败降级为空态；已登录启动失败显示重试/退出恢复页，避免半初始化界面 |
| 安全 | 移除旧的公开 `/api/password-reset/request`；登录和订阅限速只信任可信反代转发 IP |
| 备份 | 备份恢复先写入 staging 并校验 SQLite，损坏数据库备份不会覆盖当前有效库 |
| 部署 | 新增安全打包脚本，排除运行态敏感目录；默认镜像固定版本，静态资源缓存头完善 |
| 升级 | 从 v2.1.2 直接升级会自动创建新表，不需要导入旧备份 |

## v2.1.2

| 类型 | 内容 |
| --- | --- |
| 安全 | 修复 `/qr/` 管理员节点二维码未鉴权问题，非管理员无法生成管理员订阅节点二维码 |
| 安全 | `/api/login` 统一使用登录限速和审计，避免绕过页面登录保护 |
| 安全 | 注册申请不再把用户密码明文写入 SQLite，审批时使用已保存的 PBKDF2 hash 创建用户 |
| 注册 | 新增管理员可控的公开注册开关；开启后用户可自助注册，注册成功后返回登录页，默认无套餐、无节点权限 |
| 账号 | 登录页与注册页拆分；注册关闭时登录页不显示注册入口，开启时显示注册按钮 |
| 账号 | 新增管理员可控的邮箱验证码找回密码，支持 SMTP 服务商配置，SMTP 密码不在 API 响应中回显 |
| 账号 | 用户中心支持补充邮箱，管理员和用户 shell 均提供退出登录按钮 |
| 账号 | 修复旧 session/CSRF 状态下公开注册被拦截、注册后不跳转和登录后短暂空白的问题 |
| 用户 | 修复 SQLite-only 数据层中删除用户只写审计但用户记录仍保留的问题 |
| 套餐 | 修复套餐改名后管理员用户列表仍显示旧套餐名或套餐 ID 的问题 |
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
