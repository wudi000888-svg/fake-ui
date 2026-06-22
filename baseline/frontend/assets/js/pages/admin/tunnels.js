import { esc } from "../../components/layout.js?v=3.0.1";


function matchesTunnel(tunnel, query) {
  if (!query) return true;
  const haystack = [
    tunnel.id,
    tunnel.name,
    tunnel.display_name,
    tunnel.portal,
    tunnel.target,
    tunnel.reality_sni,
    tunnel.server_address,
    tunnel.public_domain,
    tunnel.bridge_id,
    tunnel.bridge_platform,
  ].join(" ").toLowerCase();
  return haystack.includes(query.toLowerCase());
}


function platformLabel(platform) {
  return { macos: "macOS", linux: "Linux", windows: "Windows" }[platform] || platform || "macOS";
}


function agentKey(tunnel) {
  if (tunnel.bridge_mode === "shared") return `shared:${tunnel.bridge_id || "default"}`;
  return `dedicated:${tunnel.id}`;
}


function serviceCountLabel(count) {
  return `${count} 个服务映射`;
}


function domainOptionsMarkup(domainOptions = {}) {
  const available = domainOptions.available || [];
  return available.map((item) => `<option value="${esc(item.domain || "")}"></option>`).join("");
}


function domainStatusCard(domainOptions = {}) {
  const available = domainOptions.available || [];
  const unavailable = domainOptions.unavailable || [];
  const hidden = unavailable.slice(0, 5).map((item) => `${item.domain}：${domainReasonLabel(item.reason)}`).join("；");
  return `
    <div class="tunnel-domain-status" data-domain-options>
      <strong>可用域名：${available.length}</strong>
      <span>${available.length ? "只显示已解析到本服务器且未被面板/节点占用的域名。" : "先把子域名 A/AAAA 解析到本 VPS，再刷新页面。"}</span>
      ${hidden ? `<small>已隐藏：${esc(hidden)}</small>` : ""}
    </div>
  `;
}


function domainReasonLabel(reason) {
  return {
    reserved_panel_domain: "面板域名",
    reserved_node_domain: "普通节点域名",
    already_used_by_tunnel: "已被穿透使用",
    not_resolved_to_server: "未解析到本服务器",
    invalid_domain: "域名无效",
  }[reason] || "不可用";
}


function uniqueSharedAgents(tunnels) {
  const seen = new Set();
  const agents = [];
  for (const tunnel of tunnels) {
    if (tunnel.bridge_mode !== "shared") continue;
    const key = agentKey(tunnel);
    if (seen.has(key)) continue;
    seen.add(key);
    const services = tunnels.filter((item) => item.bridge_mode === "shared" && agentKey(item) === key);
    agents.push({ tunnel, services });
  }
  return agents;
}


function sharedAgentCards(tunnels) {
  return uniqueSharedAgents(tunnels).map(({ tunnel, services }) => {
    const bridgeId = tunnel.bridge_id || "default";
    const platform = tunnel.bridge_platform || "macos";
    const serviceNames = services.map((item) => item.public_domain || item.display_name || item.name || item.id).join("、");
    return `
      <article class="admin-card tunnel-agent-card">
        <div>
          <strong>共享后端客户端：${esc(bridgeId)}</strong>
          <span>${esc(platformLabel(platform))} · ${serviceCountLabel(services.length)} · 一个后端客户端可以承载多个服务</span>
        </div>
        <p>安装一次后，${esc(serviceNames || "这些服务")} 都会通过这个客户端回连 VPS。新增同一 Bridge ID 的服务时，通常不需要重新安装客户端。</p>
        <div class="admin-actions">
          <button class="secondary" data-action="tunnel-shared-agent-config-export" data-bridge="${esc(bridgeId)}" type="button">导出总 JSON</button>
          <button class="primary" data-action="tunnel-shared-agent-bundle-export" data-bridge="${esc(bridgeId)}" data-platform="${esc(platform)}" type="button">下载配对安装包</button>
        </div>
      </article>
    `;
  }).join("");
}


function dedicatedAgentCards(tunnels) {
  return tunnels.filter((tunnel) => tunnel.bridge_mode !== "shared").map((tunnel) => {
    const platform = tunnel.bridge_platform || "macos";
    return `
      <article class="admin-card tunnel-agent-card">
        <div>
          <strong>独立后端客户端：${esc(tunnel.display_name || tunnel.name || tunnel.id)}</strong>
          <span>${esc(platformLabel(platform))} · 只服务这一条映射</span>
        </div>
        <p>适合 SSH、数据库或需要单独隔离的服务。下载一个配对安装包，在后端机器运行安装脚本即可自动拉取配置。</p>
        <div class="admin-actions">
          <button class="secondary" data-action="tunnel-agent-config-export" data-tunnel="${esc(tunnel.id)}" type="button">导出总 JSON</button>
          <button class="primary" data-action="tunnel-agent-bundle-export" data-tunnel="${esc(tunnel.id)}" data-platform="${esc(platform)}" type="button">下载配对安装包</button>
        </div>
      </article>
    `;
  }).join("");
}


