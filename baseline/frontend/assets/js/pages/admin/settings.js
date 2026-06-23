import { esc } from "../../components/layout.js?v=3.1.0";


function paymentType(method) {
  return `${String(method.asset || "").toUpperCase()}:${String(method.chain || "").toLowerCase()}`;
}


function methodCard(method) {
  return `
    <article class="admin-card">
      <div>
        <strong>${esc(method.asset || "")} / ${esc(method.chain || "")}</strong>
        <span>${method.enabled ? "启用" : "停用"} · ${esc(method.id || "")}</span>
      </div>
      <p>${esc(method.address || "")}</p>
      <div class="admin-actions">
        <button class="secondary" data-action="payment-method-edit" data-method="${esc(method.id || "")}" type="button">编辑</button>
        <button class="secondary" data-action="payment-method-action" data-method="${esc(method.id || "")}" data-method-action="${method.enabled ? "disable" : "enable"}" type="button">${method.enabled ? "停用" : "启用"}</button>
        <button class="secondary quiet-danger" data-action="payment-method-action" data-method="${esc(method.id || "")}" data-method-action="delete" type="button">删除</button>
      </div>
    </article>
  `;
}


function paymentMethodsSettings(methods) {
  return `
    <div class="section-row"><h2>链上收款方式</h2><span>${methods.length}</span></div>
    <div class="card-list">${methods.map(methodCard).join("") || `<article class="admin-card empty"><p>暂无收款方式</p><button data-action="payment-method-sheet" type="button">添加收款</button></article>`}</div>
  `;
}


export function renderAdminSettings(data = {}) {
  const methods = data.payment_methods || [];
  const publicSettings = data.public_settings || {};
  const emailSettings = data.email_settings || {};
  return `
    <section class="screen stack">
      <div class="screen-head">
        <div><h1>设置</h1><p>链上收款、缓存和运营参数。</p></div>
        <button class="primary" data-action="payment-method-sheet" type="button">添加收款</button>
      </div>
      <article class="admin-card">
        <div><strong>缓存</strong><span>Dashboard / RPC / 汇率</span></div>
        <button class="secondary" data-action="cache-clear" type="button">清理缓存</button>
      </article>
      <article class="admin-card">
        <div><strong>修改密码</strong><span>更新当前管理员登录密码。</span></div>
        <form class="form-grid" data-form="self-password">
          <label>当前密码<input name="old_password" type="password" autocomplete="current-password" required></label>
          <label>新密码<input name="new_password" type="password" autocomplete="new-password" minlength="8" required></label>
          <label>确认新密码<input name="new_password_confirm" type="password" autocomplete="new-password" minlength="8" required></label>
          <button class="secondary" type="submit">更新密码</button>
        </form>
      </article>
      <article class="admin-card">
        <div><strong>公开注册</strong><span>${publicSettings.registration_enabled ? "已开启" : "已关闭"}</span></div>
        <form class="form-grid" data-form="public-settings-save">
          <label>允许用户注册
            <select name="registration_enabled">
              <option value="false" ${publicSettings.registration_enabled ? "" : "selected"}>关闭</option>
              <option value="true" ${publicSettings.registration_enabled ? "selected" : ""}>开启</option>
            </select>
          </label>
          <button class="secondary" type="submit">保存公开设置</button>
        </form>
      </article>
      <article class="admin-card">
        <div><strong>找回密码</strong><span>${publicSettings.password_reset_enabled ? "已开启" : "已关闭"} · SMTP ${publicSettings.smtp_configured ? "已配置" : "未配置"}</span></div>
        <form class="form-grid" data-form="email-settings-save">
          <label>允许邮箱找回
            <select name="password_reset_enabled">
              <option value="false" ${publicSettings.password_reset_enabled ? "" : "selected"}>关闭</option>
              <option value="true" ${publicSettings.password_reset_enabled ? "selected" : ""}>开启</option>
            </select>
          </label>
          <label>服务商
            <select name="email_provider">
              <option value="" ${emailSettings.email_provider ? "" : "selected"}>未选择</option>
              <option value="smtp" ${emailSettings.email_provider === "smtp" ? "selected" : ""}>SMTP</option>
            </select>
          </label>
          <label>SMTP 主机<input name="smtp_host" value="${esc(emailSettings.smtp_host || "")}"></label>
          <label>SMTP 端口<input name="smtp_port" inputmode="numeric" value="${esc(emailSettings.smtp_port || "587")}"></label>
          <label>SMTP 用户<input name="smtp_username" value="${esc(emailSettings.smtp_username || "")}"></label>
          <label>SMTP 密码<input name="smtp_password" type="password" autocomplete="new-password" placeholder="${publicSettings.smtp_configured ? "留空则不修改" : ""}"></label>
          <label>发件邮箱<input name="smtp_from" type="email" value="${esc(emailSettings.smtp_from || "")}"></label>
          <label>TLS
            <select name="smtp_tls">
              <option value="true" ${emailSettings.smtp_tls === false ? "" : "selected"}>开启</option>
              <option value="false" ${emailSettings.smtp_tls === false ? "selected" : ""}>关闭</option>
            </select>
          </label>
          <button class="secondary" type="submit">保存邮箱设置</button>
        </form>
      </article>
      <article class="admin-card payment-method-form" hidden>
        <div>
          <strong>添加或更新收款方式</strong>
          <span>只填写收款地址；RPC、合约、小数位和确认数由系统预设。</span>
        </div>
        <form class="form-grid" data-form="payment-method-save">
          <label>支付类型
            <select name="payment_type">
              <option value="USDT:bsc">USDT / BNB Smart Chain</option>
              <option value="USDT:ethereum">USDT / Ethereum mainnet</option>
              <option value="USDC:bsc">USDC / BNB Smart Chain</option>
              <option value="USDC:ethereum">USDC / Ethereum mainnet</option>
              <option value="BTC:bitcoin">BTC / Bitcoin</option>
              <option value="ETH:ethereum">ETH / Ethereum mainnet</option>
              <option value="BNB:bsc">BNB / BNB Smart Chain</option>
            </select>
          </label>
          <label>收款地址
            <input name="address" placeholder="0x... / bc1..." required>
          </label>
          <label>启用
            <select name="enabled">
              <option value="true">启用</option>
              <option value="false">停用</option>
            </select>
          </label>
          <button class="primary" type="submit">保存收款方式</button>
        </form>
      </article>
      ${paymentMethodsSettings(methods)}
      <datalist id="payment-method-types">${methods.map((method) => `<option value="${esc(paymentType(method))}">${esc(method.id || "")}</option>`).join("")}</datalist>
    </section>
  `;
}
