import { state } from "../state.js?v=3.0.2";
import { esc } from "./layout.js?v=3.0.2";


function notice() {
  if (!state.notice) return "";
  return `<div class="notice ${esc(state.notice.type)}">${esc(state.notice.message)}</div>`;
}


export function loginView() {
  const registrationEnabled = state.publicSettings?.registration_enabled === true;
  const passwordResetEnabled = state.publicSettings?.password_reset_enabled === true;
  if (state.route === "register") {
    return registerView(registrationEnabled);
  }
  if (state.route === "forgot") {
    return forgotView(passwordResetEnabled);
  }
  return `
    <section class="login-screen">
      ${notice()}
      <form class="login-card" data-form="login">
        <div>
          <h1>fake-ui</h1>
          <p>单机多出口代理编排系统</p>
        </div>
        <label>账号<input name="username" autocomplete="username" required></label>
        <label>密码<input name="password" type="password" autocomplete="current-password" required></label>
        <button class="primary" type="submit">登录</button>
        ${registrationEnabled ? `<a class="ghost-link" href="/register">注册账号</a>` : ""}
        ${passwordResetEnabled ? `<a class="ghost-link" href="/forgot">找回密码</a>` : ""}
      </form>
    </section>
  `;
}


function registerView(registrationEnabled) {
  if (!registrationEnabled) {
    return `
      <section class="login-screen">
        ${notice()}
        <div class="login-card">
          <div>
            <h1>注册已关闭</h1>
            <p>当前不开放新用户注册。</p>
          </div>
          <a class="ghost-link" href="/login">返回登录</a>
        </div>
      </section>
    `;
  }
  return `
    <section class="login-screen">
      ${notice()}
      <form class="login-card" data-form="register">
        <div>
          <h1>注册账号</h1>
          <p>注册后请回到登录页登录。</p>
        </div>
        <label>账号<input name="username" autocomplete="username" required></label>
        <label>密码<input name="password" type="password" autocomplete="new-password" minlength="8" required></label>
        <label>邮箱<input name="email" type="email" autocomplete="email"></label>
        <button class="primary" type="submit">注册</button>
        <a class="ghost-link" href="/login">返回登录</a>
      </form>
    </section>
  `;
}


function forgotView(passwordResetEnabled) {
  if (!passwordResetEnabled) {
    return `
      <section class="login-screen">
        ${notice()}
        <div class="login-card">
          <div>
            <h1>找回密码已关闭</h1>
            <p>当前不开放邮箱找回密码。</p>
          </div>
          <a class="ghost-link" href="/login">返回登录</a>
        </div>
      </section>
    `;
  }
  return `
    <section class="login-screen">
      ${notice()}
      <form class="login-card" data-form="password-reset-send">
        <div>
          <h1>发送验证码</h1>
          <p>输入账号或邮箱，验证码会发送到账号邮箱。</p>
        </div>
        <label>账号或邮箱<input name="username" autocomplete="username" required></label>
        <button class="primary" type="submit">发送验证码</button>
      </form>
      <form class="login-card" data-form="password-reset-confirm">
        <div>
          <h1>重置密码</h1>
          <p>填写邮箱验证码和新密码。</p>
        </div>
        <label>账号或邮箱<input name="username" autocomplete="username" required></label>
        <label>验证码<input name="code" inputmode="numeric" minlength="6" maxlength="6" required></label>
        <label>新密码<input name="new_password" type="password" autocomplete="new-password" minlength="8" required></label>
        <button class="primary" type="submit">重置密码</button>
        <a class="ghost-link" href="/login">返回登录</a>
      </form>
    </section>
  `;
}