function serviceCard(tunnel) {
  const bridgeMode = tunnel.bridge_mode === "shared" ? `共享 Agent ${tunnel.bridge_id || "default"}` : "独立 Agent";
  const status = tunnel.enabled === false ? "停用" : "在线";
  const domainLabel = tunnel.kind === "private_tcp" ? "TCP 无需域名" : (tunnel.public_domain || "未配置域名");
  return `
    <article class="admin-card node-admin-card tunnel-service-card">
      <div>
        <strong>${esc(tunnel.display_name || tunnel.name || tunnel.id)}</strong>
        <span>${esc(tunnel.portal || "")} -> ${esc(tunnel.target || "")} · ${status}</span>
      </div>
      <p>${esc(domainLabel)} · ${esc(tunnel.server_address || "")}:${esc(tunnel.server_port || "443")} · SNI ${esc(tunnel.reality_sni || "www.cloudflare.com")} · ${esc(bridgeMode)}</p>
      <div class="admin-actions">
        <button class="secondary" data-action="tunnel-edit" data-tunnel="${esc(tunnel.id)}" type="button">编辑</button>
        <button class="secondary" data-action="tunnel-action" data-tunnel="${esc(tunnel.id)}" data-tunnel-action="${tunnel.enabled === false ? "enable" : "disable"}" type="button">${tunnel.enabled === false ? "启用" : "停用"}</button>
        <button class="secondary quiet-danger" data-action="tunnel-action" data-tunnel="${esc(tunnel.id)}" data-tunnel-action="delete" type="button">删除</button>
      </div>
    </article>
  `;
}


function tutorialCard() {
  return `
    <article class="admin-card tunnel-guide-card">
      <div>
        <strong>详细教程：三步完成内网穿透</strong>
        <span>客户操作步骤</span>
      </div>
      <div class="tunnel-steps">
        <div class="tunnel-step">
          <b>1</b>
          <div><strong>下载安装包</strong><p>先在“后端客户端”区域下载对应系统的配对安装包。共享 Agent 只下载一次，同一台机器后续可以挂多个服务。</p></div>
        </div>
        <div class="tunnel-step">
          <b>2</b>
          <div><strong>运行本地服务</strong><p>在客户电脑或服务器上启动真实服务，端口要和服务映射里填写的本地地址、本地端口一致。</p></div>
        </div>
        <div class="tunnel-step">
          <b>3</b>
          <div><strong>检查本地控制台</strong><p>安装后打开 <code>http://127.0.0.1:19090/</code>，确认运行状态、服务探测和公网地址都是正常。</p></div>
        </div>
      </div>
      <div class="tunnel-platform-grid">
        <div class="tunnel-platform">
          <strong>macOS 安装</strong>
          <p>解压下载包，打开终端进入目录，执行：</p>
          <code>bash install-macos.sh</code>
          <p>安装完成后执行 <code>bash open-dashboard.sh</code> 打开本地控制台。</p>
        </div>
        <div class="tunnel-platform">
          <strong>Linux 安装</strong>
          <p>上传或解压下载包，进入目录后执行：</p>
          <code>sudo bash install-linux.sh</code>
          <p>安装完成后执行 <code>bash open-dashboard.sh</code> 或访问本机控制台地址。</p>
        </div>
        <div class="tunnel-platform">
          <strong>Windows 安装</strong>
          <p>解压下载包，用管理员 PowerShell 进入目录，执行：</p>
          <code>powershell -ExecutionPolicy Bypass -File ./install-windows.ps1</code>
          <p>安装完成后运行 <code>open-dashboard.ps1</code> 打开本地控制台。</p>
        </div>
      </div>
      <p>理解方式：域名解析到 VPS，VPS 负责 HTTPS/Reality 入口；后端客户端主动连回 VPS。客户机器没有公网 IP 也可以提供服务。</p>
    </article>
  `;
}


