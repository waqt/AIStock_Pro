/**
 * 数据中心 — 宏观 Tab (V5.9 扩展: 16 个宏观指标)
 * 依赖: api.js (API_BASE), common.js (escHtml), core.js (DataTabs.Core.addLog), ECharts
 */
window.DataTabs = window.DataTabs || {};

DataTabs.Macro = {
  INFO: {
    XAU: {name:'黄金', desc:'国际金价，避险资产风向标', unit:'美元/盎司'},
    XAG: {name:'白银', desc:'工业+贵金属双重属性，光伏需求拉动', unit:'美元/盎司'},
    BRENT: {name:'原油', desc:'布伦特原油，全球制造业成本基准', unit:'美元/桶'},
    USD_CNY: {name:'美元/人民币', desc:'在岸汇率，影响外资流动和进口成本', unit:''},
    HKD_CNY: {name:'港币/人民币', desc:'港股投资汇率锚', unit:''},
    US10YT: {name:'美债10Y', desc:'全球资产定价之锚，DCF折现率基准', unit:'%'},
    CN10YT: {name:'中国国债10Y', desc:'人民币无风险利率，中美利差影响资本流动', unit:'%'},
    US2Y: {name:'美债2Y', desc:'美联储政策利率预期，2s10s利差预示衰退', unit:'%'},
    US_FED_RATE: {name:'美联储利率', desc:'联邦基金利率上限，全球流动性总闸门', unit:'%'},
    CN_LPR1Y: {name:'LPR 1年期', desc:'贷款市场报价利率，企业短期融资成本', unit:'%'},
    CN_M2_YOY: {name:'M2同比', desc:'广义货币增速，信用扩张/收缩信号', unit:'%'},
    CN_PMI_MFG: {name:'中国制造业PMI', desc:'>50扩张<50收缩，经济先行指标', unit:''},
    CN_PMI_NONMFG: {name:'中国非制造业PMI', desc:'服务业+建筑业景气度', unit:''},
    US_ISM_PMI: {name:'美国ISM PMI', desc:'美国制造业景气，全球需求风向标', unit:''},
    US_CPI_YOY: {name:'美国CPI同比', desc:'核心通胀指标，决定美联储政策路径', unit:'%'},
    CN_CPI_YOY: {name:'中国CPI同比', desc:'居民消费价格，影响货币政策空间', unit:'%'},
  },

  async sync(mode) {
    var label = mode === 'historical' ? '补齐历史' : '同步当日';
    DataTabs.Core.addLog('宏观' + label + '...', 'info');
    try {
      await fetch(API_BASE + '/data/macro/sync?mode=' + mode, { method: 'POST' });
      DataTabs.Core.addLog('宏观' + label + '完成', 'success');
      this.load();
    } catch (e) { DataTabs.Core.addLog('宏观同步失败: ' + e.message, 'error'); }
  },

  async load() {
    var el = document.getElementById('macro-cards');
    try {
      var res = await fetch(API_BASE + '/data/macro/latest');
      var data = await res.json();
      var items = data.data || [];
      var self = this;
      el.innerHTML = items.map(function(i) {
        var inf = self.INFO[i.code] || {name:i.code, unit:''};
        var pct = i.change_pct;
        var pctStr = pct != null ? ((pct >= 0 ? '+' : '') + pct.toFixed(2) + '%') : '';
        var pctColor = pct != null ? (pct >= 0 ? 'var(--accent-green)' : 'var(--accent-red)') : 'var(--text-micro)';
        var v = i.rate;
        var vStr = '—';
        if (v != null) {
          if (i.code.indexOf('PMI') >= 0 || i.code.indexOf('CPI') >= 0 || i.code.indexOf('M2') >= 0)
            vStr = v.toFixed(1);
          else if (i.code.indexOf('YT') >= 0 || i.code.indexOf('FED') >= 0 || i.code.indexOf('LPR') >= 0)
            vStr = v.toFixed(2);
          else if (i.code === 'XAU' || i.code === 'BRENT')
            vStr = v.toFixed(2);
          else
            vStr = v.toFixed(4);
        }
        var bizInfo = i.biz_date ? i.biz_date : '<span style="color:var(--accent-red);">日期缺失</span>';
        return '<div class="macro-card" style="cursor:pointer;" onclick="DataTabs.Macro.showHistory(\'' + i.code + '\',\'' + inf.name + '\')" title="' + (inf.desc || '') + ' | 点击查看历史趋势">' +
          '<div class="label">' + inf.name + '</div>' +
          '<div class="desc" style="font-size:9px;color:var(--text-micro);margin-bottom:2px;" title="' + (inf.desc || '') + '">' + (inf.desc || '') + '</div>' +
          '<div class="value">' + vStr + (inf.unit && vStr !== '—' ? ' <span style="font-size:9px;color:var(--text-micro);">' + inf.unit + '</span>' : '') + '</div>' +
          '<div class="change" style="color:' + pctColor + '">' + (pctStr || '—') + '</div>' +
          '<div style="font-size:8px;color:var(--text-micro);margin-top:2px;">' + bizInfo + '</div></div>';
      }).join('');
      // Missing indicators
      var gotCodes = items.map(function(x){return x.code;});
      var missing = Object.keys(this.INFO).filter(function(c){return gotCodes.indexOf(c) < 0;});
      if (missing.length) {
        el.innerHTML += '<div style="width:100%;font-size:9px;color:var(--text-micro);margin-top:4px;">待接入: ' + missing.join('/') + '</div>';
      }
    } catch (e) { el.innerHTML = '<div style="color:var(--accent-red);">加载失败</div>'; }
  },

  async showHistory(code, name) {
    try {
      var res = await fetch(API_BASE + '/data/macro/history?code=' + code + '&days=365');
      var d = await res.json();
      var data = d.data || [];
      if (!data.length) { DataTabs.Core.addLog(name + ' 无历史数据', 'warn'); return; }
      var dates = data.map(function(r){return r.date;});
      var values = data.map(function(r){return r.value;});
      var id = 'macro-chart-' + Date.now();
      var html = '<div style="position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.7);z-index:1000;display:flex;justify-content:center;align-items:center;backdrop-filter:blur(4px);" onclick="this.remove()">' +
        '<div style="background:var(--bg-card);width:80%;max-width:800px;border-radius:8px;border:1px solid var(--border-color);overflow:hidden;" onclick="event.stopPropagation()">' +
        '<div style="padding:10px 14px;border-bottom:1px solid var(--border-color);display:flex;justify-content:space-between;">' +
        '<span style="font-weight:700;">' + escHtml(name) + ' 历史趋势 (' + data.length + '天)</span>' +
        '<button onclick="this.closest(\'div[style*=fixed]\').remove()" style="background:none;border:none;color:var(--text-dim);cursor:pointer;font-size:16px;">&times;</button></div>' +
        '<div id="' + id + '" style="width:100%;height:400px;"></div></div></div>';
      document.body.insertAdjacentHTML('beforeend', html);
      setTimeout(function() {
        var c = document.getElementById(id);
        if (!c || !window.echarts) return;
        var chart = echarts.init(c);
        chart.setOption({
          tooltip: { trigger: 'axis' },
          xAxis: { type: 'category', data: dates, axisLabel: { fontSize: 9, rotate: 30 } },
          yAxis: { type: 'value', scale: true, splitLine: { lineStyle: { color: '#1a1a1a' } } },
          series: [{ type: 'line', data: values, smooth: true, symbol: 'none',
            lineStyle: { color: '#60a5fa', width: 1.5 },
            areaStyle: { color: 'rgba(96,165,250,0.08)' } }]
        });
      }, 200);
    } catch (e) { DataTabs.Core.addLog('历史加载失败: ' + e.message, 'error'); }
  }
};
