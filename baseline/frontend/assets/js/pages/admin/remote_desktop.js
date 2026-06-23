import { esc } from "../../components/layout.js?v=3.1.0";


function matchesDevice(device, query) {
  if (!query) return true;
  const haystack = [
    device.id,
    device.name,
    device.role,
    device.platform,
    device.desktop_protocol,
    device.wg_ip,
    device.hysteria_user,
  ].join(" ").toLowerCase();
  return haystack.includes(query.toLowerCase());
}


function platformLabel(platform) {
  return { macos: "macOS", linux: "Linux", windows: "Windows" }[platform] || platform || "macOS";
}


function roleLabel(role) {
  return { controller: "控制端", host: "被控主机", both: "双向设备" }[role] || role || "被控主机";
}


function protocolLabel(protocol) {
  return {
    sunshine: "Sunshine",
    rdp: "RDP",
    vnc: "VNC",
    rustdesk: "RustDesk",
    ssh: "SSH",
    custom: "自定义",
  }[protocol] || protocol || "Sunshine";
}


function topologyCard(topology = {}) {
  return `
    <article class="admin-card">
      <div>
        <strong>网络拓扑</strong>
        <span>${esc(topology.transport || "Hysteria2 UDP 443")} · ${esc(topology.overlay || "WireGuard")}</span>
      </div>
      <p>TCP 443 继续给 Nginx、Xray Reality、面板和本地服务发布使用；UDP 443 独立给 Hysteria2 承载远程访问流量，两边互不占端口。</p>
      <div class="stat-grid">
        <div class="stat-tile"><span>公网入口</span><strong>Hysteria2 UDP 443</strong></div>
        <div class="stat-tile"><span>虚拟内网</span><strong>WireGuard</strong></div>
        <div class="stat-tile"><span>桌面协议</span><strong>Sunshine / Moonlight</strong></div>
        <div class="stat-tile"><span>兼容系统</span><strong>macOS / Linux / Windows</strong></div>
      </div>
    </article>
  `;
}


function guideCard() {
  return `
    <article class="admin-card tunnel-guide-card">
      <div>
        <strong>使用教程</strong>
        <span>新 VPS、任意域名、任意客户机器都按这套流程</span>
      </div>
      <div class="tunnel-steps">
        <div class="tunnel-step">
          <b>1</b>
          <div><strong>添加设备</strong><p>给控制端和被控主机分别分配 WireGuard IP。IP 只要在同一个私有网段且不重复即可，不需要公网 IP，也不需要给每台设备解析域名。</p></div>
        </div>
        <div class="tunnel-step">
          <b>2</b>
          <div><strong>应用远程访问配置</strong><p>点击“应用远程访问配置”，面板会把这些设备的 <code>desktop-*</code> 账号合并进 Hysteria2。普通代理用户和本地服务发布配置不会被覆盖。</p></div>
        </div>
        <div class="tunnel-step">
          <b>3</b>
          <div><strong>下载本地客户端</strong><p>每台设备下载自己的客户端包。包内包含 <code>hysteria-desktop.yaml</code>、<code>wireguard.conf</code> 和三端启动脚本。</p></div>
        </div>
        <div class="tunnel-step">
          <b>4</b>
          <div><strong>发起远程访问</strong><p>被控主机运行 Sunshine、RDP、VNC 或其他桌面服务；控制端使用 Moonlight、系统远程桌面或对应客户端访问对方 WireGuard IP。</p></div>
        </div>
      </div>
      <div class="tunnel-platform-grid">
        <div class="tunnel-platform">
          <strong>macOS</strong>
          <p>安装 Hysteria2 与 WireGuard，运行 <code>macos/start.sh</code> 后导入 <code>wireguard.conf</code>。</p>
        </div>
        <div class="tunnel-platform">
          <strong>Linux</strong>
          <p>安装 Hysteria2 与 WireGuard tools，运行 <code>linux/start.sh</code>，再用系统网络管理器或 <code>wg-quick</code> 导入配置。</p>
        </div>
        <div class="tunnel-platform">
          <strong>Windows</strong>
          <p>安装 Hysteria2 与 WireGuard for Windows，用 PowerShell 运行 <code>windows/start-windows.ps1</code>，再导入配置。</p>
        </div>
      </div>
    </article>
  `;
}


function networkCard(network = {}) {
  return `
    <article class="admin-card">
      <div>
        <strong>远程访问网络设置</strong>
        <span>VPS 作为虚拟内网 hub，客户端通过 Hysteria2 UDP 443 连到这里</span>
      </div>
      <form class="form-grid compact-form" data-form="desktop-network-save">
        <label>虚拟网段<input name="wg_network" value="${esc(network.wg_network || "10.77.0.0/24")}" required></label>
        <label>VPS WireGuard IP<input name="server_wg_ip" value="${esc(network.server_wg_ip || "10.77.0.1")}" required></label>
        <label>VPS 监听端口<input name="server_listen_port" inputmode="numeric" value="${esc(network.server_listen_port || "51820")}" required></label>
        <label>VPS WireGuard 私钥<input name="server_wg_private_key" value="${esc(network.server_wg_private_key || "")}" autocomplete="off" placeholder="wg genkey 生成"></label>
        <label>VPS WireGuard 公钥<input name="server_wg_public_key" value="${esc(network.server_wg_public_key || "")}" autocomplete="off" placeholder="wg pubkey 生成"></label>
        <p class="form-note">新 VPS 可先在服务器执行 <code>wg genkey | tee privatekey | wg pubkey > publickey</code>，把私钥和公钥填到这里。设备公钥在各设备生成后回填到设备表单。</p>
        <div class="form-actions">
          <button class="primary" type="submit">保存网络设置</button>
        </div>
      </form>
    </article>
  `;
}