export function renderAdminTunnels(data = {}) {
  const tunnels = data.tunnels || [];
  const domainOptions = data.domain_options || {};
  const query = data.filters?.tunnels || "";
  const visibleTunnels = tunnels.filter((tunnel) => matchesTunnel(tunnel, query));
  const visibleActiveTunnels = visibleTunnels.filter((tunnel) => tunnel.enabled !== false);
  const visibleDisabledTunnels = visibleTunnels.filter((tunnel) => tunnel.enabled === false);
  const visibleSharedAgentTunnels = visibleActiveTunnels.filter((tunnel) => tunnel.bridge_mode === "shared");
  const visibleDedicatedTunnels = visibleActiveTunnels.filter((tunnel) => tunnel.bridge_mode !== "shared");
  const agentCards = [
    sharedAgentCards(visibleSharedAgentTunnels),
    dedicatedAgentCards(visibleDedicatedTunnels),
  ].filter(Boolean).join("");
  const activeServices = visibleActiveTunnels.map(serviceCard).join("");
  const disabledServices = visibleDisabledTunnels.map(serviceCard).join("");
  return `
    <section class="screen stack">
      <div class="screen-head">
        <div><h1>内网穿透</h1><p>公网入口、后端 Agent 回连与本地服务映射。</p></div>
        <div class="admin-actions">
          <button class="secondary" data-action="tunnel-portal-export" type="button">导出 VPS 配置</button>
          <button class="secondary" data-action="tunnel-portal-apply" type="button">应用到 VPS</button>
          <button class="primary" data-action="tunnel-create-sheet" type="button">新增穿透</button>
        </div>
      </div>
      ${tutorialCard()}
      <article class="admin-card tunnel-edit-form" hidden>
        <div><strong>编辑穿透节点</strong><span>填写公网域名、后端系统和本地服务端口，其余参数会自动生成。</span></div>
        <form class="form-grid compact-form" data-form="tunnel-save">
          <label>类型<select name="kind"><option value="public_https">公开 HTTPS 服务</option><option value="private_tcp">私有 TCP 服务</option></select></label>
          <label>公网域名<input name="public_domain" list="tunnel-domain-options" autocomplete="off" placeholder="app.example.com"><datalist id="tunnel-domain-options">${domainOptionsMarkup(domainOptions)}</datalist></label>
          <p class="form-note">私有 TCP/SSH 无需域名；公开 HTTPS 可选择已识别域名，也可输入新域名，保存时会校验是否解析到本 VPS 且未被面板或普通节点占用。</p>
          <label>名称<input name="name" autocomplete="off" placeholder="我的本地服务"></label>
          <label>本地地址<input name="target_host" value="127.0.0.1" required></label>
          <label>本地端口<input name="target_port" inputmode="numeric" value="3000" required></label>
          <label>ID<input name="id" autocomplete="off" placeholder="留空按域名生成"></label>
          <label>入口端口<input name="portal_port" inputmode="numeric" placeholder="留空自动分配"></label>
          <label>VLESS UUID<input name="client_id" autocomplete="off" placeholder="留空自动生成"></label>
          <label>Reality SNI<input name="reality_sni" value="www.cloudflare.com"></label>
          <label>Bridge 模式<select name="bridge_mode"><option value="dedicated">默认独立 Agent</option><option value="shared">高级共享 Agent</option></select></label>
          <label>Bridge ID<input name="bridge_id" autocomplete="off" placeholder="office-web"></label>
          <label>后端系统<select name="bridge_platform"><option value="macos">macOS</option><option value="linux">Linux</option><option value="windows">Windows</option></select></label>
          <div class="form-actions">
            <button class="primary" type="submit">保存穿透</button>
            <button class="secondary" data-action="tunnel-form-close" type="button">收起</button>
          </div>
        </form>
        ${domainStatusCard(domainOptions)}
      </article>
      <div class="toolbar"><input data-filter="tunnels" value="${esc(query)}" placeholder="搜索穿透节点、入口或本地服务"><button data-action="tunnels-filter" type="button">筛选</button></div>
      <section class="tunnel-section stack">
        <div class="section-title"><h2>后端客户端</h2><p>每台后端机器下载一个配对安装包即可；共享 Agent 下多个服务会自动合并到同一个客户端。</p></div>
        <div class="card-list compact">${agentCards || `<article class="admin-card empty"><p>${tunnels.length ? "没有匹配的后端客户端" : "暂无后端客户端，先新增穿透服务"}</p><button data-action="tunnel-create-sheet" type="button">新增穿透</button></article>`}</div>
      </section>
      <section class="tunnel-section stack">
        <div class="section-title"><h2>服务映射</h2><p>这里管理公网域名、VPS 入口端口和后端本地端口。下载客户端请到上面的“后端客户端”。</p></div>
        <div class="card-list">${activeServices || `<article class="admin-card empty"><p>${tunnels.length ? "没有匹配的在线服务" : "暂无穿透节点"}</p><button data-action="tunnel-create-sheet" type="button">新增穿透</button></article>`}</div>
      </section>
      ${visibleDisabledTunnels.length ? `
        <details class="tunnel-disabled-section">
          <summary>历史/停用服务（${visibleDisabledTunnels.length}）</summary>
          <div class="card-list">${disabledServices}</div>
        </details>
      ` : ""}
    </section>
  `;
}
