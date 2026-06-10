/**
 * 数据中心 — 行情体检 Tab
 * 依赖: api.js (API_BASE), modal.js (Modal), common.js (escHtml), core.js (DataTabs.Core.addLog)
 */
window.DataTabs = window.DataTabs || {};

DataTabs.Health = {
  async quickSync(mode) {
    const code = document.getElementById('quick-stock-input').value.trim();
    if (!code) { DataTabs.Core.addLog('请输入代码', 'warn'); return; }
    const label = mode === 'full' ? '全量同步' : '智能同步';
    DataTabs.Core.addLog(`${label}: ${code}...`, 'info');
    try {
      const r = await SyncAPI.market([code], mode);
      DataTabs.Core.addLog(`${code}: +${r.synced || 0} 条新记录`, 'success');
      DataTabs.Health.update();
    } catch (e) { DataTabs.Core.addLog(`${code} 失败: ${e.message}`, 'error'); }
  },

  quickCompute() {
    var code = document.getElementById('quick-stock-input').value.trim();
    if (!code) { DataTabs.Core.addLog('请输入代码', 'warn'); return; }
    IndicatorCompute.openModal({ target_codes: [code], mode: 'snapshot' });
  },

  async update() {
    const tbody = document.getElementById('health-table-body');
    try {
      const [hRes, sRes] = await Promise.all([
        fetch(`${API_BASE}/data/health/stocks`),
        fetch(`${API_BASE}/data/health/overview`)
      ]);
      const stocks = await hRes.json();
      const overview = await sRes.json();
      document.getElementById('health-summary-bar').innerHTML =
        `已同步: ${overview.synced_stocks || 0}只 | 指标覆盖: ${overview.indicators_coverage || 0} | 估值覆盖: ${overview.valuation_coverage || 0} | 状态: ${overview.status}`;
      const statusBadge = { HEALTHY: '<span style="color:var(--accent-green);">● HEALTHY</span>', STALE: '<span style="color:var(--accent-gold);">● STALE</span>', GAP: '<span style="color:var(--accent-red);">● GAP</span>' };
      tbody.innerHTML = stocks.map(s => `<tr>
        <td><span style="font-weight:600;">${escHtml(s.stock_name || s.stock_code)}</span><br><small style="color:var(--text-micro);">${s.stock_code}</small></td>
        <td style="font-size:10px;color:var(--text-dim);">${s.earliest_date || '—'}<br>~ ${s.latest_date || '—'}</td>
        <td style="text-align:right;font-weight:600;">${s.latest_price ? '¥' + Number(s.latest_price).toFixed(2) : '—'}</td>
        <td style="text-align:center;">${statusBadge[s.status] || s.status}</td>
        <td style="text-align:center;">
          <button style="background:none;border:none;color:var(--accent-blue);cursor:pointer;font-size:10px;" onclick="DataTabs.Health.viewDetail('${s.stock_code}')" title="体检"><i class="fas fa-search"></i></button>
          <button style="background:none;border:none;color:var(--accent-gold);cursor:pointer;font-size:10px;" onclick="DataTabs.Health.quickSyncCode('${s.stock_code}')" title="同步"><i class="fas fa-sync-alt"></i></button>
        </td>
      </tr>`).join('');
    } catch (e) { tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--accent-red);">加载失败</td></tr>'; }
  },

  async quickSyncCode(code) {
    DataTabs.Core.addLog(`同步 ${code}...`, 'info');
    try {
      await SyncAPI.market([code], 'full');
      DataTabs.Core.addLog(`${code} 完成`, 'success');
      DataTabs.Health.update();
    } catch (e) { DataTabs.Core.addLog(`${code} 失败: ${e.message}`, 'error'); }
  },

  async viewDetail(code) {
    try {
      const res = await fetch(`${API_BASE}/data/health/${code}`);
      const d = await res.json();
      Modal.alert(`${code} 数据体检`,
        `行情: ${d.data_range?.from || '—'} ~ ${d.data_range?.to || '—'} (${d.data_range?.records || 0}条)\n` +
        `最新: 开${d.latest_quote?.open || '—'} 高${d.latest_quote?.high || '—'} 低${d.latest_quote?.low || '—'} 收${d.latest_quote?.close || '—'}\n` +
        `涨跌: ${d.latest_quote?.change_pct != null ? d.latest_quote.change_pct.toFixed(2) + '%' : '—'}`);
    } catch (e) { DataTabs.Core.addLog(`体检失败: ${e.message}`, 'error'); }
  }
};