function deviceCard(device) {
  const status = device.enabled === false ? "停用" : "启用";
  return `
    <article class="admin-card node-admin-card">
      <div>
        <strong>${esc(device.display_name || device.name || device.id)}</strong>
        <span>${esc(platformLabel(device.platform))} · ${esc(roleLabel(device.role))} · ${esc(status)}</span>
      </div>
      <p>${esc(protocolLabel(device.desktop_protocol))} ${esc(device.desktop_port || "")} · WireGuard ${esc(device.wg_ip || "")} · Hysteria2 ${esc(device.hysteria_user || "")}</p>
      <div class="admin-actions">
        <button class="secondary" data-action="desktop-edit" data-desktop="${esc(device.id)}" type="button">编辑</button>
        <button class="secondary" data-action="desktop-wireguard-export" data-desktop="${esc(device.id)}" type="button">导出网络配置</button>
        <button class="primary" data-action="desktop-bundle-export" data-desktop="${esc(device.id)}" type="button">下载本地客户端</button>
        <button class="secondary" data-action="desktop-action" data-desktop="${esc(device.id)}" data-desktop-action="${device.enabled === false ? "enable" : "disable"}" type="button">${device.enabled === false ? "启用" : "停用"}</button>
        <button class="secondary quiet-danger" data-action="desktop-action" data-desktop="${esc(device.id)}" data-desktop-action="delete" type="button">删除</button>
      </div>
    </article>
  `;
}


export function renderAdminRemoteDesktop(data = {}) {
  const devices = data.desktops || [];
  const network = data.desktop_network || {};
  const topology = data.desktop_topology || {};
  const query = data.filters?.desktops || "";
  const visible = devices.filter((device) => matchesDevice(device, query));
  return `
    <section class="screen stack">
      <div class="screen-head">
        <div><h1>远程访问</h1><p>用 Hysteria2 UDP 443 承载 WireGuard 虚拟内网，再跑 Sunshine、Moonlight、RDP 或 VNC。</p></div>
        <div class="admin-actions">
          <button class="secondary" data-action="desktop-server-wireguard-export" type="button">导出 VPS WireGuard</button>
          <button class="secondary" data-action="desktop-apply-wireguard" type="button">应用 VPS WireGuard</button>
          <button class="secondary" data-action="desktop-apply" type="button">应用远程访问配置</button>
          <button class="primary" data-action="desktop-create-sheet" type="button">新增访问设备</button>
        </div>
      </div>
      ${topologyCard(topology)}
      ${guideCard()}
      ${networkCard(network)}
      <article class="admin-card remote-desktop-edit-form" hidden>
        <div><strong>编辑远程访问设备</strong><span>这些参数只描述客户自己的设备，不绑定任何固定域名或机器。</span></div>
        <form class="form-grid compact-form" data-form="desktop-save">
          <label>设备名称<input name="name" autocomplete="off" placeholder="办公室主机"></label>
          <label>设备 ID<input name="id" autocomplete="off" placeholder="office-host"></label>
          <label>启用状态<select name="enabled"><option value="true">启用</option><option value="false">停用</option></select></label>
          <label>角色<select name="role"><option value="host">被控主机</option><option value="controller">控制端</option><option value="both">双向设备</option></select></label>
          <label>系统<select name="platform"><option value="macos">macOS</option><option value="linux">Linux</option><option value="windows">Windows</option></select></label>
          <label>桌面协议<select name="desktop_protocol"><option value="sunshine">Sunshine</option><option value="rdp">RDP</option><option value="vnc">VNC</option><option value="rustdesk">RustDesk</option><option value="ssh">SSH</option><option value="custom">自定义</option></select></label>
          <label>桌面端口<input name="desktop_port" inputmode="numeric" placeholder="留空按协议默认"></label>
          <label>WireGuard IP<input name="wg_ip" required placeholder="10.77.0.20"></label>
          <label>WireGuard 私钥<input name="wg_private_key" autocomplete="off" placeholder="可留空后在客户端替换"></label>
          <label>WireGuard 公钥<input name="wg_public_key" autocomplete="off" placeholder="可保存后补充"></label>
          <label>预共享密钥<input name="wg_preshared_key" autocomplete="off" placeholder="可选"></label>
          <label>本地 WG 监听端口<input name="listen_port" inputmode="numeric" value="51820"></label>
          <label>VPS WG 转发端口<input name="remote_port" inputmode="numeric" value="51820"></label>
          <div class="form-actions">
            <button class="primary" type="submit">保存设备</button>
            <button class="secondary" data-action="desktop-form-close" type="button">收起</button>
          </div>
        </form>
      </article>
      <div class="toolbar"><input data-filter="desktops" value="${esc(query)}" placeholder="搜索设备、系统、WireGuard IP 或 Hysteria2 用户"><button data-action="desktops-filter" type="button">筛选</button></div>
      <section class="tunnel-section stack">
        <div class="section-title"><h2>设备</h2><p>每台参与远程桌面的电脑或服务器都在这里占一个设备；macOS、Linux、Windows 使用同一套网络模型。</p></div>
        <div class="card-list">${visible.map(deviceCard).join("") || `<article class="admin-card empty"><p>${devices.length ? "没有匹配的远程访问设备" : "暂无远程访问设备"}</p><button data-action="desktop-create-sheet" type="button">新增访问设备</button></article>`}</div>
      </section>
    </section>
  `;
}
