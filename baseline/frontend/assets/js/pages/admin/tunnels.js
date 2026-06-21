import { esc } from "../../components/layout.js";


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
  ].join(" ").toLowerCase();
  return haystack.includes(query.toLowerCase());
}


function tunnelCard(tunnel) {
  const bridgeMode = tunnel.bridge_mode === "shared" ? `共享 Agent ${esc(tunnel.bridge_id || "")}` : "独立 Agent";
  const platform = tunnel.bridge_platform || "macos";
  const sharedButton = tunnel.bridge_mode === "shared"
    ? `<button class="secondary" data-action="tunnel-shared-agent-bundle-export" data-bridge="${esc(tunnel.bridge_id || "")}" data-platform="${esc(platform)}" type="button">生成共享配对 Agent</button>
        <button class="secondary" data-action="tunnel-shared-bundle-export" data-bridge="${esc(tunnel.bridge_id || "")}" data-platform="${esc(platform)}" type="button">下载共享 Agent</button>`
    : "";
  const dedicatedButton = tunnel.bridge_mode === "shared"
    ? ""
    : `<button class="secondary" data-action="tunnel-agent-bundle-export" data-tunnel="${esc(tunnel.id)}" data-platform="${esc(platform)}" type="button">生成配对 Agent</button>`;
  const staticBundleButton = tunnel.bridge_mode === "shared"
    ? ""
    : `<button class="secondary" data-action="tunnel-bundle-export" data-tunnel="${esc(tunnel.id)}" data-platform="${esc(platform)}" type="button">下载后端安装包</button>`;
  return `
    <article class="admin-card node-admin-card">
      <div>
        <strong>${esc(tunnel.display_name || tunnel.name || tunnel.id)}</strong>
        <span>${esc(tunnel.portal || "")} -> ${esc(tunnel.target || "")} · ${tunnel.enabled === false ? "停用" : "在线"}</span>
      </div>
      <p>${esc(tunnel.public_domain || tunnel.server_address || "")} · ${esc(tunnel.server_address || "")}:${esc(tunnel.server_port || "443")} · SNI ${esc(tunnel.reality_sni || "www.cloudflare.com")} · ${bridgeMode}</p>
      <div class="admin-actions">
        <button class="secondary" data-action="tunnel-edit" data-tunnel="${esc(tunnel.id)}" type="button">编辑</button>
        ${dedicatedButton}
        ${staticBundleButton}
        ${sharedButton}
        <button class="secondary" data-action="tunnel-export" data-tunnel="${esc(tunnel.id)}" type="button">导出 JSON</button>
        <button class="secondary" data-action="tunnel-action" data-tunnel="${esc(tunnel.id)}" data-tunnel-action="${tunnel.enabled === false ? "enable" : "disable"}" type="button">${tunnel.enabled === false ? "启用" : "停用"}</button>
        <button class="secondary quiet-danger" data-action="tunnel-action" data-tunnel="${esc(tunnel.id)}" data-tunnel-action="delete" type="button">删除</button>
      </div>
    </article>
  `;
}


export function renderAdminTunnels(data = {}) {
  const tunnels = data.tunnels || [];
  const query = data.filters?.tunnels || "";
  const visibleTunnels = tunnels.filter((tunnel) => matchesTunnel(tunnel, query));
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
      <article class="admin-card tunnel-edit-form" hidden>
        <div><strong>编辑穿透节点</strong><span>填写公网域名、后端系统和本地服务端口，其余参数会自动生成。</span></div>
        <form class="form-grid compact-form" data-form="tunnel-save">
          <label>类型<select name="kind"><option value="public_https">公开 HTTPS 服务</option><option value="private_tcp">私有 TCP 服务</option></select></label>
          <label>公网域名<input name="public_domain" autocomplete="off" placeholder="app.example.com"></label>
          <label>名称<input name="name" autocomplete="off" placeholder="我的本地服务"></label>
          <label>本地地址<input name="target_host" value="127.0.0.1" required></label>
          <label>本地端口<input name="target_port" inputmode="numeric" value="3000" required></label>
          <label>ID<input name="id" autocomplete="off" placeholder="留空按域名生成"></label>
          <label>入口端口<input name="portal_port" inputmode="numeric" placeholder="留空自动分配"></label>
          <label>VLESS UUID<input name="client_id" autocomplete="off" placeholder="留空自动生成"></label>
          <label>Reality SNI<input name="reality_sni" value="www.cloudflare.com"></label>
          <label>Bridge 模式<select name="bridge_mode"><option value="dedicated">默认独立 Agent</option><option value="shared">高级共享 Agent</option></select></label>
          <label>Bridge ID<input name="bridge_id" autocomplete="off" placeholder="macbook-web"></label>
          <label>后端系统<select name="bridge_platform"><option value="macos">macOS</option><option value="linux">Linux</option><option value="windows">Windows</option></select></label>
          <div class="form-actions">
            <button class="primary" type="submit">保存穿透</button>
            <button class="secondary" data-action="tunnel-form-close" type="button">收起</button>
          </div>
        </form>
      </article>
      <div class="toolbar"><input data-filter="tunnels" value="${esc(query)}" placeholder="搜索穿透节点、入口或本地服务"><button data-action="tunnels-filter" type="button">筛选</button></div>
      <div class="card-list">${visibleTunnels.map(tunnelCard).join("") || `<article class="admin-card empty"><p>${tunnels.length ? "没有匹配的穿透节点" : "暂无穿透节点"}</p><button data-action="tunnel-create-sheet" type="button">新增穿透</button></article>`}</div>
    </section>
  `;
}
