export function loginView() {
  return `
    <section class="login-screen">
      <form class="login-card" data-form="login">
        <div>
          <h1>fake-ui</h1>
          <p>单机多出口代理编排系统</p>
        </div>
        <label>账号<input name="username" autocomplete="username" required></label>
        <label>密码<input name="password" type="password" autocomplete="current-password" required></label>
        <button class="primary" type="submit">登录</button>
      </form>
    </section>
  `;
}
