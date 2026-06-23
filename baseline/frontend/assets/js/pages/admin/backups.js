import { esc } from "../../components/layout.js?v=3.1.0";


function backupCard(item) {
  const sizeMb = ((Number(item.size || 0) || 0) / 1024 / 1024).toFixed(2);
  return `
    <article class="admin-card">
      <div>
        <strong>${esc(item.name || "-")}</strong>
        <span>${sizeMb} MB</span>
      </div>
      <p>${item.mtime ? esc(new Date(item.mtime * 1000).toLocaleString()) : "暂无时间"}</p>
      <div class="admin-actions">
        <button class="secondary" data-action="backup-download" data-backup="${esc(item.name || "")}" type="button">导出下载</button>
      </div>
    </article>
  `;
}


export function renderAdminBackups(data = {}) {
  const backups = data.backups || [];
  return `
    <section class="screen stack">
      <div class="screen-head">
        <div>
          <h1>备份</h1>
          <p>导出、导入和恢复面板运行数据。</p>
        </div>
        <button class="primary" data-action="backup-create" type="button">创建备份</button>
      </div>
      <article class="admin-card">
        <div>
          <strong>导入恢复</strong>
          <span>恢复前系统会自动创建一次安全备份。</span>
        </div>
        <form class="form-grid backup-import-form" data-form="backup-import">
          <label>备份文件<input name="backup_file" type="file" accept=".tgz,.gz,application/gzip"></label>
          <div class="form-actions">
            <button class="primary" type="submit">导入并恢复</button>
          </div>
        </form>
      </article>
      <div class="section-row"><h2>备份列表</h2><span>${backups.length} 个</span></div>
      <div class="card-list">${backups.map(backupCard).join("") || `<article class="admin-card empty"><p>暂无备份</p><button data-action="backup-create" type="button">创建备份</button></article>`}</div>
    </section>
  `;
}
