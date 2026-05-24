/**
 * 数据中心 — 另类数据 Tab
 * 依赖: api.js (API_BASE), common.js (escHtml), core.js (DataTabs.Core.addLog), ECharts
 * 功能: 行业拥挤度柱状图 + 个股排名 + 筹码分布 + 历史时间序列弹窗
 */
window.DataTabs = window.DataTabs || {};

DataTabs.Alt = {
  async load() {
    var days = document.getElementById('alt-date-range').value || 30;
    var industry = document.getElementById('alt-industry-filter').value;
    try {
      var indRes = await fetch(`${API_BASE}/data/alt/crowding/industry?days=${days}`);
      var ovRes = await fetch(`${API_BASE}/data/alt/overview`);
      var wlRes = industry ? Promise.resolve(null) : fetch(`${API_BASE}/data/alt/crowding/watchlist?days=${days}`);
      var results = await Promise.all([indRes, ovRes, wlRes]);
      var indData = await results[0].json();
      var ovData = await results[1].json();
      var wlData = results[2] ? await results[2].json() : null;
      var industries = indData.data || [];
      var overview = ovData.data || {};

      // 填充行业过滤器
      var sel = document.getElementById('alt-industry-filter');
      var curVal = sel.value;
      sel.innerHTML = '<option value="">全部行业</option>' +
        industries.map(function(i) { return '<option value="' + escHtml(i.industry) + '">' + escHtml(i.industry) + ' (' + i.count + ')</option>'; }).join('');
      sel.value = curVal;

      // 渲染行业柱状图
      this.renderIndustryChart('alt-industry-chart', industries);

      // 个股表 (支持行业过滤)
      var filteredCrowd;
      if (industry) {
        var match = industries.filter(function(i) { return i.industry === industry; });
        filteredCrowd = match.length ? match[0].top_stocks : [];
      } else if (wlData && wlData.data) {
        filteredCrowd = wlData.data;
      } else {
        filteredCrowd = overview.crowding || [];
      }
      this.renderCrowdTable(filteredCrowd);
      this.renderChipTable(overview.chip || []);
    } catch (e) {
      console.error('[Alt]', e);
      DataTabs.Core.addLog('另类数据加载失败: ' + e.message, 'error');
    }
  },

  renderIndustryChart(containerId, industries) {
    var el = document.getElementById(containerId);
    if (!el) return;

    var existing = echarts.getInstanceByDom(el);
    if (existing) existing.dispose();

    if (!industries.length) {
      el.innerHTML = '<div style="color:var(--text-micro);padding:20px;text-align:center;">无行业数据, 请先计算拥挤度指标</div>';
      return;
    }

    var chartHeight = Math.max(180, Math.min(industries.length * 24 + 40, 500));
    el.style.height = chartHeight + 'px';

    var chart = echarts.init(el);
    var names = industries.map(function(i) { return i.industry; });
    var values = industries.map(function(i) { return i.avg_crowding_ratio; });

    chart.setOption({
      tooltip: {
        trigger: 'axis', axisPointer: { type: 'shadow' },
        formatter: function(p) {
          var i = industries[p[0].dataIndex];
          return i.industry + '<br/>平均拥挤度: ' + i.avg_crowding_ratio.toFixed(3) +
            '<br/>平均夏普: ' + (i.avg_sharpe_60d ? i.avg_sharpe_60d.toFixed(3) : '—') +
            '<br/>股票数: ' + i.count;
        }
      },
      grid: { left: '15%', right: '8%', top: '5%', bottom: '5%' },
      xAxis: { type: 'value', splitLine: { lineStyle: { color: '#1a1a1a' } } },
      yAxis: {
        type: 'category', data: names, inverse: true,
        axisLabel: { fontSize: 10, width: 110, overflow: 'truncate' },
        triggerEvent: true
      },
      series: [{
        type: 'bar', data: values,
        itemStyle: {
          color: function(p) {
            var v = values[p.dataIndex];
            if (v > 1.5) return '#ef4444';
            if (v > 1.0) return '#f59e0b';
            return '#60a5fa';
          }
        }
      }]
    });

    var self = this;
    chart.on('click', function(params) {
      document.getElementById('alt-industry-filter').value = params.name;
      self.load();
    });

    window.addEventListener('resize', function() { chart.resize(); });
  },

  renderCrowdTable(data) {
    var el = document.getElementById('alt-crowd-table');
    if (!data.length) {
      el.innerHTML = '<div style="color:var(--text-micro);padding:20px;">无拥挤度数据, 请先计算指标</div>';
      return;
    }
    el.innerHTML = '<table class="health-table"><thead><tr>' +
      '<th>代码</th><th>名称</th><th style="text-align:right;">拥挤度</th>' +
      '<th style="text-align:right;">夏普</th><th>日期</th></tr></thead>' +
      '<tbody>' + data.map(function(d) {
        var cr = d.crowding_ratio;
        var crColor = cr > 1.5 ? 'var(--accent-red)' : cr > 1.0 ? 'var(--accent-gold)' : 'var(--accent-green)';
        return '<tr style="cursor:pointer;" onclick="DataTabs.Alt.showHistory(\'' + escHtml(d.code) + '\',\'' + escHtml(d.name || d.code) + '\')" title="点击查看时间序列">' +
          '<td style="color:var(--accent-blue);">' + escHtml(d.code) + '</td>' +
          '<td>' + escHtml(d.name || d.code) + '</td>' +
          '<td style="text-align:right;color:' + crColor + ';">' + (cr != null ? cr.toFixed(3) : '—') + '</td>' +
          '<td style="text-align:right;">' + (d.sharpe_60d != null ? d.sharpe_60d.toFixed(3) : '—') + '</td>' +
          '<td style="font-size:10px;">' + (d.date || '') + '</td></tr>';
      }).join('') + '</tbody></table>';
  },

  renderChipTable(data) {
    var el = document.getElementById('alt-chip-table');
    if (!data.length) {
      el.innerHTML = '<div style="color:var(--text-micro);padding:20px;">无筹码数据, 请先计算指标</div>';
      return;
    }
    el.innerHTML = '<table class="health-table"><thead><tr>' +
      '<th>代码</th><th style="text-align:right;">集中度</th>' +
      '<th style="text-align:right;">峰值价</th><th>形态</th></tr></thead>' +
      '<tbody>' + data.map(function(c) {
        var cd = c.code;
        var nm = c.name && c.name !== cd ? '<br><small style="color:var(--text-micro);">' + escHtml(c.name) + '</small>' : '';
        return '<tr>' +
          '<td style="color:var(--accent-blue);">' + escHtml(cd) + nm + '</td>' +
          '<td style="text-align:right;">' + (c.concentration != null ? c.concentration.toFixed(1) + '%' : '—') + '</td>' +
          '<td style="text-align:right;">' + (c.peak != null ? c.peak.toFixed(2) : '—') + '</td>' +
          '<td style="font-size:10px;">' + escHtml(c.pattern || '') + '</td></tr>';
      }).join('') + '</tbody></table>';
  },

  async showHistory(code, name) {
    try {
      var res = await fetch(`${API_BASE}/quant/indicators/history/${code}?fields=crowding_ratio,sharpe_60d&days=120`);
      var d = await res.json();
      var data = d.data;
      if (!data || !data.dates || !data.dates.length) {
        DataTabs.Core.addLog(code + ' 无历史拥挤度数据', 'warn');
        return;
      }
      var id = 'crowd-chart-' + Date.now();
      var html = '<div style="position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.7);z-index:1000;display:flex;justify-content:center;align-items:center;backdrop-filter:blur(4px);" onclick="this.remove()">' +
        '<div style="background:var(--bg-card);width:85%;max-width:900px;border-radius:8px;border:1px solid var(--border-color);overflow:hidden;" onclick="event.stopPropagation()">' +
        '<div style="padding:10px 14px;border-bottom:1px solid var(--border-color);display:flex;justify-content:space-between;">' +
        '<span style="font-weight:700;">' + escHtml(code) + ' ' + escHtml(name) + ' — 拥挤度 & 夏普</span>' +
        '<button onclick="this.closest(\'div[style*=fixed]\').remove()" style="background:none;border:none;color:var(--text-dim);cursor:pointer;font-size:16px;">&times;</button></div>' +
        '<div id="' + id + '" style="width:100%;height:400px;"></div></div></div>';
      document.body.insertAdjacentHTML('beforeend', html);
      setTimeout(function() {
        var c = document.getElementById(id);
        if (!c || !window.echarts) return;
        var chart = echarts.init(c);
        chart.setOption({
          tooltip: { trigger: 'axis' },
          legend: { data: ['拥挤度', '夏普60d'], textStyle: { color: '#999' } },
          xAxis: { type: 'category', data: data.dates, axisLabel: { fontSize: 9, rotate: 30 } },
          yAxis: [
            { type: 'value', name: '拥挤度', splitLine: { lineStyle: { color: '#1a1a1a' } }, axisLabel: { fontSize: 9 } },
            { type: 'value', name: '夏普', splitLine: { show: false }, axisLabel: { fontSize: 9 } }
          ],
          series: [
            { name: '拥挤度', type: 'line', data: data.fields.crowding_ratio, smooth: true, symbol: 'none',
              lineStyle: { color: '#60a5fa', width: 1.5 }, areaStyle: { color: 'rgba(96,165,250,0.08)' } },
            { name: '夏普60d', type: 'line', yAxisIndex: 1, data: data.fields.sharpe_60d,
              smooth: true, symbol: 'none', lineStyle: { color: '#f59e0b', width: 1.5, type: 'dashed' } }
          ]
        });
      }, 200);
    } catch (e) {
      DataTabs.Core.addLog('拥挤度历史加载失败: ' + e.message, 'error');
    }
  },

  computeIndicators() {
    IndicatorCompute.openModal({ mode: 'historical' });
  },

  toggleGuide() {
    var body = document.getElementById('alt-guide-body');
    var toggle = document.getElementById('alt-guide-toggle');
    if (body.style.display === 'none') {
      body.style.display = '';
      toggle.textContent = '收起';
    } else {
      body.style.display = 'none';
      toggle.textContent = '展开';
    }
  },

  toggleChipGuide() {
    var body = document.getElementById('alt-chip-guide-body');
    var toggle = document.getElementById('alt-chip-guide-toggle');
    if (body.style.display === 'none') {
      body.style.display = '';
      toggle.textContent = '收起';
    } else {
      body.style.display = 'none';
      toggle.textContent = '展开';
    }
  }
};
