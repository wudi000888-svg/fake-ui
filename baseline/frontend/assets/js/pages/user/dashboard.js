import { esc } from "../../components/layout.js?v=3.0.2";
import { empty, gb, stat, statusPill } from "../../components/ui.js?v=3.0.2";


function linkForNode(node, links, index) {
  if (node.kind === "hy2") return links.hy2 || "";
  if (node.kind === "vless") return (links.vless_links || [])[index] || links.vless || "";
  return "";
}


function nodeCards(nodes, links) {
  if (!nodes.length) return empty("暂无可用节点", "open-plans", "查看套餐");
  let vlessIndex = 0;
  return nodes.slice(0, 6).map((node) => {
    const index = node.kind === "vless" ? vlessIndex++ : 0;
    const nodeLink = linkForNode(node, links, index);
    return `
    <article class="mobile-card node-summary-card">
      <div>
        <strong>${esc(node.display_name || node.name || node.id)}</strong>
        <span>${esc(node.kind || "")} · ${esc(node.location || node.country || "未标注地区")}</span>
      </div>
      ${nodeLink
        ? `<button class="secondary" data-action="copy-node" data-text="${esc(nodeLink)}" type="button">复制</button>`
        : `<button class="secondary" data-action="open-links" type="button">打开订阅</button>`}
    </article>
  `;
  }).join("");
}


export function renderUserDashboard(data = {}) {
  const profile = data.profile || {};
  const nodes = data.nodes || [];
  const links = data.links || {};
  return `
    <section class="screen stack">
      <div class="screen-head">
        <div>
          <h1>首页</h1>
          <p>${esc(profile.plan_name || "当前套餐")}</p>
        </div>
        ${statusPill(profile.status)}
      </div>
      <div class="stat-grid">
        ${stat("剩余流量", gb(profile.remain_bytes))}
        ${stat("已用流量", gb(profile.used_bytes))}
        ${stat("到期天数", profile.days_left == null ? "--" : `${profile.days_left} 天`)}
      </div>
      <article class="mobile-card">
        <div>
          <strong>订阅可用性</strong>
          <span>${esc(profile.quota_status || "状态未知")}</span>
        </div>
        <button class="primary" data-action="open-links" type="button">打开订阅</button>
      </article>
      <div class="section-row"><h2>可用节点</h2><span>${nodes.length} 个</span></div>
      <div class="card-list compact">${nodeCards(nodes, links)}</div>
    </section>
  `;
}
