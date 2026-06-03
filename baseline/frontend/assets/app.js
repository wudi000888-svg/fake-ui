const app = document.querySelector("#app");

let state = {
  session: null,
  data: null,
  view: location.pathname === "/" ? "dashboard" : location.pathname.replace("/", "") || "dashboard",
  notice: null,
  busy: false,
};

const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (ch) => ({
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
}[ch]));

const jsonAttr = (value) => esc(JSON.stringify(String(value ?? "")));
const cssEscape = (value) => window.CSS?.escape ? CSS.escape(String(value ?? "")) : String(value ?? "").replace(/["\\]/g, "\\$&");
const gb = (bytes) => `${(Number(bytes || 0) / 1024 / 1024 / 1024).toFixed(2)} GB`;

async function api(path, options = {}) {
  const init = {
    credentials: "same-origin",
    headers: { "Accept": "application/json", ...(options.headers || {}) },
    ...options,
  };
  if (options.body && typeof options.body !== "string") {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(options.body);
  }
  const res = await fetch(path, init);
  const data = await res.json().catch(() => ({}));
  if (!res.ok || data.ok === false) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

function formData(form) {
  return Object.fromEntries(new FormData(form).entries());
}

function setNotice(type, text) {
  state.notice = text ? { type, text } : null;
  render();
}

async function refresh() {
  const out = await api("/api/dashboard");
  state.session = out.data.session;
  state.data = out.data;
}

function navigate(view) {
  state.view = view;
  history.pushState(null, "", view === "dashboard" ? "/" : `/${view}`);
  state.notice = null;
  render();
}

window.addEventListener("popstate", () => {
  state.view = location.pathname === "/" ? "dashboard" : location.pathname.replace("/", "") || "dashboard";
  render();
});

function nav() {
  const role = state.session?.role;
  const items = role === "admin"
    ? [["dashboard", "概览"], ["hysteria2", "Hysteria2"], ["links", "节点订阅"], ["users", "用户"], ["plans", "套餐"], ["orders", "订单"], ["requests", "申请"], ["nodes", "节点"], ["sub-access", "订阅日志"], ["audit", "审计"], ["backups", "备份"], ["settings", "设置"]]
    : [["dashboard", "首页"], ["plans", "购买套餐"], ["links", "节点订阅"], ["orders", "我的订单"], ["account", "账号"]];
  return `<div class="nav">${items.map(([id, label]) => `<button type="button" class="${state.view === id ? "active" : ""}" data-nav="${id}">${label}</button>`).join("")}<button type="button" data-action="logout">退出</button></div>`;
}

function shell(content, title = "虚假机场", subtitle = "") {
  app.innerHTML = `
    <div class="shell">
      <header class="topbar">
        <div class="brand">
          <div class="mark">IP</div>
          <div><h1>${esc(title)}</h1><p>${esc(subtitle || `${state.session?.username || ""} / ${state.session?.role || ""}`)}</p></div>
        </div>
        ${nav()}
      </header>
      <main class="main">
        ${state.notice ? `<div class="notice ${state.notice.type}">${esc(state.notice.text)}</div>` : ""}
        ${content}
      </main>
    </div>`;
}

function kv(rows) {
  return `<div class="kv">${rows.map(([k, v]) => `<div class="kv-row"><span>${esc(k)}</span><span>${esc(v)}</span></div>`).join("")}</div>`;
}

async function runAction(fn) {
  try {
    state.busy = true;
    render();
    const message = await fn();
    await refresh();
    state.busy = false;
    setNotice("ok", message || "操作完成");
  } catch (err) {
    state.busy = false;
    setNotice("error", err.message);
  }
}

function progressBar(percent) {
  const p = Math.max(0, Math.min(100, Number(percent || 0)));
  return `<div class="progress"><span style="width:${p}%"></span></div>`;
}

function statCard(label, value, hint = "") {
  return `<section class="panel stat-card"><p>${esc(label)}</p><strong>${esc(value)}</strong>${hint ? `<span>${esc(hint)}</span>` : ""}</section>`;
}

function userHomeView() {
  const profile = state.data?.profile || state.data?.links?.metrics || {};
  const orders = state.data?.orders || [];
  const nodes = state.data?.nodes || [];
  const pendingCount = orders.filter((o) => o.status === "pending").length;
  const days = profile.days_left ?? "-";
  const quota = profile.quota_bytes > 0 ? `${gb(profile.remain_bytes)} / ${gb(profile.quota_bytes)}` : "不限量";
  const orderHint = pendingCount ? `你有 ${pendingCount} 个订单等待确认` : "暂无待处理订单";
  shell(`
    <div class="grid three">
      ${statCard("当前套餐", profile.plan_name || "自定义套餐", `节点组：${(profile.node_groups || []).join(",") || "default"}`)}
      ${statCard("剩余天数", `${days} 天`, profile.expires_at || "")}
      ${statCard("订单状态", orderHint, "线下付款后等待管理员确认")}
    </div>
    <section class="panel">
      <div class="section-head"><div><h2>流量使用</h2><p>额度用尽或到期后节点会自动停用。</p></div><span class="pill ${profile.quota_status === "流量正常" ? "on" : "off"}">${esc(profile.quota_status || "未知")}</span></div>
      ${progressBar(profile.used_percent)}
      <div class="metric-row"><span>已用 ${gb(profile.used_bytes)}</span><span>剩余 ${quota}</span><span>${esc(profile.used_percent || 0)}%</span></div>
    </section>
    <section class="panel">
      <div class="section-head"><div><h2>可用节点</h2><p>节点状态由管理员维护，维护中节点可能临时不可用。</p></div><button class="secondary" type="button" data-nav="links">查看订阅</button></div>
      <div class="node-grid">${nodes.map(nodeStatusCard).join("") || `<p>暂无可用节点。</p>`}</div>
    </section>
    <section class="panel">
      <div class="section-head"><div><h2>最近订单</h2><p>订单确认后会自动开通或续费套餐。</p></div><button class="good" type="button" data-nav="plans">购买套餐</button></div>
      ${orderTable(orders.slice(0, 5), false)}
    </section>
  `, "用户中心", `欢迎回来，${state.session?.username || ""}`);
}

function adminDashboardView() {
  const x = state.data?.xray || {};
  const h = state.data?.hy2 || {};
  const users = state.data?.users || [];
  const orders = state.data?.orders || [];
  const nodes = state.data?.nodes || [];
  shell(`
    <div class="grid three">
      ${statCard("用户数量", `${users.length}`, "全部已创建用户")}
      ${statCard("待确认订单", `${orders.filter((o) => o.status === "pending").length}`, "需要人工确认")}
      ${statCard("H2 状态", h.running || "unknown", h.enabled ? `${h.proxy_type || "HTTP"} 代理中` : "直连")}
    </div>
    <div class="grid">
      <section class="panel">
        <div class="section-head"><div><h2>节点出口概览</h2><p>VLESS 出口统一在节点维护里编辑，订阅名称跟随出口国家和 IP。</p></div><button class="secondary" type="button" data-nav="nodes">节点维护</button></div>
        <div class="node-grid">${nodes.filter((n) => n.group === "default").map(nodeStatusCard).join("") || `<p>暂无默认节点。</p>`}</div>
      </section>
      <section class="panel">
        <h2>系统状态</h2>
        ${kv([["Xray 状态", x.xray], ["VPS 公网 IP", x.vps_ip], ["Reality 入站", JSON.stringify(x.inbound || {})], ["H2 Docker", h.running], ["H2 当前代理", h.proxy || "未配置"]])}
      </section>
    </div>
  `, "运营概览", "套餐、订单、节点和用户状态");
}

function dashboardView() {
  return state.session?.role === "admin" ? adminDashboardView() : userHomeView();
}

function hy2View() {
  const h = state.data?.hy2 || {};
  shell(`
    <div class="grid">
      <section class="panel">
        <span class="pill ${h.enabled ? "on" : "off"}">${h.enabled ? `${esc(h.proxy_type || "HTTP")} 代理已启用` : "VPS 直连"}</span>
        <h2>Hysteria2</h2>
        ${kv([["Docker 运行", h.running], ["域名", h.domain], ["端口", h.port], ["当前代理", h.proxy]])}
      </section>
      <section class="panel">
        <h2>启用 / 切换 Hysteria2 上游代理</h2>
        <form data-form="hy2-apply">
          <label>代理类型</label><select name="proxy_type"><option value="http">HTTP</option><option value="socks5">SOCKS5</option></select>
          <div class="form-grid"><div><label>代理地址</label><input name="addr" required></div><div><label>端口</label><input name="port" required></div></div>
          <label>用户名</label><input name="user" placeholder="无认证可留空">
          <label>密码</label><input name="password" type="password" placeholder="无认证可留空">
          <button class="good" ${state.busy ? "disabled" : ""}>启用 / 切换</button>
        </form>
        <div class="actions"><button type="button" class="danger" data-action="hy2-disable" ${state.busy ? "disabled" : ""}>关闭代理恢复直连</button></div>
      </section>
    </div>
    <section class="panel"><h2>最近日志</h2><pre>${esc(h.logs || "")}</pre></section>
  `, "Hysteria2 管理");
}

function linkCard(title, text, qr) {
  return `<div class="link-card">
    <h3>${esc(title)}</h3>
    <div class="copy-row"><textarea readonly>${esc(text || "")}</textarea><button type="button" class="secondary" data-action="copy" data-text="${jsonAttr(text || "")}">复制</button></div>
    ${qr ? `<img class="qr" src="${esc(qr)}" alt="${esc(title)} QR">` : ""}
  </div>`;
}

function linkName(uri, fallback) {
  try {
    return decodeURIComponent(String(uri || "").split("#").pop() || fallback);
  } catch (err) {
    return fallback;
  }
}

function linksView() {
  const links = state.data?.links || {};
  if (links.error) {
    shell(`<section class="panel"><h2>节点订阅暂不可用</h2><div class="notice error">${esc(links.error)}</div><p>请先确认账号是否到期、被禁用或流量已用尽。恢复后订阅会自动可用。</p><div class="actions"><button type="button" class="good" data-nav="plans">购买或续费套餐</button><button type="button" class="secondary" data-nav="dashboard">返回首页</button></div></section>`, "节点订阅");
    return;
  }
  const vlessLinks = links.vless_links || (links.vless ? [links.vless] : []);
  const vlessQrs = links.vless_qrs || [];
  const vlessCards = vlessLinks.map((item, idx) => linkCard(`VLESS ${idx + 1} / ${linkName(item, "")}`, item, vlessQrs[idx] || (idx === 0 ? links.vless_qr : ""))).join("");
  shell(`<section class="panel"><h2>节点与订阅</h2><p>优先导入订阅链接；单节点二维码适合临时测试。</p><div class="link-list">
    ${vlessCards}
    ${linkCard("Hysteria2", links.hy2, links.hy2_qr)}
    ${linkCard("通用订阅", links.subscription_url || links.raw_subscription_url, links.subscription_qr)}
    ${links.mihomo_subscription_url ? linkCard("Mihomo / Clash Meta", links.mihomo_subscription_url, "") : ""}
  </div></section>`, "节点订阅");
}

function planCard(plan, ownedPlanId = "") {
  const current = plan.id === ownedPlanId;
  return `<section class="panel plan-card ${current ? "current" : ""}">
    <div class="section-head"><div><h2>${esc(plan.name)}</h2><p>${esc((plan.node_groups || []).join(",") || "default")}</p></div><span class="pill ${plan.enabled ? "on" : "off"}">${plan.enabled ? "可购买" : "已下架"}</span></div>
    <strong>${esc(plan.traffic_gb)} GB</strong>
    <p>${esc(plan.days)} 天有效期 · 价格 ${esc(plan.price || 0)}</p>
    <div class="actions">
      ${state.session?.role === "admin" ? "" : `<button class="good" type="button" data-action="buy-plan" data-plan="${esc(plan.id)}" ${plan.enabled ? "" : "disabled"}>${current ? "续费当前套餐" : "提交购买订单"}</button>`}
    </div>
  </section>`;
}

function plansView() {
  const plans = state.data?.plans || [];
  const profile = state.data?.profile || {};
  if (state.session?.role !== "admin") {
    shell(`<section class="panel page-intro"><h2>选择套餐</h2><p>提交订单后请按线下约定付款，管理员确认后系统会自动开通或续费。</p></section><div class="grid three">${plans.map((p) => planCard(p, profile.plan_id)).join("")}</div>`, "购买套餐", "订单确认后自动生效");
    return;
  }
  shell(`
    <section class="panel">
      <h2>套餐管理</h2>
      <form data-form="plan-save">
        <div class="form-grid"><div><label>ID</label><input name="id" placeholder="standard" required></div><div><label>名称</label><input name="name" placeholder="标准套餐" required></div></div>
        <div class="form-grid"><div><label>天数</label><input name="days" value="30"></div><div><label>流量 GB</label><input name="traffic_gb" value="100"></div></div>
        <div class="form-grid"><div><label>价格</label><input name="price" value="0"></div><div><label>节点组</label><input name="node_groups" value="default"></div></div>
        <button class="good">保存套餐</button>
      </form>
    </section>
    <section class="panel"><h2>套餐列表</h2>${plansTable(plans)}</section>
  `, "套餐管理");
}

function plansTable(plans) {
  return `<div class="table-wrap"><table><thead><tr><th>ID</th><th>名称</th><th>天数</th><th>流量</th><th>节点组</th><th>状态</th><th>操作</th></tr></thead><tbody>
    ${plans.map((p) => `<tr><td>${esc(p.id)}</td><td>${esc(p.name)}</td><td>${esc(p.days)}</td><td>${esc(p.traffic_gb)} GB</td><td>${esc((p.node_groups || []).join(","))}</td><td>${p.enabled ? "启用" : "停用"}</td><td class="actions"><button type="button" class="secondary" data-action="plan-action" data-plan="${esc(p.id)}" data-plan-action="${p.enabled ? "disable" : "enable"}">${p.enabled ? "停用" : "启用"}</button><button type="button" class="danger" data-action="plan-action" data-plan="${esc(p.id)}" data-plan-action="delete">删除</button></td></tr>`).join("")}
  </tbody></table></div>`;
}

function orderStatusPill(status) {
  const cls = status === "completed" ? "on" : status === "pending" ? "warn" : "off";
  const label = { pending: "待确认", completed: "已完成", cancelled: "已取消" }[status] || status;
  return `<span class="pill ${cls}">${esc(label)}</span>`;
}

function orderKindLabel(kind) {
  return { create: "新开", renew: "续费" }[kind] || kind || "-";
}

function nodeKindLabel(kind) {
  return { vless: "VLESS", hy2: "Hysteria2" }[kind] || kind || "-";
}

function outboundLabel(node) {
  const mode = node.outbound_mode || "direct";
  if (node.kind === "hy2") return "当前 H2 出口";
  if (node.kind !== "vless") return "保持现状";
  if (mode === "direct") return "本地直连";
  return `${mode.toUpperCase()} 上游`;
}

function nodeLocation(node) {
  const ip = node.exit_ip || node.proxy_test_ip || "";
  const country = node.country || node.country_code || "";
  const city = node.city || "";
  const parts = [];
  if (ip) parts.push(ip);
  if (country) parts.push(node.country_code && country !== node.country_code ? `${country} (${node.country_code})` : country);
  if (city) parts.push(city);
  return parts.join(" · ") || "未检测";
}

function orderTable(orders, adminActions = false) {
  return `<div class="table-wrap"><table><thead><tr><th>时间</th><th>用户</th><th>类型</th><th>套餐</th><th>天数</th><th>流量</th><th>状态</th>${adminActions ? "<th>操作</th>" : ""}</tr></thead><tbody>
    ${orders.map((o) => `<tr><td>${esc(o.created_at)}</td><td>${esc(o.username)}</td><td>${esc(orderKindLabel(o.kind))}</td><td>${esc(o.plan_name || o.plan_id)}</td><td>${esc(o.days)}</td><td>${esc(o.traffic_gb)} GB</td><td>${orderStatusPill(o.status)}</td>${adminActions ? `<td>${o.status === "pending" ? `<button type="button" class="secondary" data-action="order-action" data-order="${esc(o.id)}" data-order-action="confirm">确认</button><button type="button" class="danger" data-action="order-action" data-order="${esc(o.id)}" data-order-action="cancel">取消</button>` : ""}</td>` : ""}</tr>`).join("") || `<tr><td colspan="${adminActions ? 8 : 7}">暂无订单</td></tr>`}
  </tbody></table></div>`;
}

function ordersView() {
  const orders = state.data?.orders || [];
  const plans = state.data?.plans || [];
  const planOptions = plans.map((p) => `<option value="${esc(p.id)}">${esc(p.name)} / ${esc(p.days)}天 / ${esc(p.traffic_gb)}GB</option>`).join("");
  shell(`<section class="panel">
    <h2>${state.session?.role === "admin" ? "创建人工订单" : "提交续费订单"}</h2>
    <form data-form="order-create">
      <div class="form-grid"><div><label>用户名</label><input name="username" value="${esc(state.session?.role === "admin" ? "" : state.session?.username || "")}" ${state.session?.role === "admin" ? "" : "readonly"}></div><div><label>类型</label><select name="kind"><option value="renew">续费</option><option value="create">新开</option></select></div></div>
      <label>套餐</label><select name="plan_id">${planOptions}</select>
      <label>备注</label><input name="note" placeholder="线下付款备注">
      <button class="good">提交订单</button>
    </form>
  </section>
  <section class="panel"><div class="section-head"><div><h2>${state.session?.role === "admin" ? "订单与续费记录" : "我的订单"}</h2><p>待确认订单需要管理员审核后才会生效。</p></div></div>${orderTable(orders, state.session?.role === "admin")}</section>`, "订单中心");
}

function nodeStatusCard(n) {
  const status = n.status || "online";
  const cls = status === "online" ? "on" : status === "maintenance" ? "warn" : "off";
  const label = { online: "在线", maintenance: "维护中", offline: "离线" }[status] || status;
  const proxy = n.kind === "vless" && n.outbound_mode !== "direct" ? ` · ${esc(n.proxy_addr || "")}:${esc(n.proxy_port || "")}` : "";
  return `<div class="node-card"><div><strong>${esc(n.display_name || n.name)}</strong><p>${esc(nodeLocation(n))} · ${esc(nodeKindLabel(n.kind))} · ${esc(outboundLabel(n))}${proxy} · 倍率 x${esc(n.multiplier || 1)}</p></div><span class="pill ${cls}">${esc(label)}</span></div>`;
}

function userNodePicker(u, nodes) {
  const selected = new Set((u.effective_node_ids || u.node_ids || []).map(String));
  const hasOverride = Array.isArray(u.node_ids) && u.node_ids.length > 0;
  const enabledNodes = nodes.filter((n) => n.enabled !== false);
  if (!enabledNodes.length) return '<span class="muted">暂无可用节点</span>';
  const choices = enabledNodes.map((n) => {
    const id = String(n.id || "");
    const name = n.display_name || n.name || id;
    return `<label class="node-choice"><input type="checkbox" data-user-node="${esc(u.username)}" value="${esc(id)}" ${selected.has(id) ? "checked" : ""}><span>${esc(name)}</span><em>${esc(nodeKindLabel(n.kind))}</em></label>`;
  }).join("");
  return `<div class="node-picker"><div class="node-picker-head"><span class="muted">${hasOverride ? "精确指定" : "按套餐默认"}</span><button type="button" class="secondary tiny" data-action="save-user-nodes" data-user="${esc(u.username)}">保存节点</button><button type="button" class="secondary tiny" data-action="clear-user-nodes" data-user="${esc(u.username)}">恢复默认</button></div>${choices}</div>`;
}

function usersView() {
  const users = state.data?.users || [];
  const plans = state.data?.plans || [];
  const nodes = state.data?.nodes || [];
  const planOptions = `<option value="">自定义</option>${plans.map((p) => `<option value="${esc(p.id)}">${esc(p.name)} / ${esc(p.days)}天 / ${esc(p.traffic_gb)}GB</option>`).join("")}`;
  shell(`
    <section class="panel">
      <h2>创建用户</h2>
      <form data-form="user-create">
        <label>套餐</label><select name="plan_id">${planOptions}</select>
        <div class="form-grid"><div><label>用户名</label><input name="username" required></div><div><label>天数</label><input name="days" value="30"></div></div>
        <div class="form-grid"><div><label>流量 GB</label><input name="traffic_gb" value="0"></div><div><label>面板密码</label><input name="panel_password" placeholder="留空自动生成"></div></div>
        <label>备注</label><input name="note">
        <button class="good" ${state.busy ? "disabled" : ""}>创建用户</button>
      </form>
    </section>
    <section class="panel"><h2>用户列表</h2><div class="table-wrap"><table><thead><tr><th>用户</th><th>状态</th><th>到期</th><th>流量</th><th>可用节点</th><th>订阅</th><th>操作</th></tr></thead><tbody>
      ${users.map((u) => `<tr><td>${esc(u.username)}<br><span class="muted">${esc(u.note)}</span></td><td>${esc(u.status)}<br>${esc(u.quota_status)}</td><td>${esc(u.expires_at)}<br><span class="muted">${esc(u.metrics?.days_left ?? "-")} 天</span></td><td>${progressBar(u.metrics?.used_percent)}<span class="muted">${esc(u.quota)}</span></td><td>${userNodePicker(u, nodes)}</td><td><button type="button" class="secondary" data-action="copy" data-text="${jsonAttr(u.raw_subscription_url || u.subscription_url)}">复制订阅</button></td><td class="actions"><button type="button" class="secondary" data-action="user-action" data-user="${esc(u.username)}" data-user-action="${u.enabled ? "disable" : "enable"}">${u.enabled ? "禁用" : "启用"}</button><button type="button" class="secondary" data-action="user-action" data-user="${esc(u.username)}" data-user-action="extend">延长30天</button><button type="button" class="secondary" data-action="reset-sub" data-user="${esc(u.username)}">重置订阅</button><button type="button" class="secondary" data-action="user-action" data-user="${esc(u.username)}" data-user-action="reset_traffic">清流量</button><button type="button" class="danger" data-action="user-action" data-user="${esc(u.username)}" data-user-action="delete">删除</button></td></tr>`).join("")}
    </tbody></table></div></section>
  `, "用户管理");
}

function nodesView() {
  const nodes = state.data?.nodes || [];
  const option = (value, label) => `<option value="${value}">${label}</option>`;
  shell(`
    <section class="panel">
      <div class="section-head"><div><h2>节点维护</h2><p>新增默认 VLESS 会自动编号、排序，并作为本机出口同步进所有用户订阅。</p></div><button type="button" class="good" data-action="add-vless">新增默认 VLESS</button></div>
      <form data-form="node-save">
        <div class="form-grid"><div><label>ID</label><input name="id" placeholder="vless-main" required></div><div><label>名称</label><input name="name" placeholder="香港 VLESS"></div></div>
        <div class="form-grid"><div><label>类型</label><select name="kind"><option value="vless">VLESS</option><option value="hy2">Hysteria2</option></select></div><div><label>节点组</label><input name="group" value="default"></div></div>
        <div class="form-grid"><div><label>地区</label><input name="region" placeholder="自动检测"></div><div><label>倍率</label><input name="multiplier" value="1"></div></div>
        <div class="form-grid"><div><label>状态</label><select name="status"><option value="online">在线</option><option value="maintenance">维护中</option><option value="offline">离线</option></select></div><div><label>延迟 ms</label><input name="latency_ms" value="0"></div></div>
        <div class="form-grid"><div><label>VLESS 出口</label><select name="outbound_mode">${option("direct", "本地直连")}${option("http", "HTTP 上游代理")}${option("socks5", "SOCKS5 上游代理")}</select></div><div><label>排序</label><input name="sort" value="100"></div></div>
        <div class="form-grid"><div><label>上游地址</label><input name="proxy_addr" placeholder="直连可留空"></div><div><label>上游端口</label><input name="proxy_port" placeholder="直连可留空"></div></div>
        <div class="form-grid"><div><label>上游用户名</label><input name="proxy_user" placeholder="无认证可留空"></div><div><label>上游密码</label><input name="proxy_password" type="password" placeholder="留空保留原密码"></div></div>
        <button class="good">保存节点</button>
      </form>
    </section>
    <section class="panel"><h2>节点状态</h2><div class="node-grid">${nodes.map(nodeStatusCard).join("")}</div><div class="table-wrap"><table><thead><tr><th>ID</th><th>名称</th><th>类型</th><th>出口</th><th>出口IP / 国家</th><th>组</th><th>地区</th><th>倍率</th><th>状态</th><th>启用</th><th>操作</th></tr></thead><tbody>
      ${nodes.map((n) => `<tr><td>${esc(n.id)}</td><td>${esc(n.display_name || n.name)}</td><td>${esc(nodeKindLabel(n.kind))}</td><td>${esc(outboundLabel(n))}<br><span class="muted">${n.outbound_mode !== "direct" ? `${esc(n.proxy_addr || "")}:${esc(n.proxy_port || "")}${n.proxy_password_set ? " / 已保存密码" : ""}` : "本机 IP 出口"}</span></td><td>${esc(nodeLocation(n))}</td><td>${esc(n.group)}</td><td>${esc(n.region || "")}</td><td>x${esc(n.multiplier || 1)}</td><td>${esc(n.status || "")}</td><td>${n.enabled ? "启用" : "停用"}</td><td class="actions"><button type="button" class="secondary" data-action="node-edit" data-node="${esc(n.id)}">编辑</button>${["vless", "hy2"].includes(n.kind) ? `<button type="button" class="secondary" data-action="node-action" data-node="${esc(n.id)}" data-node-action="refresh">刷新出口</button>` : ""}<button type="button" class="secondary" data-action="node-action" data-node="${esc(n.id)}" data-node-action="${n.enabled ? "disable" : "enable"}">${n.enabled ? "停用" : "启用"}</button>${n.can_delete ? `<button type="button" class="danger" data-action="node-action" data-node="${esc(n.id)}" data-node-action="delete">删除</button>` : ""}</td></tr>`).join("")}
    </tbody></table></div></section>
  `, "节点管理");
}

function fillNodeForm(node) {
  const form = app.querySelector('form[data-form="node-save"]');
  if (!form || !node) return;
  const fields = ["id", "name", "kind", "group", "region", "multiplier", "status", "latency_ms", "outbound_mode", "sort", "proxy_addr", "proxy_port", "proxy_user"];
  fields.forEach((key) => {
    if (form.elements[key]) form.elements[key].value = node[key] ?? "";
  });
  if (form.elements.proxy_password) form.elements.proxy_password.value = "";
  form.scrollIntoView({ behavior: "smooth", block: "start" });
  form.elements.name?.focus();
}

function requestsView() {
  const regs = state.data?.registrations || [];
  const resets = state.data?.password_resets || [];
  shell(`<section class="panel"><h2>注册申请</h2><div class="table-wrap"><table><thead><tr><th>时间</th><th>用户</th><th>邮箱</th><th>套餐</th><th>状态</th><th>操作</th></tr></thead><tbody>
    ${regs.map((r) => `<tr><td>${esc(r.created_at)}</td><td>${esc(r.username)}</td><td>${esc(r.email)}</td><td>${esc(r.plan_id)}</td><td>${esc(r.status)}</td><td>${r.status === "pending" ? `<button type="button" class="secondary" data-action="registration-action" data-token="${esc(r.token)}" data-registration-action="approve">通过</button><button type="button" class="danger" data-action="registration-action" data-token="${esc(r.token)}" data-registration-action="reject">拒绝</button>` : ""}</td></tr>`).join("")}
  </tbody></table></div></section><section class="panel"><h2>找回密码申请</h2><div class="table-wrap"><table><thead><tr><th>时间</th><th>用户</th><th>状态</th><th>操作</th></tr></thead><tbody>
    ${resets.map((r) => `<tr><td>${esc(r.created_at)}</td><td>${esc(r.username)}</td><td>${esc(r.status)}</td><td>${r.status === "pending" ? `<button type="button" class="secondary" data-action="reset-action" data-token="${esc(r.token)}" data-reset-action="approve">生成新密码</button><button type="button" class="danger" data-action="reset-action" data-token="${esc(r.token)}" data-reset-action="reject">拒绝</button>` : ""}</td></tr>`).join("")}
  </tbody></table></div></section>`, "申请处理");
}

function subAccessView() {
  const access = state.data?.subscription_access || [];
  shell(`<section class="panel"><h2>订阅访问日志</h2><p>用于发现订阅泄露、异常 IP 和频繁请求。</p><div class="table-wrap"><table><thead><tr><th>时间</th><th>用户</th><th>IP</th><th>状态</th><th>路径</th><th>User-Agent</th></tr></thead><tbody>
    ${access.map((a) => `<tr><td>${esc(a.time)}</td><td>${esc(a.username)}</td><td>${esc(a.ip)}</td><td>${esc(a.status)}</td><td>${esc(a.path)}</td><td>${esc(a.ua)}</td></tr>`).join("")}
  </tbody></table></div></section>`, "订阅安全");
}

function auditView() {
  const audit = state.data?.audit || [];
  shell(`<section class="panel"><h2>操作审计</h2><div class="table-wrap"><table><thead><tr><th>时间</th><th>操作者</th><th>动作</th><th>目标</th><th>详情</th></tr></thead><tbody>
    ${audit.map((a) => `<tr><td>${esc(a.time)}</td><td>${esc(a.actor)}</td><td>${esc(a.action)}</td><td>${esc(a.target)}</td><td><pre>${esc(JSON.stringify(a.detail || {}, null, 2))}</pre></td></tr>`).join("")}
  </tbody></table></div></section>`, "操作审计");
}

function backupsView() {
  const backups = state.data?.backups || [];
  shell(`<section class="panel"><h2>备份</h2><p>备份包含面板 JSON 数据和日志。</p><button type="button" class="good" data-action="backup-create">立即备份</button></section><section class="panel"><h2>备份文件</h2><div class="table-wrap"><table><thead><tr><th>文件</th><th>大小</th><th>路径</th></tr></thead><tbody>
    ${backups.map((b) => `<tr><td>${esc(b.name)}</td><td>${esc(b.size)}</td><td>${esc(b.path)}</td></tr>`).join("")}
  </tbody></table></div></section>`, "备份管理");
}

function accountView() {
  shell(`<section class="panel"><h2>账号安全</h2><form data-form="self-password"><label>当前密码</label><input name="old_password" type="password" required><label>新密码</label><input name="new_password" type="password" required><button class="good">修改密码</button></form><div class="actions"><button type="button" class="secondary" data-action="self-reset-sub">重置我的订阅</button></div></section>`, "账号设置");
}

function registerView() {
  app.innerHTML = `<div class="login-wrap"><section class="panel login-card"><div class="mark">IP</div><h2>注册账号</h2><p>提交后等待管理员审核，审核通过会自动开通套餐。</p><form data-form="register"><label for="register-username">用户名</label><input id="register-username" name="username" required><label for="register-email">邮箱</label><input id="register-email" name="email"><label for="register-password">密码</label><input id="register-password" name="password" type="password" required><label for="register-plan">套餐 ID</label><input id="register-plan" name="plan_id" value="starter"><button class="good">提交注册申请</button></form><div class="actions"><button type="button" class="secondary" data-nav="login">返回登录</button><button type="button" class="secondary" data-nav="forgot">找回密码</button></div></section></div>`;
}

function forgotView() {
  app.innerHTML = `<div class="login-wrap"><section class="panel login-card"><div class="mark">IP</div><h2>找回密码</h2><p>提交后等待管理员审核，审核通过后管理员会看到新密码。</p><form data-form="forgot"><label for="forgot-username">用户名</label><input id="forgot-username" name="username" required><button class="good">提交找回申请</button></form><div class="actions"><button type="button" class="secondary" data-nav="login">返回登录</button></div></section></div>`;
}

function settingsView() {
  shell(`<section class="panel"><h2>管理员账号设置</h2><form data-form="settings"><label>当前管理员密码</label><input name="old_password" type="password" required><div class="form-grid"><div><label>管理员账号</label><input name="admin_username" required></div><div><label>管理员新密码</label><input name="admin_password" type="password"></div></div><div class="form-grid"><div><label>查看账号</label><input name="viewer_username" required></div><div><label>查看账号新密码</label><input name="viewer_password" type="password"></div></div><button class="blue">保存并重新登录</button></form></section>`, "系统设置");
}

function render() {
  if (state.view === "register") return registerView();
  if (state.view === "forgot") return forgotView();
  if (!state.session) return renderLogin();
  if (state.session.role !== "admin" && !["dashboard", "plans", "links", "orders", "account"].includes(state.view)) state.view = "dashboard";
  if (state.view === "dashboard") return dashboardView();
  if (state.view === "hysteria2") return hy2View();
  if (state.view === "links") return linksView();
  if (state.view === "users") return usersView();
  if (state.view === "plans") return plansView();
  if (state.view === "orders") return ordersView();
  if (state.view === "requests") return requestsView();
  if (state.view === "nodes") return nodesView();
  if (state.view === "sub-access") return subAccessView();
  if (state.view === "audit") return auditView();
  if (state.view === "backups") return backupsView();
  if (state.view === "account") return accountView();
  if (state.view === "settings") return settingsView();
  return dashboardView();
}

function renderLogin(error = "") {
  app.innerHTML = `<div class="login-wrap"><section class="panel login-card"><div class="mark">IP</div><h2>代理服务面板</h2><p>登录后查看套餐、流量、节点和订单。</p>${error ? `<div class="notice error">${esc(error)}</div>` : ""}<form data-form="login"><label for="login-username">账号</label><input id="login-username" name="username" autocomplete="username" required autofocus><label for="login-password">密码</label><input id="login-password" name="password" type="password" autocomplete="current-password" required><button class="good">登录</button></form><div class="actions"><button type="button" class="secondary" data-nav="register">注册</button><button type="button" class="secondary" data-nav="forgot">找回密码</button></div></section></div>`;
}

async function copyText(text) {
  const value = String(text || "");
  if (navigator.clipboard?.writeText && window.isSecureContext) {
    await navigator.clipboard.writeText(value);
  } else {
    const ta = document.createElement("textarea");
    ta.value = value;
    ta.style.position = "fixed";
    ta.style.left = "-9999px";
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    document.execCommand("copy");
    ta.remove();
  }
  setNotice("ok", "已复制");
}

async function logout() {
  await api("/api/logout", { method: "POST", body: {} }).catch(() => {});
  state = { session: null, data: null, view: "dashboard", notice: null, busy: false };
  history.replaceState(null, "", "/login");
  renderLogin();
}

function userAction(username, action) {
  if (action === "delete" && !confirm(`确认删除 ${username}？`)) return;
  runAction(async () => {
    await api("/api/users/action", { method: "POST", body: { username, action, days: "30" } });
    return `用户 ${username} 操作完成`;
  });
}

app.addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  const navTarget = button.dataset.nav;
  if (navTarget) return navigate(navTarget);
  const action = button.dataset.action;
  if (!action) return;
  if (action === "logout") logout();
  else if (action === "copy") copyText(JSON.parse(button.dataset.text || "\"\""));
  else if (action === "buy-plan") {
    runAction(async () => {
      const out = await api("/api/orders/create", { method: "POST", body: { plan_id: button.dataset.plan || "", kind: "renew", note: "用户自助提交" } });
      return `订单已提交：${out.order.id}，等待管理员确认`;
    });
  } else if (action === "user-action") userAction(button.dataset.user || "", button.dataset.userAction || "");
  else if (action === "save-user-nodes") {
    const username = button.dataset.user || "";
    const boxes = Array.from(app.querySelectorAll(`input[data-user-node="${cssEscape(username)}"]`));
    const node_ids = boxes.filter((box) => box.checked).map((box) => box.value);
    runAction(async () => {
      await api("/api/users/action", { method: "POST", body: { username, action: "set_nodes", node_ids } });
      return node_ids.length ? "用户节点已精确同步" : "用户节点已恢复套餐默认";
    });
  }
  else if (action === "clear-user-nodes") {
    const username = button.dataset.user || "";
    runAction(async () => {
      await api("/api/users/action", { method: "POST", body: { username, action: "set_nodes", node_ids: [] } });
      return "用户节点已恢复套餐默认";
    });
  }
  else if (action === "reset-sub") runAction(async () => { await api("/api/users/reset-subscription", { method: "POST", body: { username: button.dataset.user || "" } }); return "订阅已重置"; });
  else if (action === "plan-action") runAction(async () => { await api("/api/plans/action", { method: "POST", body: { id: button.dataset.plan || "", action: button.dataset.planAction || "" } }); return "套餐已更新"; });
  else if (action === "add-vless") runAction(async () => { const out = await api("/api/nodes/add-vless", { method: "POST", body: {} }); return `已新增 ${out.node.display_name || out.node.name}`; });
  else if (action === "node-edit") fillNodeForm((state.data?.nodes || []).find((n) => n.id === button.dataset.node));
  else if (action === "node-action") {
    const nodeAction = button.dataset.nodeAction || "";
    if (nodeAction === "delete" && !confirm(`确认删除 ${button.dataset.node || ""}？`)) return;
    runAction(async () => {
      await api("/api/nodes/action", { method: "POST", body: { id: button.dataset.node || "", action: nodeAction } });
      if (nodeAction === "refresh") return "出口已刷新";
      if (nodeAction === "delete") return "节点已删除";
      return "节点已更新";
    });
  }
  else if (action === "order-action") runAction(async () => { await api("/api/orders/action", { method: "POST", body: { id: button.dataset.order || "", action: button.dataset.orderAction || "" } }); return "订单已更新"; });
  else if (action === "registration-action") runAction(async () => { await api("/api/registrations/action", { method: "POST", body: { token: button.dataset.token || "", action: button.dataset.registrationAction || "" } }); return "注册申请已处理"; });
  else if (action === "reset-action") runAction(async () => { const out = await api("/api/password-reset/action", { method: "POST", body: { token: button.dataset.token || "", action: button.dataset.resetAction || "" } }); return out.result?.password ? `新密码：${out.result.password}` : "找回申请已处理"; });
  else if (action === "backup-create") runAction(async () => { const out = await api("/api/backups/create", { method: "POST", body: { reason: "manual" } }); return `备份已创建：${out.backup.path}`; });
  else if (action === "self-reset-sub") runAction(async () => { await api("/api/self/reset-subscription", { method: "POST", body: {} }); return "订阅已重置"; });
  else if (action === "hy2-disable") runAction(async () => (await api("/api/hy2/disable", { method: "POST", body: {} })).result.message);
});

app.addEventListener("submit", (event) => {
  const form = event.target.closest("form");
  if (!form) return;
  event.preventDefault();
  const kind = form.dataset.form;
  if (kind === "login") {
    (async () => {
      try {
        await api("/api/login", { method: "POST", body: formData(form) });
        await refresh();
        state.view = "dashboard";
        history.replaceState(null, "", "/");
        render();
      } catch (err) {
        renderLogin(err.message === "invalid username or password" ? "账号或密码错误。" : err.message);
      }
    })();
  } else if (kind === "hy2-apply") runAction(async () => { const out = await api("/api/hy2/apply", { method: "POST", body: formData(form) }); return `${out.result.message}\n代理出口：${out.result.proxy_test_ip || ""}`; });
  else if (kind === "user-create") runAction(async () => { const out = await api("/api/users/create", { method: "POST", body: formData(form) }); return `用户 ${out.result.username} 创建成功，密码：${out.result.panel_password}`; });
  else if (kind === "order-create") runAction(async () => { const out = await api("/api/orders/create", { method: "POST", body: formData(form) }); return `订单已提交：${out.order.id}`; });
  else if (kind === "register") {
    (async () => {
      try {
        const out = await api("/api/register", { method: "POST", body: formData(form) });
        renderLogin(`注册申请已提交，编号：${out.registration.token.slice(0, 10)}...`);
      } catch (err) {
        app.querySelector(".login-card")?.insertAdjacentHTML("afterbegin", `<div class="notice error">${esc(err.message)}</div>`);
      }
    })();
  } else if (kind === "forgot") {
    (async () => {
      try {
        const out = await api("/api/password-reset/request", { method: "POST", body: formData(form) });
        renderLogin(`找回申请已提交，编号：${out.reset.token.slice(0, 10)}...`);
      } catch (err) {
        app.querySelector(".login-card")?.insertAdjacentHTML("afterbegin", `<div class="notice error">${esc(err.message)}</div>`);
      }
    })();
  } else if (kind === "plan-save") runAction(async () => { await api("/api/plans/save", { method: "POST", body: formData(form) }); return "套餐已保存"; });
  else if (kind === "node-save") runAction(async () => { await api("/api/nodes/save", { method: "POST", body: formData(form) }); return "节点已保存"; });
  else if (kind === "self-password") runAction(async () => { await api("/api/self/password", { method: "POST", body: formData(form) }); return "密码已修改"; });
  else if (kind === "settings") {
    (async () => {
      try {
        state.busy = true;
        render();
        await api("/api/settings", { method: "POST", body: formData(form) });
        state.busy = false;
        state.session = null;
        state.data = null;
        history.replaceState(null, "", "/login");
        renderLogin("设置已保存，请重新登录。");
      } catch (err) {
        state.busy = false;
        setNotice("error", err.message);
      }
    })();
  }
});

(async function boot() {
  try {
    await refresh();
    render();
  } catch {
    state.session = null;
    if (location.pathname !== "/login" && !["/register", "/forgot"].includes(location.pathname)) history.replaceState(null, "", "/login");
    state.view = location.pathname.replace("/", "") || "login";
    render();
  }
})();
