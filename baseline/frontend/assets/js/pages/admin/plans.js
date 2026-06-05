import { esc } from "../../components/layout.js";
import { money, statusPill } from "../../components/ui.js";


function groupsText(plan) {
  const groups = plan.node_groups || [];
  if (Array.isArray(groups)) return groups.join(",");
  return String(groups || "");
}


function matchesPlan(plan, query) {
  if (!query) return true;
  const haystack = [
    plan.id,
    plan.name,
    plan.days,
    plan.traffic_gb,
    plan.price,
    groupsText(plan),
    plan.enabled === false ? "停用 disabled" : "启用 enabled",
  ].join(" ").toLowerCase();
  return haystack.includes(query.toLowerCase());
}


function planCard(plan) {
  const enabled = plan.enabled !== false;
  const status = enabled ? "completed" : "cancelled";
  return `
    <article class="admin-card">
      <div>
        <strong>${esc(plan.name || plan.id || "-")}</strong>
        ${statusPill(status)}
      </div>
      <p>${esc(plan.id || "")} · ${esc(plan.days || 0)} 天 · ${esc(plan.traffic_gb || 0)} GB · ${money(plan.price || 0)}</p>
      <p>节点组：${esc(groupsText(plan) || "default")} · 排序 ${esc(plan.sort ?? 100)}</p>
      <div class="admin-actions">
        <button class="secondary" data-action="plan-edit" data-plan="${esc(plan.id || "")}" type="button">编辑</button>
        <button class="secondary" data-action="plan-action" data-plan="${esc(plan.id || "")}" data-plan-action="${enabled ? "disable" : "enable"}" type="button">${enabled ? "停用" : "启用"}</button>
        <button class="secondary quiet-danger" data-action="plan-action" data-plan="${esc(plan.id || "")}" data-plan-action="delete" type="button">删除</button>
      </div>
    </article>
  `;
}


export function renderAdminPlans(data = {}) {
  const plans = data.plans || [];
  const query = data.filters?.plans || "";
  const visiblePlans = plans.filter((plan) => matchesPlan(plan, query));
  return `
    <section class="screen stack">
      <div class="screen-head">
        <div><h1>套餐</h1><p>编辑价格、周期、流量和默认节点组。</p></div>
        <button class="primary" data-action="plan-create-sheet" type="button">新增套餐</button>
      </div>
      <article class="admin-card plan-edit-form" hidden>
        <div><strong>新增或编辑套餐</strong><span>ID 保存后不可直接改名；要改 ID 请新建套餐。</span></div>
        <form class="form-grid compact-form" data-form="plan-save">
          <label>套餐 ID<input name="id" autocomplete="off" placeholder="standard" required></label>
          <label>名称<input name="name" autocomplete="off" placeholder="Standard" required></label>
          <label>天数<input name="days" inputmode="numeric" placeholder="30" required></label>
          <label>流量 GB<input name="traffic_gb" inputmode="decimal" placeholder="300" required></label>
          <label>美元价格<input name="price" inputmode="decimal" placeholder="9.9" required></label>
          <label>节点组<input name="node_groups" placeholder="default,sg"></label>
          <label>排序<input name="sort" inputmode="numeric" placeholder="100"></label>
          <label>启用
            <select name="enabled">
              <option value="true">启用</option>
              <option value="false">停用</option>
            </select>
          </label>
          <div class="form-actions">
            <button class="primary" type="submit">保存套餐</button>
            <button class="secondary" data-action="plan-form-close" type="button">关闭</button>
          </div>
        </form>
      </article>
      <div class="toolbar">
        <input data-filter="plans" value="${esc(query)}" placeholder="搜索套餐、价格、节点组">
        <button data-action="plans-filter" type="button">筛选</button>
      </div>
      <div class="section-row"><h2>套餐列表</h2><span>${visiblePlans.length} / ${plans.length}</span></div>
      <div class="card-list">${visiblePlans.map(planCard).join("") || `<article class="admin-card empty"><p>${plans.length ? "没有匹配的套餐" : "暂无套餐"}</p><button data-action="plan-create-sheet" type="button">新增套餐</button></article>`}</div>
    </section>
  `;
}
