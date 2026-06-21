import { esc } from "../../components/layout.js?v=3.0.1";


function matchesNode(node, query) {
  if (!query) return true;
  const haystack = [
    node.id,
    node.name,
    node.display_name,
    node.kind,
    node.group,
    node.region,
    node.outbound_mode,
    node.exit_ip,
    node.country,
    node.country_code,
    node.city,
    node.proxy_addr,
  ].join(" ").toLowerCase();
  return haystack.includes(query.toLowerCase());
}


function nodeCard(node) {
  const canDelete = node.can_delete && node.kind === "vless";
  return `
    <article class="admin-card node-admin-card">
      <div>
        <strong>${esc(node.display_name || node.name || node.id)}</strong>
        <span>${esc(node.kind || "")} · ${esc(node.outbound_mode || "direct")} · ${esc(node.status || "online")}</span>
      </div>
      <p>${esc(node.exit_ip || node.address || "")} ${node.country_code ? `· ${esc(node.country_code)}` : ""}</p>
      <div class="admin-actions">
        <button class="secondary" data-action="node-edit" data-node="${esc(node.id)}" type="button">编辑</button>
        <button class="secondary" data-action="node-quality-check" data-node="${esc(node.id)}" type="button">exit quality</button>
        <button class="secondary" data-action="node-action" data-node="${esc(node.id)}" data-node-action="${node.enabled === false ? "enable" : "disable"}" type="button">${node.enabled === false ? "启用" : "停用"}</button>
        ${canDelete ? `<button class="secondary quiet-danger" data-action="node-action" data-node="${esc(node.id)}" data-node-action="delete" type="button">删除</button>` : ""}
      </div>
    </article>
  `;
}


export function renderAdminNodes(data = {}) {
  const nodes = data.nodes || [];
  const query = data.filters?.nodes || "";
  const visibleNodes = nodes.filter((node) => matchesNode(node, query));
  return `
    <section class="screen stack">
      <div class="screen-head">
        <div><h1>节点</h1><p>VLESS、Hysteria2 与出口质量检测。</p></div>
        <button class="primary" data-action="node-add" type="button">新增节点</button>
      </div>
      <article class="admin-card node-edit-form" hidden>
        <div><strong>编辑节点</strong><span>VLESS 可设置直连、HTTP 或 SOCKS5 出口；H2 保持直连。</span></div>
        <form class="form-grid compact-form" data-form="node-save">
          <label>ID<input name="id" autocomplete="off" required></label>
          <label>名称<input name="name" autocomplete="off"></label>
          <label>类型
            <select name="kind">
              <option value="vless">VLESS</option>
              <option value="hy2">Hysteria2</option>
            </select>
          </label>
          <label>节点组<input name="group" value="default"></label>
          <label>地区<input name="region" placeholder="自动检测可留空"></label>
          <label>倍率<input name="multiplier" inputmode="decimal" value="1"></label>
          <label>状态
            <select name="status">
              <option value="online">在线</option>
              <option value="maintenance">维护中</option>
              <option value="offline">离线</option>
            </select>
          </label>
          <label>延迟 ms<input name="latency_ms" inputmode="numeric" value="0"></label>
          <label>VLESS 出口
            <select name="outbound_mode">
              <option value="direct">本机直连</option>
              <option value="http">HTTP 上游代理</option>
              <option value="socks5">SOCKS5 上游代理</option>
            </select>
          </label>
          <label>排序<input name="sort" inputmode="numeric" value="100"></label>
          <label>上游地址<input name="proxy_addr" placeholder="直连可留空"></label>
          <label>上游端口<input name="proxy_port" inputmode="numeric" placeholder="直连可留空"></label>
          <label>上游用户名<input name="proxy_user" placeholder="无认证可留空"></label>
          <label>上游密码<input name="proxy_password" type="password" placeholder="留空保留原密码"></label>
          <div class="form-actions">
            <button class="primary" type="submit">保存节点</button>
            <button class="secondary" data-action="node-form-close" type="button">收起</button>
          </div>
        </form>
      </article>
      <div class="toolbar"><input data-filter="nodes" value="${esc(query)}" placeholder="搜索节点、地区或出口 IP"><button data-action="nodes-filter" type="button">筛选</button></div>
      <div class="card-list">${visibleNodes.map(nodeCard).join("") || `<article class="admin-card empty"><p>${nodes.length ? "没有匹配的节点" : "暂无节点"}</p><button data-action="node-add" type="button">新增节点</button></article>`}</div>
    </section>
  `;
}
