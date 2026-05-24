/**
 * 数据中心 — 财务报告 Tab
 * 依赖: api.js (API_BASE), common.js (escHtml), core.js (DataTabs.Core.addLog)
 */
window.DataTabs = window.DataTabs || {};

DataTabs.Financial = {
  async initDropdown() {
    try {
      const r = await fetch(`${API_BASE}/data/watchlist`);
      const d = await r.json();
      const sel = document.getElementById('fin-select');
      sel.innerHTML = '<option value="">— 选择自选股 —</option>' +
        (d.data || []).map(i => `<option value="${i.stock_code}">${i.stock_code} ${i.stock_name}</option>`).join('');
    } catch (e) { /* ignore */ }
  },

  selectStock() {
    const code = document.getElementById('fin-select').value;
    if (code) DataTabs.Financial.load(code);
  },

  async syncSelected() {
    const sel = document.getElementById('fin-select');
    const code = sel.value;
    if (!code) { DataTabs.Core.addLog('请先选择自选股', 'warn'); return; }
    DataTabs.Core.addLog(`拉取 ${code} 财报...`, 'info');
    try {
      const r = await fetch(`${API_BASE}/data/financial/sync/${code}`, { method: 'POST' });
      const d = await r.json();
      DataTabs.Core.addLog(`${code}: ${d.data?.stored || 0} 季度已存储`, 'success');
      DataTabs.Financial.load(code);
    } catch (e) { DataTabs.Core.addLog(`失败: ${e.message}`, 'error'); }
  },

  async batchSync() {
    DataTabs.Core.addLog('批量拉取自选股财报...', 'info');
    try {
      const r = await fetch(`${API_BASE}/data/financial/sync`, { method: 'POST' });
      const d = await r.json();
      DataTabs.Core.addLog(`完成: ${d.data?.synced_stocks || 0}只 ${d.data?.total_quarters || 0}季度`, 'success');
    } catch (e) { DataTabs.Core.addLog(`失败: ${e.message}`, 'error'); }
  },

  async load(code) {
    const el = document.getElementById('financial-content');
    try {
      const r = await fetch(`${API_BASE}/data/financial/${code}?periods=12`);
      const d = await r.json();
      const rows = d.data || [];
      if (!rows.length) { el.innerHTML = '<div style="color:var(--text-micro);padding:40px;text-align:center;">无数据, 点击"拉取财报"</div>'; return; }
      el.innerHTML = `<table class="health-table">
        <thead><tr>
          <th>报告期</th><th>营收(亿)</th><th>净利润(亿)</th><th>毛利率</th><th>净利率</th>
          <th>现金流(亿)</th><th>存货(亿)</th><th>合同负债(亿)</th><th>应收(亿)</th>
          <th>总资产(亿)</th><th>负债(亿)</th><th>ROE</th>
        </tr></thead>
        <tbody>${rows.map(r => {
          const rev = (r.revenue || 0) / 1e8;
          const profit = (r.parent_profit || 0) / 1e8;
          const gm = r.revenue ? ((r.revenue - r.operate_cost) / r.revenue * 100).toFixed(1) : '—';
          const nm = r.revenue ? (profit * 1e8 / r.revenue * 100).toFixed(1) : '—';
          const ocf = (r.op_cashflow || 0) / 1e8;
          const inv = (r.inventory || 0) / 1e8;
          const cl = (r.contract_liability || 0) / 1e8;
          const ar = (r.accounts_receivable || 0) / 1e8;
          const ta = (r.total_assets || 0) / 1e8;
          const tl = (r.total_liabilities || 0) / 1e8;
          const roe = r.total_equity ? (profit * 1e8 / r.total_equity * 100).toFixed(1) : '—';
          const color = profit >= 0 ? 'var(--accent-green)' : 'var(--accent-red)';
          return `<tr>
            <td>${r.report_date} <span style="font-size:9px;color:var(--text-micro);">${r.report_type}</span></td>
            <td style="text-align:right;">${rev.toFixed(2)}</td>
            <td style="text-align:right;color:${color};">${profit.toFixed(2)}</td>
            <td style="text-align:right;">${gm}%</td><td style="text-align:right;">${nm}%</td>
            <td style="text-align:right;">${ocf.toFixed(2)}</td>
            <td style="text-align:right;">${inv.toFixed(2)}</td>
            <td style="text-align:right;">${cl.toFixed(2)}</td>
            <td style="text-align:right;">${ar.toFixed(2)}</td>
            <td style="text-align:right;">${ta.toFixed(2)}</td>
            <td style="text-align:right;">${tl.toFixed(2)}</td>
            <td style="text-align:right;">${roe}%</td>
          </tr>`;
        }).join('')}</tbody>
      </table>`;
    } catch (e) { el.innerHTML = '<div style="color:var(--accent-red);">加载失败</div>'; }
  }
};
