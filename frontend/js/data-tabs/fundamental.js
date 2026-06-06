/**
 * 数据中心 — 基本面 Tab
 * 依赖: api.js (API_BASE), common.js (escHtml), ECharts
 */
window.DataTabs = window.DataTabs || {};

DataTabs.Fundamental = {
  async load() {
    try {
      const [ovRes, distRes] = await Promise.all([
        fetch(`${API_BASE}/data/fundamental/overview`),
        fetch(`${API_BASE}/data/fundamental/distribution`),
      ]);
      const ovData = (await ovRes.json()).data || {};
      const distData = (await distRes.json()).data || {};

      // 摘要栏
      const total = distData.total_stocks || ovData.stocks?.length || 0;
      document.getElementById('fund-summary-bar').textContent =
        `${total}只股票 | PE中位数: ${this._median((ovData.stocks || []).map(s => s.pe_ttm).filter(v => v != null && v > 0)).toFixed(1)} | 行业数: ${(ovData.industries || []).length}`;

      // PE分桶图
      this._renderBuckets('fund-pe-chart', distData.pe_buckets || [], 'PE区间', '#60a5fa');
      // PB分桶图
      this._renderBuckets('fund-pb-chart', distData.pb_buckets || [], 'PB区间', '#2ed573');

      // 行业分布表
      this._renderIndustryTable(ovData.industries || []);

      // ROE排行
      this._renderROETable(distData.roe_top || []);

      // 估值一览表
      this._renderValuationTable(ovData.stocks || []);

    } catch (e) { console.error('[Fundamental]', e); }
  },

  _median(arr) {
    if (!arr.length) return 0;
    const sorted = [...arr].sort((a, b) => a - b);
    const mid = Math.floor(sorted.length / 2);
    return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
  },

  _renderBuckets(containerId, data, name, color) {
    const el = document.getElementById(containerId);
    if (!el) return;
    const existing = echarts.getInstanceByDom(el);
    if (existing) existing.dispose();

    if (!data.length) {
      el.innerHTML = '<div style="color:var(--text-micro);padding:20px;text-align:center;">无数据</div>';
      return;
    }

    const chart = echarts.init(el);
    chart.setOption({
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      grid: { left: '12%', right: '5%', top: '8%', bottom: '10%' },
      xAxis: { type: 'category', data: data.map(d => d.range), axisLabel: { fontSize: 10, color: '#999' } },
      yAxis: { type: 'value', splitLine: { lineStyle: { color: '#1a1a1a' } }, axisLabel: { fontSize: 9 } },
      series: [{
        type: 'bar', data: data.map(d => d.count),
        itemStyle: { color, borderRadius: [3, 3, 0, 0] },
        label: { show: true, position: 'top', color: '#ccc', fontSize: 10 },
      }]
    });
    window.addEventListener('resize', () => chart.resize());
  },

  _renderIndustryTable(industries) {
    const el = document.getElementById('fund-industry-table');
    if (!industries.length) {
      el.innerHTML = '<div style="color:var(--text-micro);padding:20px;">行业数据待同步</div>';
      return;
    }
    el.innerHTML = `<table class="health-table"><thead><tr><th>行业</th><th style="text-align:right;">数量</th><th style="text-align:right;">均PE</th><th style="text-align:right;">均市值(亿)</th></tr></thead>
      <tbody>${industries.map(i => `<tr><td>${escHtml(i.name)}</td><td style="text-align:right;">${i.count}</td><td style="text-align:right;">${i.avg_pe}</td><td style="text-align:right;">${Math.round(i.avg_mcap)}</td></tr>`).join('')}</tbody></table>`;
  },

  _renderROETable(roeList) {
    const el = document.getElementById('fund-roe-table');
    if (!roeList.length) {
      el.innerHTML = '<div style="color:var(--text-micro);padding:20px;">ROE数据待同步</div>';
      return;
    }
    el.innerHTML = `<table class="health-table"><thead><tr><th>#</th><th>代码</th><th>名称</th><th style="text-align:right;">ROE</th><th style="text-align:right;">PE</th><th style="text-align:right;">PB</th></tr></thead>
      <tbody>${roeList.map((s, i) => {
        const roeColor = s.roe > 15 ? 'var(--accent-green)' : s.roe > 8 ? 'var(--accent-gold)' : 'var(--accent-red)';
        return `<tr>
          <td style="color:var(--text-micro);">${i + 1}</td>
          <td style="color:var(--accent-blue);">${escHtml(s.code)}</td>
          <td>${escHtml(s.name)}</td>
          <td style="text-align:right;color:${roeColor};">${s.roe != null ? s.roe.toFixed(1) + '%' : '—'}</td>
          <td style="text-align:right;">${s.pe_ttm != null ? s.pe_ttm.toFixed(1) : '—'}</td>
          <td style="text-align:right;">${s.pb != null ? s.pb.toFixed(1) : '—'}</td>
        </tr>`;
      }).join('')}</tbody></table>`;
  },

  _renderValuationTable(stocks) {
    const el = document.getElementById('fund-valuation-table');
    if (!stocks.length) {
      el.innerHTML = '<div style="color:var(--text-micro);padding:20px;">估值数据从stock_info表加载</div>';
      return;
    }
    el.innerHTML = `<table class="health-table"><thead><tr><th>代码</th><th>名称</th><th>行业</th><th style="text-align:right;">PE</th><th style="text-align:right;">PB</th><th style="text-align:right;">市值(亿)</th></tr></thead>
      <tbody>${stocks.map(s => {
        const peColor = s.pe_ttm != null ? (s.pe_ttm < 0 ? 'var(--accent-red)' : s.pe_ttm > 50 ? 'var(--accent-gold)' : 'var(--accent-green)') : '';
        return `<tr>
          <td style="color:var(--accent-blue);">${escHtml(s.code)}</td><td style="color:#fff;">${escHtml(s.name)}</td>
          <td style="font-size:10px;color:var(--text-micro);">${escHtml(s.industry)}</td>
          <td style="text-align:right;color:${peColor};">${s.pe_ttm != null ? s.pe_ttm.toFixed(1) : '—'}</td>
          <td style="text-align:right;">${s.pb != null ? s.pb.toFixed(1) : '—'}</td>
          <td style="text-align:right;">${s.mcap_yi != null ? Math.round(s.mcap_yi) : '—'}</td>
        </tr>`;
      }).join('')}</tbody></table>`;
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
