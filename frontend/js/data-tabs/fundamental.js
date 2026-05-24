/**
 * 数据中心 — 基本面 Tab
 * 依赖: api.js (API_BASE), common.js (escHtml)
 */
window.DataTabs = window.DataTabs || {};

DataTabs.Fundamental = {
  async load() {
    try {
      const r = await fetch(`${API_BASE}/data/fundamental/overview`);
      const d = await r.json();
      const data = d.data || {};
      const industries = data.industries || [];
      const stocks = data.stocks || [];

      document.getElementById('fund-industry-table').innerHTML = industries.length
        ? `<table class="health-table"><thead><tr><th>行业</th><th style="text-align:right;">数量</th><th style="text-align:right;">均PE</th><th style="text-align:right;">均市值(亿)</th></tr></thead>
            <tbody>${industries.map(i => `<tr><td>${escHtml(i.name)}</td><td style="text-align:right;">${i.count}</td><td style="text-align:right;">${i.avg_pe}</td><td style="text-align:right;">${Math.round(i.avg_mcap)}</td></tr>`).join('')}</tbody></table>`
        : '<div style="color:var(--text-micro);padding:20px;">行业数据待同步</div>';

      document.getElementById('fund-valuation-table').innerHTML = stocks.length
        ? `<table class="health-table"><thead><tr><th>代码</th><th>名称</th><th>行业</th><th style="text-align:right;">PE</th><th style="text-align:right;">PB</th><th style="text-align:right;">市值(亿)</th></tr></thead>
            <tbody>${stocks.map(s => `<tr>
              <td style="color:var(--accent-blue);">${escHtml(s.code)}</td><td style="color:#fff;">${escHtml(s.name)}</td>
              <td style="font-size:10px;color:var(--text-micro);">${escHtml(s.industry)}</td>
              <td style="text-align:right;">${s.pe_ttm != null ? s.pe_ttm.toFixed(1) : '—'}</td>
              <td style="text-align:right;">${s.pb != null ? s.pb.toFixed(1) : '—'}</td>
              <td style="text-align:right;">${s.mcap_yi != null ? Math.round(s.mcap_yi) : '—'}</td>
            </tr>`).join('')}</tbody></table>`
        : '<div style="color:var(--text-micro);padding:20px;">估值数据从stock_info表加载</div>';
    } catch (e) { console.error('[Fundamental]', e); }
  },

  async syncIndustry() {
    DataTabs.Core.addLog('同步行业信息...', 'info');
    try {
      const r = await fetch(`${API_BASE}/data/stock-info/sync`, { method: 'POST' });
      const d = await r.json();
      DataTabs.Core.addLog(`行业同步完成: ${d.synced || 0}/${d.total || 0}只`, 'success');
      this.load();
    } catch (e) { DataTabs.Core.addLog(`行业同步失败: ${e.message}`, 'error'); }
  }
};
