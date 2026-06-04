import { esc } from "../../components/layout.js";


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


export function renderAdminSettings(data = {}) {
  const methods = data.payment_methods || [];
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
      <div class="section-row"><h2>链上收款方式</h2><span>${methods.length}</span></div>
      <div class="card-list">${methods.map(methodCard).join("") || `<article class="admin-card empty"><p>暂无收款方式</p><button data-action="payment-method-sheet" type="button">添加收款</button></article>`}</div>
      <datalist id="payment-method-types">${methods.map((method) => `<option value="${esc(paymentType(method))}">${esc(method.id || "")}</option>`).join("")}</datalist>
    </section>
  `;
}
