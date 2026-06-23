import { esc } from "../../components/layout.js?v=3.0.2";
import { gb } from "../../components/ui.js?v=3.0.2";


function metricCard(label, value, sub, tone = "blue") {
  return `
    <article class="metric-card tone-${esc(tone)}">
      <span class="metric-icon" aria-hidden="true"></span>
      <div>
        <span>${esc(label)}</span>
        <strong>${esc(value)}</strong>
        <small>${esc(sub || "")}</small>
      </div>
    </article>
  `;
}


function topUsers(users = []) {
  return users.slice(0, 12).map((item, idx) => `
    <div class="rank-row">
      <span>${idx + 1}</span>
      <strong>${esc(item.username || "unknown")}</strong>
      <em>${gb(item.total_bytes || 0)}</em>
    </div>
  `).join("") || `<div class="empty">暂无用户流量样本</div>`;
}


function planRows(plans = {}) {
  return Object.entries(plans)
    .sort((a, b) => b[1] - a[1])
    .map(([name, count]) => `
      <div class="rank-row">
        <span></span>
        <strong>${esc(name)}</strong>
        <em>${esc(count)} 用户</em>
      </div>
    `).join("") || `<div class="empty">暂无套餐分布</div>`;
}


function asChart(data) {
  return esc(JSON.stringify(data || []));
}


function trafficLineChart(series) {
  return `<canvas data-chart-type="line" data-chart="${asChart(series || [])}" aria-label="用户流量趋势"></canvas>`;
}


function donutChart(items, label) {
  return `<canvas data-chart-type="donut" data-chart="${asChart(items || [])}" aria-label="${esc(label || "分布图")}"></canvas>`;
}


export function renderAdminOverview(data = {}) {
  const users = data.users || [];
  const orders = data.orders || [];
  const nodes = data.nodes || [];
  const payments = data.payments || [];
  const metrics = data.metrics || {};
  const traffic = data.traffic || {};
  const top = data.top_users || [];
  const nodeTraffic = data.node_traffic || [];
  const pending = orders.filter((order) => order.status === "pending").length;
  const enabledUsers = users.filter((user) => user.enabled !== false).length;
  const totalUsed = users.reduce((sum, user) => sum + Number(user.used_bytes || user.metrics?.used_bytes || 0), 0);
  const totalQuota = users.reduce((sum, user) => sum + Number(user.quota_bytes || user.metrics?.quota_bytes || 0), 0);
  const activeNodes = nodes.filter((node) => node.enabled !== false).length;
  const planChart = Object.entries(metrics.plans || {}).map(([name, value]) => ({ name, value }));
  return `
    <section class="screen commercial-dashboard stack">
      <div class="screen-head">
        <div><h1>管理控制台</h1><p>系统概览、用户流量、节点出口和商业运营数据。</p></div>
        <button class="secondary" data-action="refresh" type="button">刷新</button>
      </div>
      <div class="metric-grid">
        ${metricCard("用户", users.length, `${enabledUsers} 启用`, "green")}
        ${metricCard("总流量", gb(metrics.traffic_total_bytes || totalUsed), `配额 ${gb(totalQuota)}`, "blue")}
        ${metricCard("今日/近期样本", gb((traffic.series || []).reduce((sum, item) => sum + Number(item.total_bytes || 0), 0)), "按采集历史聚合", "orange")}
        ${metricCard("节点", nodes.length, `${activeNodes} 启用`, "purple")}
        ${metricCard("待处理订单", pending, `付款记录 ${payments.length}`, "red")}
        ${metricCard("面板状态", data.xray?.enabled ? "运行中" : "待检查", `${esc(data.hy2?.running || "HY2")}`, "green")}
      </div>
      <article class="traffic-toolbar admin-card">
        <div>
          <strong>时间范围</strong>
          <span>近 24 小时 · 按小时</span>
        </div>
        <div class="toolbar-actions">
          <button class="secondary" data-action="refresh" type="button">刷新</button>
          <button class="secondary" data-nav="users" type="button">用户管理</button>
        </div>
      </article>
      <div class="dashboard-grid">
        <article class="chart-panel wide">
          <div class="chart-head">
            <div><strong>用户流量趋势</strong><span>总量 / 下行 / 上行</span></div>
            <div class="chart-legend"><span>总量</span><span>下行</span><span>上行</span></div>
          </div>
          ${trafficLineChart(traffic.series || [])}
        </article>
        <article class="chart-panel">
          <div class="chart-head"><div><strong>套餐分布</strong><span>用户套餐结构</span></div></div>
          ${donutChart(planChart, "套餐分布")}
          <div class="rank-list">${planRows(metrics.plans || {})}</div>
        </article>
        <article class="chart-panel">
          <div class="chart-head"><div><strong>用户流量排行</strong><span>Top 12</span></div></div>
          <div class="rank-list user-traffic-rank">${topUsers(top)}</div>
        </article>
        <article class="chart-panel">
          <div class="chart-head"><div><strong>节点流量分布</strong><span>VLESS / HY2 / 出口节点</span></div></div>
          <div class="rank-list">
            ${nodeTraffic.slice(0, 10).map((item) => `
              <div class="rank-row">
                <span>${esc(item.source || "")}</span>
                <strong>${esc(item.name || item.node_id || "unknown")}</strong>
                <em>${gb(item.total_bytes || 0)}</em>
              </div>
            `).join("") || `<div class="empty">暂无节点流量样本</div>`}
          </div>
        </article>
      </div>
    </section>
  `;
}
