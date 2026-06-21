import { esc } from "../../components/layout.js?v=3.0.1";


function statusLine(hy2 = {}) {
  const mode = hy2.enabled ? (hy2.proxy_type || "代理") : "直连";
  return `${hy2.running || "unknown"} · ${mode} · ${hy2.domain || ""}:${hy2.port || "443"}`;
}


function currentProxy(hy2 = {}) {
  const proxy = String(hy2.proxy || "");
  if (!proxy || proxy === "未配置") return {};
  try {
    const parsed = new URL(proxy);
    return {
      proxy_type: parsed.protocol.startsWith("socks") ? "socks5" : "http",
      addr: parsed.hostname,
      port: parsed.port,
      user: decodeURIComponent(parsed.username || ""),
      password: decodeURIComponent(parsed.password || ""),
    };
  } catch {
    return {};
  }
}


function addrFromProxy(proxy = {}) {
  return proxy.addr || "";
}


export function renderAdminHy2(data = {}) {
  const hy2 = data.hy2 || {};
  const node = (data.nodes || []).find((item) => item.kind === "hy2") || {};
  const proxy = currentProxy(hy2);
  const selectedType = proxy.proxy_type || "http";
  return `
    <section class="screen stack">
      <div class="screen-head">
        <div><h1>Hysteria2</h1><p>H2 出口代理、运行状态和节点展示。</p></div>
        <button class="secondary" data-action="refresh" type="button">刷新</button>
      </div>
      <article class="admin-card">
        <div class="hy2-status-head"><strong>运行状态</strong><span>${esc(statusLine(hy2))}</span></div>
        <p>${esc(hy2.proxy || "未配置")}</p>
        <p>${esc(node.display_name || node.name || "Hysteria2")} ${node.exit_ip ? `· ${esc(node.exit_ip)}` : ""} ${node.country_code ? `· ${esc(node.country_code)}` : ""}</p>
        <div class="admin-actions">
          <button class="secondary" data-action="hy2-disable" type="button">恢复直连</button>
        </div>
      </article>
      <article class="admin-card">
        <div><strong>Hysteria2 出口</strong><span>填写 HTTP 或 SOCKS5 上游；保存后自动检测出口 IP / 国家并同步节点名称。</span></div>
        <form class="form-grid compact-form" data-form="hy2-save">
          <label>上游类型
            <select name="proxy_type">
              <option value="http"${selectedType === "http" ? " selected" : ""}>HTTP</option>
              <option value="socks5"${selectedType === "socks5" ? " selected" : ""}>SOCKS5</option>
            </select>
          </label>
          <label>上游地址<input name="addr" value="${esc(addrFromProxy(proxy))}" placeholder="例如 1.2.3.4" required></label>
          <label>上游端口<input name="port" value="${esc(proxy.port || "")}" inputmode="numeric" placeholder="例如 8080" required></label>
          <label>上游用户名<input name="user" value="${esc(proxy.user || "")}" placeholder="无认证可留空"></label>
          <label>上游密码<input name="password" type="password" value="${esc(proxy.password || "")}" placeholder="无认证可留空"></label>
          <div class="form-actions">
            <button class="primary" type="submit">保存 H2 出口</button>
            <button class="secondary" data-action="refresh" type="button">取消</button>
          </div>
        </form>
      </article>
      <article class="admin-card">
        <div><strong>最近日志</strong><span>Hysteria2</span></div>
        <pre class="log-box">${esc((hy2.logs || "").slice(-1600) || "暂无日志")}</pre>
      </article>
    </section>
  `;
}
