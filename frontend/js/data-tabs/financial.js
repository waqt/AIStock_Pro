/**
 * 数据中心 — 财务报告 Tab
 * 依赖: api.js (API_BASE), common.js (escHtml), core.js (DataTabs.Core.addLog), ECharts
 */
window.DataTabs = window.DataTabs || {};

DataTabs.Financial = {
  _currentCode: '',

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
    this._currentCode = code;
    if (code) this.load(code);
  },

  async syncSelected() {
    const sel = document.getElementById('fin-select');
    const code = sel.value;
    if (!code) { DataTabs.Core.addLog('请先选择自选股', 'warn'); return; }
    DataTabs.Core.addLog(`拉取 ${code} 财报...`, 'info');
    try {
      const r = await SyncAPI.financial([code], 'smart');
      DataTabs.Core.addLog(`${code}: ${r.stored || 0} 季度已存储`, 'success');
      this.load(code);
    } catch (e) { DataTabs.Core.addLog(`失败: ${e.message}`, 'error'); }
  },

  async batchSync() {
    DataTabs.Core.addLog('批量拉取自选股财报...', 'info');
    try {
      const r = await SyncAPI.financial(null, 'smart');
      DataTabs.Core.addLog(`完成: ${r.stored || 0} 季度`, 'success');
    } catch (e) { DataTabs.Core.addLog(`失败: ${e.message}`, 'error'); }
  },

  async load(code) {
    const codeToLoad = code || this._currentCode;
    if (!codeToLoad) return;
    try {
      const r = await fetch(`${API_BASE}/data/financial/${codeToLoad}?periods=12`);
      const d = await r.json();
      var rows = d.data || [];
      var contentEl = document.getElementById('financial-content');
      if (!rows.length) {
        contentEl.innerHTML = '<div style="color:var(--text-micro);padding:40px;text-align:center;">无数据, 点击"拉取财报"</div>';
        return;
      }

      // 反转: newest-first → chronological
      var reversed = [...rows].reverse();

      // 摘要栏
      var latest = rows[0];
      document.getElementById('fin-summary-bar').textContent =
        '最新报告期: ' + latest.report_date + ' | 营收: ' + ((latest.revenue || 0) / 1e8).toFixed(2) + '亿 | 净利: ' + ((latest.parent_profit || 0) / 1e8).toFixed(2) + '亿';

      // KPI 卡片
      this._renderKPICards(rows);

      // 趋势图
      this._renderRevenueChart(reversed);
      this._renderMarginChart(reversed);
      this._renderCashflowChart(reversed);
      this._renderRDChart(reversed);

      // 明细表
      this._renderTable(rows);

    } catch (e) {
      console.error('[Financial]', e);
      var tableEl = document.getElementById('financial-table');
      if (tableEl) tableEl.innerHTML = '<div style="color:var(--accent-red);">加载失败</div>';
    }
  },

  _renderKPICards: function(rows) {
    var latest = rows[0];
    var prev = rows.length > 4 ? rows[4] : null; // YoY comparison
    var el = document.getElementById('fin-kpi-cards');
    if (!latest || !el) return;

    var rev = (latest.revenue || 0) / 1e8;
    var profit = (latest.parent_profit || 0) / 1e8;
    var prevRev = prev ? (prev.revenue || 0) / 1e8 : null;
    var prevProfit = prev ? (prev.parent_profit || 0) / 1e8 : null;
    var revGrowth = (prevRev && prevRev > 0) ? ((rev - prevRev) / prevRev * 100).toFixed(1) : null;
    var profitGrowth = (prevProfit && prevProfit > 0) ? ((profit - prevProfit) / prevProfit * 100).toFixed(1) : null;
    var gm = latest.revenue ? ((latest.revenue - latest.operate_cost) / latest.revenue * 100).toFixed(1) : null;
    var nm = latest.revenue ? (profit * 1e8 / latest.revenue * 100).toFixed(1) : null;
    var ocf = (latest.op_cashflow || 0) / 1e8;
    var inv = (latest.inventory || 0) / 1e8;
    var rceipt = (latest.accounts_receivable || 0) / 1e8;

    var cards = [
      { label: '营收(TTM)', value: rev.toFixed(2) + '亿', color: '#60a5fa' },
      { label: '净利(TTM)', value: profit.toFixed(2) + '亿', color: profit >= 0 ? '#2ed573' : '#ff4757' },
      { label: '营收同比', value: revGrowth ? revGrowth + '%' : '—', color: revGrowth > 0 ? '#2ed573' : '#ff4757' },
      { label: '净利同比', value: profitGrowth ? profitGrowth + '%' : '—', color: profitGrowth > 0 ? '#2ed573' : '#ff4757' },
      { label: '毛利率', value: gm ? gm + '%' : '—', color: '#ffa502' },
      { label: '净利率', value: nm ? nm + '%' : '—', color: '#70a1ff' },
      { label: '经营现金流', value: ocf.toFixed(2) + '亿', color: ocf >= 0 ? '#2ed573' : '#ff4757' },
      { label: '合同负债', value: ((latest.contract_liability || 0) / 1e8).toFixed(2) + '亿', color: '#ffa502' },
    ];

    el.innerHTML = cards.map(function(c) {
      return '<div class="macro-card" style="flex:1;min-width:72px;padding:8px 10px;">' +
        '<div class="label">' + c.label + '</div>' +
        '<div class="value" style="font-size:13px;color:' + c.color + ';">' + c.value + '</div></div>';
    }).join('');
  },

  _renderRevenueChart: function(data) {
    var el = document.getElementById('fin-revenue-chart');
    if (!el) return;
    var existing = echarts.getInstanceByDom(el);
    if (existing) existing.dispose();

    var dates = data.map(function(d) { return d.report_date ? d.report_date.slice(0, 7) : ''; });
    var revenue = data.map(function(d) { return ((d.revenue || 0) / 1e8); });
    var profit = data.map(function(d) { return ((d.parent_profit || 0) / 1e8); });

    var chart = echarts.init(el);
    chart.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: ['营收(亿)', '净利润(亿)'], textStyle: { color: '#999' }, bottom: 0 },
      grid: { left: '12%', right: '5%', top: '8%', bottom: '22%' },
      xAxis: { type: 'category', data: dates, axisLabel: { fontSize: 9, rotate: 30, color: '#999' },
        axisLine: { lineStyle: { color: '#333' } } },
      yAxis: { type: 'value', splitLine: { lineStyle: { color: '#1a1a1a' } }, axisLabel: { fontSize: 9 } },
      series: [
        { name: '营收(亿)', type: 'bar', data: revenue, itemStyle: { color: '#60a5fa', borderRadius: [2,2,0,0] } },
        { name: '净利润(亿)', type: 'line', data: profit, smooth: true, symbol: 'circle', symbolSize: 6,
          lineStyle: { color: '#2ed573', width: 2 },
          itemStyle: { color: function(p) { return p.value >= 0 ? '#2ed573' : '#ff4757'; } } }
      ]
    });
    window.addEventListener('resize', function() { chart.resize(); });
  },

  _renderMarginChart: function(data) {
    var el = document.getElementById('fin-margin-chart');
    if (!el) return;
    var existing = echarts.getInstanceByDom(el);
    if (existing) existing.dispose();

    var dates = data.map(function(d) { return d.report_date ? d.report_date.slice(0, 7) : ''; });
    var gm = data.map(function(d) {
      return d.revenue ? ((d.revenue - d.operate_cost) / d.revenue * 100) : null;
    });

    var chart = echarts.init(el);
    chart.setOption({
      tooltip: { trigger: 'axis', formatter: function(p) {
        return p.map(function(item) {
          return item.seriesName + ': ' + (item.value != null ? item.value.toFixed(1) + '%' : '—');
        }).join('<br/>');
      }},
      legend: { data: ['毛利率'], textStyle: { color: '#999' }, bottom: 0 },
      grid: { left: '12%', right: '5%', top: '8%', bottom: '22%' },
      xAxis: { type: 'category', data: dates, axisLabel: { fontSize: 9, rotate: 30, color: '#999' },
        axisLine: { lineStyle: { color: '#333' } } },
      yAxis: { type: 'value', splitLine: { lineStyle: { color: '#1a1a1a' } },
        axisLabel: { formatter: '{value}%', fontSize: 9 } },
      series: [
        { name: '毛利率', type: 'line', data: gm, smooth: true, symbol: 'none',
          lineStyle: { color: '#ffa502', width: 2 }, connectNulls: true,
          areaStyle: { color: 'rgba(255,165,2,0.05)' } },
      ]
    });
    window.addEventListener('resize', function() { chart.resize(); });
  },

  _renderCashflowChart: function(data) {
    var el = document.getElementById('fin-cf-chart');
    if (!el) return;
    var existing = echarts.getInstanceByDom(el);
    if (existing) existing.dispose();

    var dates = data.map(function(d) { return d.report_date ? d.report_date.slice(0, 7) : ''; });
    var ocf = data.map(function(d) { return ((d.op_cashflow || 0) / 1e8); });
    var netProfit = data.map(function(d) { return ((d.parent_profit || 0) / 1e8); });

    var chart = echarts.init(el);
    chart.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: ['经营现金流(亿)', '净利润(亿)'], textStyle: { color: '#999' }, bottom: 0 },
      grid: { left: '12%', right: '5%', top: '8%', bottom: '22%' },
      xAxis: { type: 'category', data: dates, axisLabel: { fontSize: 8, rotate: 30, color: '#999' },
        axisLine: { lineStyle: { color: '#333' } } },
      yAxis: { type: 'value', splitLine: { lineStyle: { color: '#1a1a1a' } }, axisLabel: { fontSize: 9 } },
      series: [
        { name: '经营现金流(亿)', type: 'bar', data: ocf,
          itemStyle: { color: function(p) { return p.value >= 0 ? '#2ed573' : '#ff4757'; }, borderRadius: [2,2,0,0] } },
        { name: '净利润(亿)', type: 'line', data: netProfit, smooth: true, symbol: 'circle', symbolSize: 4,
          lineStyle: { color: '#70a1ff', width: 1.5, type: 'dashed' } }
      ]
    });
    window.addEventListener('resize', function() { chart.resize(); });
  },

  _renderRDChart: function(data) {
    var el = document.getElementById('fin-rd-chart');
    if (!el) return;
    var existing = echarts.getInstanceByDom(el);
    if (existing) existing.dispose();

    var dates = data.map(function(d) { return d.report_date ? d.report_date.slice(0, 7) : ''; });
    var rd = data.map(function(d) { return ((d.rd_expense || 0) / 1e8); });
    var rdRatio = data.map(function(d) {
      return d.revenue ? ((d.rd_expense || 0) / d.revenue * 100) : null;
    });

    var chart = echarts.init(el);
    chart.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: ['研发费用(亿)', '研发占比'], textStyle: { color: '#999' }, bottom: 0 },
      grid: { left: '12%', right: '8%', top: '8%', bottom: '22%' },
      xAxis: { type: 'category', data: dates, axisLabel: { fontSize: 8, rotate: 30, color: '#999' },
        axisLine: { lineStyle: { color: '#333' } } },
      yAxis: [
        { type: 'value', name: '亿', splitLine: { lineStyle: { color: '#1a1a1a' } }, axisLabel: { fontSize: 9 } },
        { type: 'value', name: '%', splitLine: { show: false }, axisLabel: { formatter: '{value}%', fontSize: 9 } }
      ],
      series: [
        { name: '研发费用(亿)', type: 'bar', data: rd,
          itemStyle: { color: '#70a1ff', borderRadius: [2,2,0,0] } },
        { name: '研发占比', type: 'line', yAxisIndex: 1, data: rdRatio,
          smooth: true, symbol: 'none', connectNulls: true,
          lineStyle: { color: '#ffa502', width: 1.5, type: 'dashed' } }
      ]
    });
    window.addEventListener('resize', function() { chart.resize(); });
  },

  _renderTable: function(rows) {
    var el = document.getElementById('financial-table');
    if (!el) return;
    el.innerHTML = '<table class="health-table"><thead><tr>' +
      '<th>报告期</th><th style="text-align:right;">营收(亿)</th><th style="text-align:right;">净利(亿)</th>' +
      '<th style="text-align:right;">毛利率</th><th style="text-align:right;">净利率</th>' +
      '<th style="text-align:right;">现金流(亿)</th><th style="text-align:right;">存货(亿)</th>' +
      '<th style="text-align:right;">合同负债(亿)</th><th style="text-align:right;">应收(亿)</th>' +
      '<th style="text-align:right;">总资产(亿)</th><th style="text-align:right;">ROE</th>' +
    '</tr></thead><tbody>' + rows.map(function(r) {
      var rev = (r.revenue || 0) / 1e8;
      var profit = (r.parent_profit || 0) / 1e8;
      var gm = r.revenue ? ((r.revenue - r.operate_cost) / r.revenue * 100).toFixed(1) : '—';
      var nm = r.revenue ? (profit * 1e8 / r.revenue * 100).toFixed(1) : '—';
      var ocf = (r.op_cashflow || 0) / 1e8;
      var inv = (r.inventory || 0) / 1e8;
      var cl = (r.contract_liability || 0) / 1e8;
      var ar = (r.accounts_receivable || 0) / 1e8;
      var ta = (r.total_assets || 0) / 1e8;
      var roe = r.total_equity ? (profit * 1e8 / r.total_equity * 100).toFixed(1) : '—';
      var color = profit >= 0 ? 'var(--accent-green)' : 'var(--accent-red)';
      return '<tr>' +
        '<td>' + r.report_date + '<span style="font-size:9px;color:var(--text-micro);margin-left:4px;">' + (r.report_type || '') + '</span></td>' +
        '<td style="text-align:right;">' + rev.toFixed(2) + '</td>' +
        '<td style="text-align:right;color:' + color + ';">' + profit.toFixed(2) + '</td>' +
        '<td style="text-align:right;">' + gm + '%</td><td style="text-align:right;">' + nm + '%</td>' +
        '<td style="text-align:right;">' + ocf.toFixed(2) + '</td>' +
        '<td style="text-align:right;">' + inv.toFixed(2) + '</td>' +
        '<td style="text-align:right;">' + cl.toFixed(2) + '</td>' +
        '<td style="text-align:right;">' + ar.toFixed(2) + '</td>' +
        '<td style="text-align:right;">' + ta.toFixed(2) + '</td>' +
        '<td style="text-align:right;">' + roe + '%</td>' +
      '</tr>';
    }).join('') + '</tbody></table>';
  }
};
