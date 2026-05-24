/**
 * 数据中心 — 自选股 Tab (V5.9: +备注/目标价/编辑)
 */
window.DataTabs = window.DataTabs || {};

DataTabs.Watchlist = {
  async load() {
    const el = document.getElementById('watchlist-table');
    try {
      const res = await fetch(`${API_BASE}/data/watchlist`);
      const data = await res.json();
      let items = data.data || [];
      const filterGroup = document.getElementById('wl-filter-group').value;
      const filterHeld = document.getElementById('wl-filter-held').checked;
      if (filterGroup) items = items.filter(i => (i.group_tag || '默认') === filterGroup);
      if (filterHeld) items = items.filter(i => i.is_held);

      const groups = [...new Set(data.data.map(i => i.group_tag || '默认'))];
      const sel = document.getElementById('wl-filter-group');
      const curVal = sel.value;
      sel.innerHTML = '<option value="">全部分组</option>' + groups.map(g => `<option>${g}</option>`).join('');
      sel.value = curVal;

      if (!items.length) { el.innerHTML = '<div style="color:var(--text-micro);padding:20px;text-align:center;">无匹配结果，从持仓导入或手动添加</div>'; return; }

      const grouped = {};
      items.forEach(i => { const g = i.group_tag || '默认'; if (!grouped[g]) grouped[g] = []; grouped[g].push(i); });
      el.innerHTML = Object.entries(grouped).map(([g, stocks]) => `
        <div class="panel" style="margin-bottom:6px;">
          <div class="panel-header"><span style="font-size:11px;">${escHtml(g)}</span><span style="font-size:9px;color:var(--text-micro);">(${stocks.length})</span></div>
          <div class="panel-body" style="padding:0;">
            <table class="watchlist-table">
              <thead><tr><th style="width:80px;">代码</th><th>名称</th><th style="width:130px;">备注</th><th style="text-align:right;width:65px;">现价</th><th style="text-align:right;width:65px;">涨跌</th><th style="text-align:right;width:70px;">市值(亿)</th><th style="text-align:right;width:55px;">PE</th><th style="text-align:right;width:70px;">营收(亿)</th><th style="text-align:right;width:55px;">净利率</th><th style="text-align:right;width:60px;">ROE</th><th style="text-align:right;width:70px;">目标价</th><th style="text-align:center;width:110px;">操作</th></tr></thead>
              <tbody>${stocks.map(s => {
                const pct = s.change_pct;
                const pc = pct != null ? (pct >= 0 ? 'var(--accent-green)' : 'var(--accent-red)') : 'var(--text-micro)';
                const ps = pct != null ? ((pct >= 0 ? '+' : '') + pct.toFixed(2) + '%') : '—';
                const rev = s.fin_revenue;
                const profit = s.fin_profit;
                const cost = s.fin_cost;
                const equity = s.fin_equity;
                const nm = rev ? (profit / rev * 100).toFixed(1) : '—';
                const roe = equity ? (profit / equity * 100).toFixed(1) : '—';
                const revYi = rev ? (rev / 1e8).toFixed(1) : '—';
                var tpLow = s.target_price_low != null ? s.target_price_low.toFixed(2) : '';
                var tpHigh = s.target_price_high != null ? s.target_price_high.toFixed(2) : '';
                var tpStr = (tpLow && tpHigh) ? tpLow + '~' + tpHigh : (tpLow || tpHigh || '—');
                return `<tr onclick="DataTabs.Watchlist.showChart('${escHtml(s.stock_code)}','${escHtml(s.stock_name)}')" title="点击查看K线">
                  <td style="width:80px;color:var(--accent-blue);">${escHtml(s.stock_code)}</td>
                  <td style="color:#fff;">${escHtml(s.stock_name)}${s.is_held ? '<span style="color:var(--accent-green);font-size:9px;">[持仓]</span>' : ''}</td>
                  <td style="font-size:10px;color:var(--text-dim);width:130px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;text-align:left;" title="${escHtml(s.notes||'')}">${escHtml((s.notes||'').substring(0,20)) || '—'}</td>
                  <td style="text-align:right;width:65px;">${s.price != null ? s.price.toFixed(2) : '—'}</td>
                  <td style="text-align:right;width:65px;color:${pc};">${ps}</td>
                  <td style="text-align:right;width:70px;">${s.mcap_yi != null ? Math.round(s.mcap_yi) : '—'}</td>
                  <td style="text-align:right;width:55px;">${s.pe_ttm != null ? s.pe_ttm.toFixed(1) : '—'}</td>
                  <td style="text-align:right;width:70px;">${revYi}</td>
                  <td style="text-align:right;width:55px;">${nm}%</td>
                  <td style="text-align:right;width:60px;">${roe}%</td>
                  <td style="text-align:right;width:70px;font-size:10px;color:var(--accent-gold);">${tpStr}</td>
                  <td style="text-align:center;width:110px;" onclick="event.stopPropagation();">
                    <button onclick="DataTabs.Watchlist.finDetail('${escHtml(s.stock_code)}','${escHtml(s.stock_name)}')" title="财务F10" style="background:none;border:none;color:var(--accent-gold);cursor:pointer;font-size:9px;"><i class="fas fa-file-invoice"></i></button>
                    <button onclick="DataTabs.Watchlist.syncOne('${escHtml(s.stock_code)}',this)" style="background:none;border:none;color:var(--accent-blue);cursor:pointer;font-size:9px;"><i class="fas fa-sync-alt"></i></button>
                    <button data-code="${escHtml(s.stock_code)}" onclick="DataTabs.Watchlist.edit(this.dataset.code)" title="编辑" style="background:none;border:none;color:var(--accent-gold);cursor:pointer;font-size:9px;"><i class="fas fa-edit"></i></button>
                    <button onclick="DataTabs.Watchlist.remove('${escHtml(s.stock_code)}')" style="background:none;border:none;color:var(--accent-red);cursor:pointer;font-size:9px;"><i class="fas fa-trash"></i></button>
                  </td>
                </tr>`;
              }).join('')}</tbody>
            </table>
          </div>
        </div>`).join('');
    } catch (e) { el.innerHTML = '<div style="color:var(--accent-red);">加载失败</div>'; }
  },

  async add() {
    const code = document.getElementById('wl-code').value.trim();
    if (!code) { DataTabs.Core.addLog('请输入代码', 'warn'); return; }
    const group = document.getElementById('wl-group').value.trim() || '默认';
    const notes = document.getElementById('wl-notes').value.trim();
    const tLow = document.getElementById('wl-target-low').value;
    const tHigh = document.getElementById('wl-target-high').value;
    let url = `${API_BASE}/data/watchlist/add?stock_code=${encodeURIComponent(code)}&group_tag=${encodeURIComponent(group)}`;
    if (notes) url += `&notes=${encodeURIComponent(notes)}`;
    if (tLow) url += `&target_price_low=${tLow}`;
    if (tHigh) url += `&target_price_high=${tHigh}`;
    try {
      const res = await fetch(url, { method: 'POST' });
      const d = await res.json();
      document.getElementById('wl-code').value = '';
      document.getElementById('wl-notes').value = '';
      document.getElementById('wl-target-low').value = '';
      document.getElementById('wl-target-high').value = '';
      DataTabs.Watchlist.load();
      DataTabs.Core.addLog(`已添加 ${code} (${d.name || ''})`, 'success');
    } catch (e) { DataTabs.Core.addLog(`添加失败: ${e.message}`, 'error'); }
  },

  async edit(code) {
    var current = {}, allGroups = [];
    try {
      var res = await fetch(API_BASE + '/data/watchlist');
      var d = await res.json();
      var items = d.data || [];
      current = items.find(function(i){return i.stock_code === code;}) || {};
      allGroups = [...new Set(items.map(function(i){return i.group_tag || '默认';}))];
    } catch(e) {}
    var cg = current.group_tag || '默认';
    var cn = current.notes || '';
    var cl = current.target_price_low || '';
    var ch = current.target_price_high || '';
    if (allGroups.indexOf(cg) < 0) allGroups.unshift(cg);
    var gOpts = allGroups.map(function(g){return '<option value="'+g+'"'+(g===cg?' selected':'')+'>'+g+'</option>';}).join('');
    var html = '<div style="display:flex;flex-direction:column;gap:8px;min-width:380px;">' +
      '<div style="color:#fff;font-size:13px;"><span style="font-family:var(--font-mono);color:var(--accent-blue);">'+code+'</span></div>' +
      '<label style="color:var(--text-dim);font-size:11px;">分组 <select id="editwl-group" onchange="var v=this.value;var inp=document.getElementById(\'editwl-new-group\');inp.style.display=v===\'__new__\'?\'\':\'none\'" style="background:#000;border:1px solid var(--border-color);color:#fff;padding:4px 8px;border-radius:3px;font-size:11px;width:100%;">'+gOpts+'<option value="__new__">+ 新建分组...</option></select></label>' +
      '<input id="editwl-new-group" placeholder="输入新分组名称" style="display:none;background:#000;border:1px solid var(--border-color);color:#fff;padding:4px 8px;border-radius:3px;font-size:11px;">' +
      '<label style="color:var(--text-dim);font-size:11px;">备注 <textarea id="editwl-notes" style="width:100%;background:#000;border:1px solid var(--border-color);color:#fff;padding:4px 8px;border-radius:3px;font-size:11px;" rows="2">'+cn+'</textarea></label>' +
      '<div style="display:flex;gap:8px;">' +
      '<label style="color:var(--text-dim);font-size:11px;flex:1;">目标价下限 <input id="editwl-low" type="number" step="0.01" value="'+cl+'" style="width:100%;background:#000;border:1px solid var(--border-color);color:#fff;padding:4px 8px;border-radius:3px;font-size:11px;"></label>' +
      '<label style="color:var(--text-dim);font-size:11px;flex:1;">目标价上限 <input id="editwl-high" type="number" step="0.01" value="'+ch+'" style="width:100%;background:#000;border:1px solid var(--border-color);color:#fff;padding:4px 8px;border-radius:3px;font-size:11px;"></label></div>' +
      '<div style="display:flex;gap:6px;justify-content:flex-end;">' +
      '<button class="btn-sm" onclick="Modal.close()" style="padding:6px 14px;">取消</button>' +
      '<button class="btn-primary" onclick="DataTabs.Watchlist.submitEdit(\''+code+'\')" style="font-size:11px;">保存</button></div></div>';
    Modal.custom({title: '编辑 ' + code, content: html});
  },

  async submitEdit(code) {
    var g = document.getElementById('editwl-group').value;
    if (g === '__new__') { g = document.getElementById('editwl-new-group').value.trim(); if (!g) return; }
    var n = document.getElementById('editwl-notes').value;
    var l = document.getElementById('editwl-low').value;
    var h = document.getElementById('editwl-high').value;
    var url = `${API_BASE}/data/watchlist/${code}?group_tag=${encodeURIComponent(g)}`;
    url += `&notes=${encodeURIComponent(n)}`;
    if (l) url += `&target_price_low=${l}`;
    if (h) url += `&target_price_high=${h}`;
    try {
      await fetch(url, { method: 'PUT' });
      Modal.close();
      DataTabs.Watchlist.load();
    } catch(e) { Modal.alert('错误', e.message); }
  },

  async importPositions() {
    try {
      const res = await fetch(`${API_BASE}/data/watchlist/import-positions`, { method: 'POST' });
      const d = await res.json();
      DataTabs.Watchlist.load();
      DataTabs.Core.addLog(`导入了 ${d.imported || 0} 条持仓`, 'success');
    } catch (e) { DataTabs.Core.addLog('导入失败', 'error'); }
  },

  async sync(mode) {
    DataTabs.Core.addLog(`自选股${mode === 'daily' ? '当日' : '历史'}同步中...`, 'info');
    try {
      const res = await fetch(`${API_BASE}/data/watchlist/sync?mode=${mode}`, { method: 'POST' });
      const d = await res.json();
      DataTabs.Core.addLog(`同步完成: ${d.synced || 0} 只`, 'success');
      DataTabs.Watchlist.load();
    } catch (e) { DataTabs.Core.addLog('同步失败', 'error'); }
  },

  async syncOne(code, btn) {
    if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>'; }
    try { await fetch(`${API_BASE}/data/sync/daily/${code}`, { method: 'POST' }); }
    catch (e) { /* ignore */ }
    DataTabs.Watchlist.load();
  },

  async refreshHeld() {
    await fetch(`${API_BASE}/data/watchlist/refresh-held`, { method: 'POST' });
    DataTabs.Watchlist.load();
  },

  async editGroup(code, currentGroup) { this.edit(code); },

  async remove(code) {
    if (!confirm('确认删除自选股 ' + code + '?')) return;
    await fetch(`${API_BASE}/data/watchlist/${code}`, { method: 'DELETE' });
    DataTabs.Watchlist.load();
  },

  async showChart(code, name) {
    try {
      const res = await fetch(`${API_BASE}/data/daily/${code}?limit=500`);
      const d = await res.json();
      const data = d.data || [];
      const modal = document.createElement('div');
      modal.innerHTML = `<div id="chart-modal-content" style="display:flex;flex-direction:column;gap:8px;">
        <div style="font-size:12px;color:#fff;">${escHtml(code)} ${escHtml(name)}</div>
        <div id="chart-container" style="width:750px;height:420px;"></div></div>`;
      Modal.custom({title: 'K线走势', content: modal.innerHTML});
      await new Promise(r => setTimeout(r, 100));
      const chartDom = document.getElementById('chart-container');
      if (!chartDom || !window.echarts) return;
      const chart = echarts.init(chartDom, 'dark');
      const dates = data.map(d => d.trade_date);
      chart.setOption({
        grid: { left: 60, right: 20, top: 20, bottom: 40 },
        xAxis: { type: 'category', data: dates, axisLabel: { fontSize: 9 } },
        yAxis: { type: 'value', scale: true },
        series: [{ type: 'candlestick', data: data.map(d => [d.open, d.close, d.low, d.high]),
          itemStyle: { color: '#ef5350', color0: '#26a69a', borderColor: '#ef5350', borderColor0: '#26a69a' } }],
        dataZoom: [{ type: 'inside' }, { type: 'slider', height: 20 }]
      });
    } catch(e) { /* ignore */ }
  },

  async finDetail(code, name) {
    try {
      const res = await fetch(`${API_BASE}/data/financial/${code}?periods=12`);
      const d = await res.json();
      const quarters = (d.data || []);
      if (!quarters.length) { Modal.alert('提示', '暂无财务数据'); return; }
      let rows = '';
      for (let i = 0; i < quarters.length; i++) {
        const q = quarters[i];
        const rev = (q.revenue / 1e8).toFixed(1);
        const prf = ((q.parent_profit || q.profit || 0) / 1e8).toFixed(2);
        const cost = q.operate_cost || 0;
        const gm = rev > 0 ? ((q.revenue - cost) / q.revenue * 100).toFixed(1) : '—';
        const nm = rev > 0 ? ((q.parent_profit || q.profit || 0) / q.revenue * 100).toFixed(1) : '—';
        const eq = q.total_equity || 1;
        const roe = ((q.parent_profit || q.profit || 0) / eq * 100).toFixed(1);
        const ocf = ((q.op_cashflow || 0) / 1e8).toFixed(1);
        const inv = ((q.inventory || 0) / 1e8).toFixed(1);
        const cl = ((q.contract_liability || 0) / 1e8).toFixed(1);
        rows += `<tr>
          <td style="font-size:10px;">${(q.report_date||'').substring(0,7)}</td>
          <td style="text-align:right;">${rev}</td>
          <td style="text-align:right;">${prf}</td>
          <td style="text-align:right;">${gm}%</td>
          <td style="text-align:right;">${nm}%</td>
          <td style="text-align:right;">${roe}%</td>
          <td style="text-align:right;">${ocf}</td>
          <td style="text-align:right;">${inv}</td>
          <td style="text-align:right;">${cl}</td>
        </tr>`;
      }
      const html = `<div style="max-height:55vh;overflow:auto;">
        <table class="watchlist-table" style="font-size:10px;">
          <thead><tr>
            <th>报告期</th><th style="text-align:right;">营收(亿)</th><th style="text-align:right;">净利润(亿)</th>
            <th style="text-align:right;">毛利率</th><th style="text-align:right;">净利率</th><th style="text-align:right;">ROE</th>
            <th style="text-align:right;">CF(亿)</th><th style="text-align:right;">存货(亿)</th><th style="text-align:right;">合同负债(亿)</th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table></div>`;
      Modal.custom({title: `财务F10: ${code} ${name}`, content: html});
    } catch(e) { Modal.alert('错误', '加载财务数据失败: ' + e.message); }
  }
};
