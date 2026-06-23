import { esc } from "../../components/layout.js?v=3.0.2";
import { empty } from "../../components/ui.js?v=3.0.2";


function linkCard(label, value, action) {
  if (!value) return "";
  return `
    <article class="mobile-card link-mobile-card">
      <div>
        <strong>${esc(label)}</strong>
        <span>${esc(value)}</span>
      </div>
      <button class="secondary" data-action="${esc(action)}" data-text="${esc(value)}" type="button">复制</button>
    </article>
  `;
}


export function renderUserLinks(data = {}) {
  const links = data.links || {};
  if (links.error) {
    return `
      <section class="screen stack">
        <div class="screen-head"><h1>订阅</h1></div>
        <article class="mobile-card notice-card">
          <div><strong>订阅暂不可用</strong><span>${esc(links.error)}</span></div>
          <button class="primary" data-action="open-plans" type="button">续费套餐</button>
        </article>
      </section>
    `;
  }
  const cards = [
    linkCard("通用订阅", links.subscription_url || links.raw_subscription_url, "copy-subscription"),
    linkCard("Mihomo / Clash Meta", links.mihomo_subscription_url, "copy-subscription"),
    linkCard("VLESS", (links.vless_links || [links.vless]).filter(Boolean)[0], "copy-node"),
    linkCard("Hysteria2", links.hy2, "copy-node"),
  ].join("");
  return `
    <section class="screen stack">
      <div class="screen-head">
        <div>
          <h1>订阅</h1>
          <p>优先复制订阅链接，单节点适合临时测试。</p>
        </div>
      </div>
      <div class="card-list">${cards || empty("暂无订阅链接", "refresh", "刷新")}</div>
    </section>
  `;
}
