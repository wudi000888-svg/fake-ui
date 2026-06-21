import { esc } from "../../components/layout.js?v=3.0.1";
import { gb } from "../../components/ui.js?v=3.0.1";


function matchesUser(user, query) {
  if (!query) return true;
  const haystack = [
    user.username,
    user.status,
    user.quota_status,
    user.plan_name,
    user.plan_id,
    user.note,
    user.expires_at,
  ].join(" ").toLowerCase();
  return haystack.includes(query.toLowerCase());
}


function nodeLabel(node) {
  return node.display_name || node.name || node.id || "";
}


function userNodeText(user, nodes) {
  const ids = user.effective_node_ids || user.node_ids || [];
  if (!ids.length) return "按套餐默认节点";
  const byId = Object.fromEntries(nodes.map((node) => [node.id, nodeLabel(node)]));
  return ids.map((id) => byId[id] || id).join("、");
}


function nodePicker(nodes, user = {}) {
  const selected = new Set(user.node_ids || []);
  return `
    <fieldset class="node-picker" data-node-picker="user-edit">
      <legend>可用节点</legend>
      <p>不勾选时使用套餐默认节点组；勾选后只允许这些节点。</p>
      <div class="node-picker-grid">
        ${nodes.map((node) => `
          <label class="check-card">
            <input type="checkbox" name="node_ids" value="${esc(node.id || "")}" ${selected.has(node.id) ? "checked" : ""}>
            <span>
              <strong>${esc(nodeLabel(node))}</strong>
              <small>${esc(node.kind || "")} · ${esc(node.group || "default")} · ${esc(node.enabled === false ? "停用" : "启用")}</small>
            </span>
          </label>
        `).join("") || `<div class="empty">暂无节点</div>`}
      </div>
    </fieldset>
  `;
}


function userCard(user, nodes) {
  const metrics = user.metrics || {};
  const usedPercent = Number(metrics.used_percent || user.used_percent || 0);
  const clamped = Math.max(0, Math.min(100, usedPercent));
  return `
    <article class="admin-card">
      <div>
        <strong>${esc(user.username)}</strong>
        <span>${esc(user.status || "")} · ${esc(user.quota_status || "")}</span>
      </div>
      <p>${esc(user.plan_name || user.plan_id || "自定义套餐")} · ${esc(user.metrics?.days_left ?? "-")} 天</p>
      <div class="traffic-progress" aria-label="用户流量使用情况">
        <div>
          <span>已用 ${gb(metrics.used_bytes || user.used_bytes || 0)}</span>
          <span>${clamped.toFixed(clamped >= 10 ? 0 : 1)}%</span>
        </div>
        <i style="--traffic-width:${clamped}%"></i>
      </div>
      <p>今日流量：${gb(user.today_bytes || 0)} · 剩余 ${gb(metrics.remain_bytes || 0)}</p>
      <p>节点：${esc(userNodeText(user, nodes))}</p>
      <div class="admin-actions">
        <button class="secondary" data-action="user-edit" data-user="${esc(user.username)}" type="button">编辑</button>
        <button class="secondary" data-action="copy-subscription" data-text="${esc(user.raw_subscription_url || user.subscription_url || "")}" type="button">复制订阅</button>
        <button class="secondary" data-action="user-action" data-user="${esc(user.username)}" data-user-action="${user.enabled === false ? "enable" : "disable"}" type="button">${user.enabled === false ? "启用" : "禁用"}</button>
        <button class="secondary" data-action="user-action" data-user="${esc(user.username)}" data-user-action="extend" type="button">续 30 天</button>
        <button class="secondary" data-action="reset-sub" data-user="${esc(user.username)}" type="button">重置订阅</button>
        <button class="secondary" data-action="user-action" data-user="${esc(user.username)}" data-user-action="reset_traffic" type="button">清流量</button>
        <button class="secondary quiet-danger" data-action="user-action" data-user="${esc(user.username)}" data-user-action="delete" type="button">删除</button>
      </div>
    </article>
  `;
}


export function renderAdminUsers(data = {}) {
  const users = data.users || [];
  const plans = (data.plans || []).filter((plan) => plan.enabled !== false);
  const nodes = data.nodes || [];
  const query = data.filters?.users || "";
  const visibleUsers = users.filter((user) => matchesUser(user, query));
  const planOptions = plans.map((plan) => `<option value="${esc(plan.id || "")}">${esc(plan.name || plan.id || "")}</option>`).join("");
  return `
    <section class="screen stack">
      <div class="screen-head">
        <div><h1>用户</h1><p>创建、续费、订阅与节点授权。</p></div>
        <button class="primary" data-action="user-create-sheet" type="button">新建</button>
      </div>
      <article class="admin-card user-create-form" hidden>
        <div><strong>新建用户</strong><span>可以选择套餐；留空密码时系统生成一次性密码。</span></div>
        <form class="form-grid compact-form" data-form="user-create">
          <label>用户名<input name="username" autocomplete="off" required></label>
          <label>登录密码<input name="panel_password" type="password" placeholder="留空自动生成"></label>
          <label>套餐
            <select name="plan_id">
              <option value="">自定义</option>
              ${planOptions}
            </select>
          </label>
          <label>有效期天数<input name="days" inputmode="numeric" value="30"></label>
          <label>流量 GB<input name="traffic_gb" inputmode="decimal" value="0"></label>
          <label>备注<input name="note" placeholder="可选"></label>
          <div class="form-actions">
            <button class="primary" type="submit">创建用户</button>
            <button class="secondary" data-action="user-form-close" type="button">收起</button>
          </div>
        </form>
      </article>
      <article class="admin-card user-edit-form" hidden>
        <div><strong>快速编辑用户</strong><span>续费、改套餐、配额和精确授权节点。</span></div>
        <form class="form-grid compact-form" data-form="user-edit">
          <label>用户名<input name="username" readonly></label>
          <label>状态
            <select name="enabled">
              <option value="true">启用</option>
              <option value="false">禁用</option>
            </select>
          </label>
          <label>套餐
            <select name="plan_id">
              <option value="">不指定套餐</option>
              ${planOptions}
            </select>
          </label>
          <label>有效期天数<input name="days" inputmode="numeric" placeholder="留空不改"></label>
          <label>流量 GB<input name="quota_gb" inputmode="decimal" placeholder="留空按套餐或不改"></label>
          <label class="wide-field">备注<input name="note" placeholder="可选"></label>
          <div class="wide-field user-node-picker-slot">${nodePicker(nodes)}</div>
          <div class="form-actions">
            <button class="primary" type="submit">保存用户</button>
            <button class="secondary" data-action="user-form-close" type="button">收起</button>
          </div>
        </form>
      </article>
      <div class="toolbar"><input data-filter="users" value="${esc(query)}" placeholder="搜索用户"><button data-action="users-filter" type="button">筛选</button></div>
      <div class="card-list">${visibleUsers.map((user) => userCard(user, nodes)).join("") || `<article class="admin-card empty"><p>${users.length ? "没有匹配的用户" : "暂无用户"}</p><button data-action="user-create-sheet" type="button">创建用户</button></article>`}</div>
    </section>
  `;
}
