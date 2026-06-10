/**
 * 数据中心 — 宏观 Tab (V5.10: 路由层 + 宏观报告卡片)
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
      await SyncAPI.macro(null, mode === 'historical' ? 'full' : 'smart');
      DataTabs.Core.addLog('宏观' + label + '完成', 'success');
      this.load();
    } catch (e) { DataTabs.Core.addLog('宏观同步失败: ' + e.message, 'error'); }
  },

  async refreshReport() {
    DataTabs.Core.addLog('刷新宏观报告...', 'info');
    try {
      await fetch(API_BASE + '/data/macro/report/refresh', { method: 'POST' });
      DataTabs.Core.addLog('宏观报告刷新完成', 'success');
      this.load();
    } catch(e) { DataTabs.Core.addLog('刷新失败: ' + e.message, 'error'); }
  },

  async load() {
    var el = document.getElementById('macro-cards');
    // 宏观报告摘要卡片
    this._loadReportCard(el);
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
      var gotCodes = items.map(function(x){return x.code;});
      var missing = Object.keys(this.INFO).filter(function(c){return gotCodes.indexOf(c) < 0;});
      if (missing.length) {
        el.innerHTML += '<div style="width:100%;font-size:9px;color:var(--text-micro);margin-top:4px;">待接入: ' + missing.join('/') + '</div>';
      }
    } catch (e) { el.innerHTML = '<div style="color:var(--accent-red);">加载失败</div>'; }
  },

  async _loadReportCard(el) {
    try {
      var res = await fetch(API_BASE + '/data/macro/report');
      if (!res.ok) return;
      var mr = await res.json();
      var d = mr.data || mr;
      if (!d) return;
      var es = d.executive_summary;
      if (!es) return;
      var mr = d.macro_regime || {};
      var regime = mr.cycle_position || mr.capital_flow_direction || '—';
      var genTime = (d.generated_at || '').substring(0, 16).replace('T', ' ');
      var validTime = (d.valid_until || '').substring(0, 10);
      var card = '<div class="macro-report-card" style="grid-column:1/-1;background:rgba(255,255,255,0.03);border:1px solid var(--accent-blue);border-radius:6px;padding:10px 14px;margin-bottom:4px;">' +
        '<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px;">' +
        '<span style="color:#fff;font-size:13px;"><i class="fas fa-globe"></i> 宏观周期报告</span>' +
        '<span style="color:var(--text-micro);font-size:9px;">' + genTime + ' · 有效期至 ' + validTime + '</span>' +
        '<div style="display:flex;align-items:center;gap:6px;">' +
        '<span style="font-size:10px;background:rgba(255,255,255,0.06);padding:2px 8px;border-radius:3px;">' + regime + '</span>' +
        '<button onclick="DataTabs.Macro.refreshReport()" style="background:none;border:1px solid var(--border-thin);color:var(--text-dim);padding:2px 6px;border-radius:3px;cursor:pointer;font-size:10px;" title="刷新宏观报告"><i class="fas fa-sync-alt"></i></button>' +
        '</div></div>' +
        '<div style="color:var(--text-dim);font-size:11px;margin-top:6px;line-height:1.6;">' +
        '<div><strong>定调：</strong>' + (es.one_liner || '未生成') + '</div>' +
        '<div><strong>流动性：</strong>' + (es.liquidity_direction || '—') + '</div>' +
        (mr.implication ? '<div style="margin-top:3px;color:var(--accent-blue);font-size:10px;">' + mr.implication + '</div>' : '') +
        '</div></div>';
      el.insertAdjacentHTML('afterbegin', card);
    } catch(e) { /* 可选, 失败静默 */ }
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
      var html = '<div id="' + id + '" style="width:100%;height:450px;"></div>';
      Modal.custom({title: name + ' 历史趋势', content: html, wide: true});
      setTimeout(function() {
        var chart = echarts.init(document.getElementById(id));
        chart.setOption({
          tooltip: {trigger:'axis'}, grid: {left:55,right:30,top:20,bottom:30},
          xAxis: {type:'category',data:dates,axisLabel:{fontSize:10,color:'#aaa'}},
          yAxis: {type:'value',scale:true,axisLabel:{fontSize:10,color:'#aaa'}},
          series: [{data:values,type:'line',smooth:true,
            lineStyle:{color:'#4e9eff', width:2},itemStyle:{color:'#4e9eff'},
            areaStyle:{color:{type:'linear',x:0,y:0,x2:0,y2:1,
              colorStops:[{offset:0,color:'rgba(78,158,255,0.4)'},{offset:1,color:'rgba(78,158,255,0.02)'}]}}}]
        });
      }, 300);
    } catch(e) { DataTabs.Core.addLog('趋势加载失败: ' + e.message, 'error'); }
  }
};
