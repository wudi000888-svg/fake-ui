import { esc } from "../../components/layout.js?v=3.0.1";
import { gb } from "../../components/ui.js?v=3.0.1";


export function renderUserAccount(data = {}, shell = {}) {
  const profile = data.profile || {};
  return `
    <section class="screen stack">
      <div class="screen-head"><h1>账号</h1></div>
      <article class="mobile-card">
        <div>
          <strong>${esc(profile.username || shell.username || "")}</strong>
          <span>${esc(profile.status || "状态未知")}</span>
        </div>
        <button class="secondary" data-action="logout" type="button">退出</button>
      </article>
      <div class="detail-list">
        <div><span>当前套餐</span><strong>${esc(profile.plan_name || "-")}</strong></div>
        <div><span>邮箱</span><strong>${esc(profile.email || "-")}</strong></div>
        <div><span>到期时间</span><strong>${esc(profile.expires_at || "-")}</strong></div>
        <div><span>已用流量</span><strong>${gb(profile.used_bytes)}</strong></div>
        <div><span>剩余流量</span><strong>${gb(profile.remain_bytes)}</strong></div>
      </div>
      <article class="mobile-card">
        <div><strong>邮箱</strong><span>用于找回密码验证码。</span></div>
        <form class="form-grid" data-form="self-email">
          <label>邮箱<input name="email" type="email" autocomplete="email" value="${esc(profile.email || "")}"></label>
          <button class="secondary" type="submit">保存邮箱</button>
        </form>
      </article>
      <article class="mobile-card">
        <div><strong>修改密码</strong><span>需要先输入当前登录密码。</span></div>
        <form class="form-grid" data-form="self-password">
          <label>当前密码<input name="old_password" type="password" autocomplete="current-password" required></label>
          <label>新密码<input name="new_password" type="password" autocomplete="new-password" minlength="8" required></label>
          <label>确认新密码<input name="new_password_confirm" type="password" autocomplete="new-password" minlength="8" required></label>
          <button class="secondary" type="submit">更新密码</button>
        </form>
      </article>
      <article class="mobile-card">
        <div><strong>安全建议</strong><span>定期更换面板密码，订阅链接泄露后请联系管理员重置。</span></div>
        <button class="secondary" data-action="refresh" type="button">刷新账号</button>
      </article>
    </section>
  `;
}
