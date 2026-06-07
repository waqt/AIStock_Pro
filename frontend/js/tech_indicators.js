/**
 * 技术指标前端模块 (TechInd) — V4
 *
 * 三层展示架构:
 *   Tier 1: 主图 (K线+成交量+叠加层)   ← 始终显示
 *   Tier 2: 副图 (Tab 切换, 一次一图)   ← 用户选择
 *   Tier 3: 筹码信息卡片                 ← 始终显示
 * + Field Mode: 排序排名表 + 筛选 + CSV
 * + Compare Mode: 多股票×多指标交叉比较
 */
window.TechInd = (function() {
    'use strict';

    var API = window.API_BASE || '/api';

    // ── 分类名称 (保留给 indicator value 列表用) ──
    var CAT_NAMES = {
        trend: '趋势', momentum: '动量', volatility: '波动',
        volume: '量能', crowding: '拥挤度', chip: '筹码'
    };
    var CAT_ORDER = ['trend', 'momentum', 'volatility', 'volume', 'crowding', 'chip'];

    var SERIES_COLORS = ['#60a5fa', '#2ed573', '#ff4757', '#ffa502', '#a29bfe', '#fb6da7', '#00d2d3', '#f368e0'];

    // ── 主图叠加层定义 (K线同量纲) ──
    var OVERLAY_DEFS = {
        // 均线 (逐个展开)
        'ma5':   { label: 'MA5',  color: '#60a5fa', fields: ['ma5'],   type: 'line' },
        'ma10':  { label: 'MA10', color: '#2ed573', fields: ['ma10'],  type: 'line' },
        'ma20':  { label: 'MA20', color: '#ffa502', fields: ['ma20'],  type: 'line' },
        'ma60':  { label: 'MA60', color: '#ff4757', fields: ['ma60'],  type: 'line' },
        'ma120': { label: 'MA120',color: '#a29bfe', fields: ['ma120'], type: 'line' },
        'ma250': { label: 'MA250',color: '#00d2d3', fields: ['ma250'], type: 'line' },
        // 组叠加
        'bollinger':  { label: '布林带',  fields: ['bb_upper','bb_mid','bb_lower'],               type: 'band' },
        'vwap':       { label: 'VWAP',    color: '#f368e0',     fields: ['vwap'],                  type: 'line' },
        'chip_price': { label: '筹码价格', fields: ['chip_peak_price','chip_avg_cost'],            type: 'multi_line',
                        colors: {'chip_peak_price':'#22d3ee','chip_avg_cost':'#fb6da7'} },
    };
    // 均线排列顺序 (UI 用)
    var MA_KEYS = ['ma5','ma10','ma20','ma60','ma120','ma250'];
    // 组叠加重定向 (渲染时展开)
    var GROUP_OVERLAY_KEYS = ['bollinger','vwap','chip_price'];

    // ── 副图定义 (Tab 切换, 一次一个) ──
    var SUB_CHART_DEFS = {
        'macd':  { label: 'MACD',     fields: ['macd','macd_signal','macd_hist'],              style: 'macd' },
        'kdj':   { label: 'KDJ',      fields: ['k','d','j'],                                    style: 'ranged', min: 0, max: 100 },
        'rsi':   { label: 'RSI',      fields: ['rsi'],                                          style: 'rsi' },
        'atr':   { label: 'ATR',      fields: ['atr'],                                          style: 'line' },
        'cci':   { label: 'CCI',      fields: ['cci'],                                          style: 'line' },
        'obv':   { label: 'OBV',      fields: ['obv'],                                          style: 'line' },
        'volma': { label: '均量线',    fields: ['v_ma5','v_ma10','v_ma20'],                     style: 'line' },
        'bbw':   { label: '布林带宽',  fields: ['bb_width'],                                    style: 'line' },
        'turn':  { label: '换手率',    fields: ['turnover_20d','turnover_120d'],                 style: 'line' },
        'crowd': { label: '拥挤度',    fields: ['crowding_ratio'],                               style: 'line' },
        'sharpe':{ label: '夏普比',    fields: ['sharpe_60d'],                                   style: 'line' },
        'chipc': { label: '筹码集中度',fields: ['chip_concentration'],                           style: 'line' },
        'chipd': { label: '筹码分布',  fields: [],                                                style: 'chip_dist' },
    };
    var SUB_CHART_ORDER = ['macd','kdj','rsi','atr','cci','obv','volma','bbw','turn','crowd','sharpe','chipc','chipd'];

    // ── 状态 ──
    var currentMode = 'stock';       // 'stock' | 'field' | 'compare'
    var currentStock = '';
    var currentField = '';
    var registry = [];
    var registryMap = {};
    var textFields = {};
    var stockList = [];
    var stockNameMap = {};

    // 比较状态 (localStorage)
    var compareStocks = JSON.parse(localStorage.getItem('ti_compare_stocks') || '[]');
    var compareIndicators = JSON.parse(localStorage.getItem('ti_compare_inds') || '[]');
    var allStocksForCompare = [];

    // ★ V4 新增状态
    var _dailyData = null;           // 日线 OHLC [{trade_date,open,high,low,close,volume}...]
    var _indicatorHistory = null;    // 指标历史 {dates, fields:{...}}
    var _cachedSnapshot = null;      // 最新指标快照 (用于左面板数值显示)
    var _overlayState = {};           // { ma5: true, ma10: true, ..., bollinger: false, ... }
    var _activeSubChart = 'macd';    // 当前副图 key
    var _chartDays = 180;            // 当前时间范围

    // 排序/筛选状态 (field mode)
    var _fieldItems = [];
    var _sortCol = '';
    var _sortDir = '';
    var _filterOp = '';
    var _filterVal = '';

    var _chartInstances = [];
    var _resizeHandler = null;

    // ── 工具 ──
    function escHtml(s) { if (!s) return ''; return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
    function getStockName(code) { return stockNameMap[code] || code; }
    function getFieldLabel(field) {
        if (!field) return '';
        for (var k in registryMap) {
            var ind = registryMap[k];
            if (ind.name === field) return ind.label || field;
            if ((ind.output || []).indexOf(field) >= 0) return ind.label || field;
        }
        return field;
    }
    function _fmtValue(v, indName) {
        if (v == null || v === '' || v === undefined) return '—';
        if (typeof v === 'string') return v;
        var n = Number(v);
        if (isNaN(n)) return String(v);
        var abs = Math.abs(n);
        if (abs >= 1000) return n.toFixed(0);
        if (abs >= 1) return n.toFixed(2);
        if (abs >= 0.01) return n.toFixed(4);
        return n.toExponential(2);
    }
    function _valueColor(field, v) {
        if (v == null || v === '') return 'var(--text-micro)';
        if (typeof v === 'string') return 'var(--text-dim)';
        var n = Number(v);
        if (isNaN(n)) return 'var(--text-dim)';
        if (field === 'rsi' || field === 'k' || field === 'd') {
            if (n > 70) return 'var(--accent-red)';
            if (n < 30) return 'var(--accent-green)';
            return 'var(--text-dim)';
        }
        if (field.indexOf('macd') >= 0 || field.indexOf('hist') >= 0) {
            if (n > 0) return 'var(--accent-green)';
            if (n < 0) return 'var(--accent-red)';
            return 'var(--text-dim)';
        }
        if (n > 0) return 'var(--accent-green)';
        if (n < 0) return 'var(--accent-red)';
        return 'var(--text-dim)';
    }
    function _isETF(code) { return /^(159|510|512|513|560|588)/.test(code); }
    function _toDateStr() {
        var d = new Date();
        return d.getFullYear() + '-' + String(d.getMonth()+1).padStart(2,'0') + '-' + String(d.getDate()).padStart(2,'0');
    }
    function _downloadCSV(content, filename) {
        var blob = new Blob([content], { type: 'text/csv;charset=utf-8;' });
        var link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = filename;
        link.click();
    }

    // ── 初始化 ──
    async function init() {
        try {
            var res = await fetch(API + '/quant/indicators/registry');
            var d = await res.json();
            registry = d.data || [];
            registryMap = {};
            textFields = {};
            registry.forEach(function(ind) {
                registryMap[ind.name] = ind;
                (ind.text_output || []).forEach(function(f) { textFields[f] = true; });
            });
            var fs = document.getElementById('field-select');
            if (fs) {
                fs.innerHTML = '<option value="">— 选择指标 —</option>' +
                    registry.map(function(i) {
                        return '<option value="' + i.name + '">' + i.name + ' (' + (i.label || '') + ')</option>';
                    }).join('');
            }
        } catch (e) { console.error('[TechInd] registry error:', e); }

        try {
            var [posRes, wlRes] = await Promise.all([
                fetch(API + '/positions'),
                fetch(API + '/data/watchlist')
            ]);
            var posData = await posRes.json();
            var wlData = await wlRes.json();
            var map = {};
            // positions API 返回扁平数组, watchlist API 返回 {success, data}
            var posList = Array.isArray(posData) ? posData : (posData.data || []);
            var wlList = Array.isArray(wlData) ? wlData : (wlData.data || []);
            posList.forEach(function(p) { map[p.stock_code] = p.stock_name || ''; });
            wlList.forEach(function(w) { map[w.stock_code] = w.stock_name || ''; });
            stockList = Object.keys(map).filter(function(code) { return !_isETF(code); }).map(function(code) {
                return { stock_code: code, stock_name: map[code] };
            });
            stockNameMap = map;
            allStocksForCompare = stockList.slice();

            var sel = document.getElementById('stock-select');
            if (sel) {
                sel.innerHTML = '<option value="">— 选择股票 —</option>' +
                    stockList.map(function(i) {
                        return '<option value="' + i.stock_code + '">' + i.stock_code + ' ' + (i.stock_name || '') + '</option>';
                    }).join('');
                if (stockList.length > 0) { sel.value = stockList[0].stock_code; selectStock(); }
            }
        } catch (e) { console.error('[TechInd] stock list error:', e); }

        _resizeHandler = function() {
            _chartInstances.forEach(function(c) { if (c) c.resize(); });
        };
        window.addEventListener('resize', _resizeHandler);
    }

    // ══════════════════════════════════════════════════════════════
    // Mode Switching
    // ══════════════════════════════════════════════════════════════
    function switchMode(mode) {
        currentMode = mode;
        var btns = { stock: 'btn-stock', field: 'btn-field', compare: 'btn-compare' };
        for (var m in btns) {
            var el = document.getElementById(btns[m]);
            if (el) el.classList.toggle('active', m === mode);
        }
        document.getElementById('mode-stock').style.display = mode === 'stock' ? 'flex' : 'none';
        document.getElementById('mode-field').style.display = mode === 'field' ? 'flex' : 'none';
        document.getElementById('mode-compare').style.display = mode === 'compare' ? 'flex' : 'none';

        if (mode === 'stock' && currentStock) selectStock();
        if (mode === 'field' && currentField) selectField();
        if (mode === 'compare') _updateCompareUI();
    }

    // ══════════════════════════════════════════════════════════════
    // ★ V4: Stock Mode — K线主图 + 副图Tab + 筹码卡片
    // ══════════════════════════════════════════════════════════════

    // ── 选择股票 ──
    function selectStock() {
        var code = document.getElementById('stock-select').value;
        if (!code) return;
        currentStock = code;

        // 重置状态
        _disposeAllCharts();
        _dailyData = null;
        _indicatorHistory = null;
        _cachedSnapshot = null;

        // 初始化叠加层默认状态 (ma5/10/20/60 默认开启)
        _overlayState = {};
        MA_KEYS.forEach(function(k) { _overlayState[k] = ['ma5','ma10','ma20','ma60'].indexOf(k) >= 0; });
        GROUP_OVERLAY_KEYS.forEach(function(k) { _overlayState[k] = false; });
        _activeSubChart = 'macd';

        document.getElementById('stock-info-text').textContent = '加载中...';
        document.getElementById('indicator-cards').innerHTML = '<div style="color:var(--text-micro);padding:20px;">加载中...</div>';

        // 并行加载: 日线数据 + 指标历史 + 指标快照
        var allFields = _getAllFieldNames();
        // days=0 → 取全部数据, 用最大值
        var apiDays = _chartDays || 2000;
        Promise.all([
            fetch(API + '/data/daily/' + code + '?limit=' + apiDays).then(function(r) { return r.json(); }),
            fetch(API + '/quant/indicators/history/' + code + '?fields=' + allFields.join(',') + '&days=' + apiDays).then(function(r) { return r.json(); }),
            fetch(API + '/quant/indicators/' + code).then(function(r) { return r.json(); })
        ])
        .then(function(results) {
            // Daily API returns flat array (not wrapped in {value}), indicator APIs use {success, data}
            var dailyResp = results[0];
            _dailyData = (Array.isArray(dailyResp) ? dailyResp : (dailyResp.value || [])).filter(function(r) { return r.open > 0; });
            _indicatorHistory = results[1].data;
            _cachedSnapshot = (results[2].data && results[2].data.indicators) ? results[2].data.indicators : null;

            if (!_dailyData.length && (!_indicatorHistory || !_indicatorHistory.dates || !_indicatorHistory.dates.length)) {
                document.getElementById('stock-info-text').textContent = code + ' — 无数据';
                document.getElementById('indicator-cards').innerHTML = '<div style="color:var(--text-micro);padding:20px;text-align:center;">暂无该股票的数据</div>';
                return;
            }

            var infoText = '';
            if (_cachedSnapshot && _cachedSnapshot.price) {
                infoText = '现价: ' + _cachedSnapshot.price.toFixed(2);
            }
            if (_dailyData.length) {
                var latest = _dailyData[_dailyData.length - 1];
                infoText += ' | 日期: ' + latest.trade_date + '  O:' + latest.open.toFixed(2) + ' H:' + latest.high.toFixed(2) + ' L:' + latest.low.toFixed(2) + ' C:' + latest.close.toFixed(2) + '  Vol:' + (latest.volume/1e4).toFixed(0) + '万股';
            }
            document.getElementById('stock-info-text').textContent = infoText || (code + ' — 数据已加载');

            // 渲染左侧面板
            _renderCards();
            // 渲染主图
            _renderMainChart();
            // 渲染副图
            _renderSubChart();
            // 渲染筹码卡片
            _renderChipCard();
        })
        .catch(function(e) {
            console.error('[TechInd] load error:', e);
            document.getElementById('stock-info-text').textContent = '加载失败: ' + e.message;
            document.getElementById('indicator-cards').innerHTML = '<div style="color:var(--accent-red);padding:20px;">加载失败，请重试</div>';
        });
    }

    // ── 获取所有可能需要的字段名 ──
    function _getAllFieldNames() {
        var fields = [];
        // 叠加层
        for (var k in OVERLAY_DEFS) {
            OVERLAY_DEFS[k].fields.forEach(function(f) { if (fields.indexOf(f) < 0) fields.push(f); });
        }
        // 副图
        for (var sk in SUB_CHART_DEFS) {
            SUB_CHART_DEFS[sk].fields.forEach(function(f) { if (fields.indexOf(f) < 0) fields.push(f); });
        }
        return fields;
    }

    // ── 拼接日线与指标数据 ──
    function _getMergedData() {
        if (!_dailyData || !_dailyData.length) return null;

        // _dailyData 来自 API: 正序 (chronological, oldest-first)
        var dates = _dailyData.map(function(r) { return r.trade_date; });
        var ohlc = _dailyData.map(function(r) { return [r.open, r.close, r.low, r.high]; });
        var volumes = _dailyData.map(function(r) { return r.volume; });

        // 若没有指标历史, 返回纯 K线数据
        if (!_indicatorHistory || !_indicatorHistory.dates) {
            return { dates: dates, ohlc: ohlc, volumes: volumes, aligned: {} };
        }

        // 指标历史是 newest-first, 反转以对齐日线正序
        var indDates = _indicatorHistory.dates.slice().reverse();
        var indFields = {};
        for (var f in _indicatorHistory.fields) {
            indFields[f] = _indicatorHistory.fields[f].slice().reverse();
        }

        // 指标日期 → 索引映射 (now chronological)
        var dateToIdx = {};
        indDates.forEach(function(d, i) { dateToIdx[d] = i; });

        // 对齐每个指标字段到日线日期
        var aligned = {};
        for (var field in indFields) {
            aligned[field] = dates.map(function(d) {
                var idx = dateToIdx[d];
                return idx !== undefined ? indFields[field][idx] : null;
            });
        }

        return { dates: dates, ohlc: ohlc, volumes: volumes, aligned: aligned };
    }

    // ── 渲染左面板 ──
    function _renderCards() {
        // 不再沿用 category 分组, 改为三区域:
        // 1. 主图叠加 (均线 + 组叠加)
        // 2. 副图选择
        // 3. (筹码卡片独立渲染到右侧)
        var ind = _cachedSnapshot;
        if (!ind) {
            document.getElementById('indicator-cards').innerHTML = '<div style="color:var(--text-micro);padding:10px;">暂无指标数据</div>';
            return;
        }

        var html = '';

        // ── 区域1: 主图叠加 ──
        html += '<div class="cat-title" style="margin-top:0;">📈 主图叠加</div>';
        html += '<div style="padding:4px 6px 2px;display:flex;flex-wrap:wrap;gap:3px;">';
        // 均线
        MA_KEYS.forEach(function(k) {
            var def = OVERLAY_DEFS[k];
            if (!def) return;
            var checked = _overlayState[k] ? ' checked' : '';
            var val = ind[k] != null ? def.label : '';
            html += '<label style="display:inline-flex;align-items:center;gap:2px;font-size:9px;cursor:pointer;padding:1px 4px;border-radius:2px;background:rgba(255,255,255,0.03);">';
            html += '<input type="checkbox" ' + checked + ' onchange="TechInd._toggleOverlay(\'' + k + '\')" style="margin:0;cursor:pointer;">';
            html += '<span style="color:' + (def.color || '#ccc') + ';">' + def.label + '</span>';
            html += '</label>';
        });
        html += '</div>';

        // 组叠加
        html += '<div style="padding:2px 6px 6px;display:flex;flex-wrap:wrap;gap:3px;">';
        GROUP_OVERLAY_KEYS.forEach(function(k) {
            var def = OVERLAY_DEFS[k];
            if (!def) return;
            var checked = _overlayState[k] ? ' checked' : '';
            var allNull = def.fields.every(function(f) { return ind[f] == null; });
            html += '<label style="display:inline-flex;align-items:center;gap:2px;font-size:9px;cursor:pointer;padding:1px 4px;border-radius:2px;background:rgba(255,255,255,0.03);' + (allNull ? 'opacity:0.3;' : '') + '">';
            html += '<input type="checkbox" ' + checked + ' onchange="TechInd._toggleOverlay(\'' + k + '\')" style="margin:0;cursor:pointer;">';
            html += '<span>' + def.label + '</span>';
            html += '</label>';
        });
        html += '</div>';

        // ── 区域2: 副图选择 (Tab 风格) ──
        html += '<div class="cat-title" style="margin-top:4px;">📊 副图</div>';
        html += '<div style="padding:2px 6px 4px;display:flex;flex-wrap:wrap;gap:2px;">';
        SUB_CHART_ORDER.forEach(function(k) {
            var def = SUB_CHART_DEFS[k];
            if (!def) return;
            var isActive = _activeSubChart === k;
            var hasData = def.fields.some(function(f) { return ind[f] != null; });
            html += '<span onclick="TechInd._selectSubChart(\'' + k + '\')" style="display:inline-block;padding:2px 6px;font-size:9px;border-radius:3px;cursor:pointer;' +
                (isActive ? 'background:var(--accent-blue);color:#fff;' : 'background:rgba(255,255,255,0.04);color:var(--text-dim);') +
                (hasData ? '' : 'opacity:0.35;') + '">' + def.label + '</span>';
        });
        html += '</div>';

        // ── 区域3: 当前副图指标值 ──
        var activeDef = SUB_CHART_DEFS[_activeSubChart];
        if (activeDef) {
            html += '<div class="cat-title" style="margin-top:2px;">🔹 ' + activeDef.label + ' 当前值</div>';
            html += '<div style="padding:4px 8px;font-size:9px;display:flex;flex-wrap:wrap;gap:4px 8px;">';
            activeDef.fields.forEach(function(f) {
                var v = ind[f];
                var isText = textFields[f];
                var color = isText ? '#a78bfa' : (_valueColor(f, v));
                var vs = _fmtValue(v, f);
                html += '<span><span style="color:var(--text-micro);">' + f + ':</span> <span style="color:' + color + ';font-family:var(--font-mono);">' + vs + '</span></span>';
            });
            html += '</div>';
        }

        document.getElementById('indicator-cards').innerHTML = html || '<div style="color:var(--text-micro);padding:10px;">暂无指标数据</div>';
    }

    // ── 叠加层切换 ──
    function _toggleOverlay(key) {
        _overlayState[key] = !_overlayState[key];
        _renderMainChart();
        // 只更新左面板的 checkbox 视觉, 不重建整个左面板
        var cbs = document.querySelectorAll('.ind-checkbox-overlay');
        cbs.forEach(function(cb) {
            if (cb.dataset.key === key) cb.checked = _overlayState[key];
        });
    }

    // ── 副图切换 ──
    function _selectSubChart(key) {
        if (!SUB_CHART_DEFS[key]) return;
        _activeSubChart = key;
        // 更新左面板: 重新渲染 (或纯 tab 切换)
        _renderCards();
        _renderSubChart();
    }

    // ── 时间范围 ──
    function _setTimeRange(days) {
        _chartDays = days;
        if (currentMode === 'stock' && currentStock) {
            selectStock(); // 重新加载
        }
    }

    function _renderChartControls() {
        var html = '<div class="chart-controls" style="display:flex;gap:6px;align-items:center;padding:4px 0;">';
        html += '<span style="font-size:9px;color:var(--text-micro);">时间:</span>';
        var ranges = [7, 30, 90, 180, 365, 0];
        var rangeLabels = ['7d', '30d', '90d', '180d', '365d', 'Max'];
        ranges.forEach(function(d, idx) {
            var active = _chartDays === d ? 'var(--accent-gold);border-color:var(--accent-gold);' : 'var(--text-micro);border-color:var(--border-color);';
            html += '<button onclick="TechInd._setTimeRange(' + d + ')" style="background:none;border:1px solid;padding:2px 6px;border-radius:3px;cursor:pointer;font-size:9px;color:' + active + '">' + rangeLabels[idx] + '</button>';
        });
        html += '</div>';
        return html;
    }

    // ═══ ★ V4: 主图渲染 (K线 + 成交量 + 叠加层) ═══

    function _renderMainChart() {
        var container = document.getElementById('main-chart');
        var titleEl = document.getElementById('chart-title');
        if (!container) return;

        var merged = _getMergedData();
        if (!merged || !merged.dates.length) {
            titleEl.innerHTML = (currentStock || '') + ' — 指标时间序列';
            container.innerHTML = '<div style="color:var(--text-micro);padding:40px;text-align:center;">无 K 线数据' +
                (_indicatorHistory && _indicatorHistory.dates ? '，但指标数据可用，请切换副图查看' : '') + '</div>';
            return;
        }

        titleEl.innerHTML = (currentStock || '') + ' — 主图' + _renderChartControls();

        // Dispose old chart
        var old = echarts.getInstanceByDom(container);
        if (old) old.dispose();

        var dates = merged.dates;
        var ohlc = merged.ohlc;
        var volumes = merged.volumes;
        var aligned = merged.aligned;

        var chart = echarts.init(container);
        _chartInstances.push(chart);

        // ── 构建 series ──
        var series = [];

        // 1. K线 (始终显示)
        series.push({
            name: 'K线', type: 'candlestick',
            data: ohlc,
            xAxisIndex: 0, yAxisIndex: 0,
            itemStyle: {
                color: '#2ed573',
                color0: '#ff4757',
                borderColor: '#2ed573',
                borderColor0: '#ff4757'
            },
            barWidth: '60%'
        });

        // 2. 成交量 (始终显示)
        series.push({
            name: '成交量', type: 'bar',
            data: volumes,
            xAxisIndex: 1, yAxisIndex: 1,
            itemStyle: {
                color: function(p) {
                    var daily = _dailyData[p.dataIndex];
                    return daily && daily.close >= daily.open ? 'rgba(46,213,115,0.35)' : 'rgba(255,71,87,0.35)';
                }
            },
            barWidth: '60%'
        });

        // 3. 叠加层 (按 _overlayState)
        series = series.concat(_buildOverlaySeries(aligned));

        // ── 生成 option ──
        var option = {
            tooltip: {
                trigger: 'axis',
                axisPointer: { type: 'cross' },
                // 自定义 K 线 tooltip
                formatter: function(params) {
                    var kLine = params[0];
                    if (!kLine || !kLine.data) return '';
                    var dIdx = kLine.dataIndex;
                    var dateStr = dates[dIdx] || '';
                    var o = ohlc[dIdx][0], c = ohlc[dIdx][1], l = ohlc[dIdx][2], h = ohlc[dIdx][3];
                    var vol = volumes[dIdx] || 0;
                    var changePct = o > 0 ? ((c - o) / o * 100).toFixed(2) : '—';
                    var html = '<div style="font-size:11px;">' + dateStr + '</div>';
                    html += '开: ' + o.toFixed(2) + ' 收: ' + c.toFixed(2) + ' 低: ' + l.toFixed(2) + ' 高: ' + h.toFixed(2) + ' (' + changePct + '%)<br/>';
                    html += '成交量: ' + (vol / 1e4).toFixed(0) + '万股';
                    // 叠加层数值
                    for (var i = 1; i < params.length; i++) {
                        var p = params[i];
                        if (p && p.value != null && p.seriesName) {
                            html += '<br/>' + p.seriesName + ': ' + _fmtValue(p.value);
                        }
                    }
                    return html;
                }
            },
            legend: {
                data: _getLegendData(series),
                textStyle: { color: '#999', fontSize: 9 },
                bottom: 0, type: 'scroll'
            },
            grid: [
                { left: '8%', right: '5%', top: '3%', height: '55%' },
                { left: '8%', right: '5%', top: '63%', height: '15%' }
            ],
            xAxis: [
                { type: 'category', data: dates, gridIndex: 0, axisLabel: { show: false }, axisLine: { lineStyle: { color: '#333' } } },
                { type: 'category', data: dates, gridIndex: 1, axisLabel: { fontSize: 8, rotate: 30, color: '#999' }, axisLine: { lineStyle: { color: '#333' } } }
            ],
            yAxis: [
                { type: 'value', scale: true, gridIndex: 0, splitLine: { lineStyle: { color: '#1a1a1a' } }, axisLabel: { fontSize: 9 } },
                { type: 'value', scale: true, gridIndex: 1, splitLine: { show: false }, axisLabel: { fontSize: 8, color: '#999' } }
            ],
            dataZoom: [
                { type: 'inside', xAxisIndex: [0, 1] }
            ],
            series: series
        };

        chart.setOption(option);
    }

    // ── 构建叠加层 line series ──
    function _buildOverlaySeries(aligned) {
        var series = [];

        MA_KEYS.forEach(function(k) {
            if (!_overlayState[k]) return;
            var def = OVERLAY_DEFS[k];
            if (!def) return;
            var data = aligned[def.fields[0]];
            if (!data) return;
            series.push({
                name: def.label, type: 'line',
                data: data, xAxisIndex: 0, yAxisIndex: 0,
                smooth: true, symbol: 'none',
                lineStyle: { color: def.color, width: 1.2 }
            });
        });

        GROUP_OVERLAY_KEYS.forEach(function(k) {
            if (!_overlayState[k]) return;
            switch (k) {
                case 'bollinger':
                    var upper = aligned['bb_upper'];
                    var mid = aligned['bb_mid'];
                    var lower = aligned['bb_lower'];
                    if (upper && mid && lower) {
                        series.push({
                            name: '布林上轨', type: 'line',
                            data: upper, xAxisIndex: 0, yAxisIndex: 0,
                            smooth: true, symbol: 'none',
                            lineStyle: { color: 'rgba(255,71,87,0.5)', width: 1 }
                        });
                        series.push({
                            name: '布林中轨', type: 'line',
                            data: mid, xAxisIndex: 0, yAxisIndex: 0,
                            smooth: true, symbol: 'none',
                            lineStyle: { color: '#ffa502', width: 1, type: 'dashed' }
                        });
                        series.push({
                            name: '布林下轨', type: 'line',
                            data: lower, xAxisIndex: 0, yAxisIndex: 0,
                            smooth: true, symbol: 'none',
                            lineStyle: { color: 'rgba(46,213,115,0.5)', width: 1 }
                        });
                    }
                    break;
                case 'vwap':
                    var vwapData = aligned['vwap'];
                    if (vwapData) {
                        series.push({
                            name: 'VWAP', type: 'line',
                            data: vwapData, xAxisIndex: 0, yAxisIndex: 0,
                            smooth: true, symbol: 'none',
                            lineStyle: { color: '#f368e0', width: 1, type: 'dotted' }
                        });
                    }
                    break;
                case 'chip_price':
                    var peak = aligned['chip_peak_price'];
                    var cost = aligned['chip_avg_cost'];
                    if (peak) {
                        series.push({
                            name: '筹码峰值', type: 'line',
                            data: peak, xAxisIndex: 0, yAxisIndex: 0,
                            smooth: true, symbol: 'none',
                            lineStyle: { color: '#22d3ee', width: 1, type: 'dashed' }
                        });
                    }
                    if (cost) {
                        series.push({
                            name: '筹码成本', type: 'line',
                            data: cost, xAxisIndex: 0, yAxisIndex: 0,
                            smooth: true, symbol: 'none',
                            lineStyle: { color: '#fb6da7', width: 1, type: 'dashed' }
                        });
                    }
                    break;
            }
        });

        return series;
    }

    function _getLegendData(series) {
        return series.filter(function(s) { return s.name; }).map(function(s) { return s.name; });
    }

    // ═══ ★ V4: 副图渲染 (Tab 切换, 一次一图) ═══

    function _renderSubChart() {
        var container = document.getElementById('sub-chart');
        if (!container) return;

        var old = echarts.getInstanceByDom(container);
        if (old) old.dispose();

        var def = SUB_CHART_DEFS[_activeSubChart];
        if (!def) {
            container.innerHTML = '<div style="color:var(--text-micro);padding:20px;text-align:center;">选择副图指标</div>';
            return;
        }

        // 筹码分布图是特殊子图: 取单日快照, 非时间序列
        if (def.style === 'chip_dist') {
            _renderChipDistSubChart(container);
            return;
        }

        // 从合并数据中提取副图字段
        var merged = _getMergedData();
        if (!merged || !merged.dates || !merged.dates.length) {
            // 可能只有指标数据没有日线数据
            if (_indicatorHistory && _indicatorHistory.dates && _indicatorHistory.dates.length) {
                // _indicatorHistory is newest-first, reverse to chronological
                var dates = _indicatorHistory.dates.slice().reverse();
                var fields = {};
                for (var f in _indicatorHistory.fields) {
                    fields[f] = _indicatorHistory.fields[f].slice().reverse();
                }
                merged = { dates: dates, aligned: fields };
            } else {
                container.innerHTML = '<div style="color:var(--text-micro);padding:20px;text-align:center;">无指标历史数据</div>';
                return;
            }
        }

        // 检查数据是否存在
        var hasAnyData = def.fields.some(function(f) {
            return merged.aligned[f] && merged.aligned[f].some(function(v) { return v != null; });
        });

        if (!hasAnyData) {
            container.innerHTML = '<div style="color:var(--text-micro);padding:20px;text-align:center;">暂无 ' + def.label + ' 历史数据</div>';
            return;
        }

        // 构建简化的 data 结构供渲染器使用
        var subData = {
            dates: merged.dates,
            fields: {}
        };
        def.fields.forEach(function(f) {
            subData.fields[f] = merged.aligned[f] || [];
        });

        // 用现成的渲染器
        var chart = echarts.init(container);
        _chartInstances.push(chart);
        _renderGroupChart(chart, def, subData);
    }

    function _renderGroupChart(chart, def, data) {
        var dates = data.dates;
        var fields = def.fields;
        var style = def.style;

        switch (style) {
            case 'macd':  _renderMACD(chart, dates, data, fields); break;
            case 'rsi':   _renderRSI(chart, dates, data, fields); break;
            case 'ranged': _renderRanged(chart, dates, data, fields, def.min || 0, def.max || 100); break;
            default:      _renderLines(chart, dates, data, fields); break;
        }
    }

    // ── MACD ──
    function _renderMACD(chart, dates, data, fields) {
        var hist = data.fields['macd_hist'] || [];
        var macd = data.fields['macd'] || [];
        var signal = data.fields['macd_signal'] || [];
        chart.setOption({
            tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
            grid: { left: '8%', right: '5%', top: '8%', bottom: '10%' },
            xAxis: { type: 'category', data: dates, axisLabel: { fontSize: 8, rotate: 30, show: true } },
            yAxis: { type: 'value', scale: true, splitLine: { lineStyle: { color: '#1a1a1a' } }, axisLabel: { fontSize: 9 } },
            series: [
                { name: 'MACD Hist', type: 'bar', data: hist,
                    itemStyle: { color: function(p) { return p.value >= 0 ? 'rgba(46,213,115,0.7)' : 'rgba(255,71,87,0.7)'; } } },
                { name: 'MACD', type: 'line', data: macd, smooth: true, symbol: 'none', lineStyle: { color: '#60a5fa', width: 1.5 } },
                { name: 'Signal', type: 'line', data: signal, smooth: true, symbol: 'none', lineStyle: { color: '#ffa502', width: 1.5 } }
            ]
        });
    }

    // ── RSI ──
    function _renderRSI(chart, dates, data, fields) {
        var values = data.fields['rsi'] || [];
        chart.setOption({
            tooltip: { trigger: 'axis' },
            grid: { left: '8%', right: '5%', top: '8%', bottom: '10%' },
            xAxis: { type: 'category', data: dates, axisLabel: { fontSize: 8, rotate: 30 } },
            yAxis: { type: 'value', min: 0, max: 100, splitLine: { lineStyle: { color: '#1a1a1a' } }, axisLabel: { fontSize: 9 } },
            series: [{
                name: 'RSI', type: 'line', data: values,
                smooth: true, symbol: 'none', lineStyle: { color: '#a29bfe', width: 2 },
                markLine: {
                    silent: true,
                    data: [
                        { yAxis: 70, label: { formatter: '超买 70', color: '#ff4757', fontSize: 9 }, lineStyle: { color: '#ff4757', type: 'dashed', width: 1 } },
                        { yAxis: 30, label: { formatter: '超卖 30', color: '#2ed573', fontSize: 9 }, lineStyle: { color: '#2ed573', type: 'dashed', width: 1 } },
                        { yAxis: 50, label: { formatter: '50', color: '#666', fontSize: 8 }, lineStyle: { color: '#333', type: 'dotted', width: 1 } }
                    ]
                }
            }]
        });
    }

    // ── 0-100 范围 (KDJ) ──
    function _renderRanged(chart, dates, data, fields, minV, maxV) {
        var series = fields.map(function(f, i) {
            var color = ['#60a5fa', '#2ed573', '#ffa502'][i % 3];
            return { name: f, type: 'line', data: data.fields[f] || [], smooth: true, symbol: 'none', lineStyle: { color: color, width: 1.5 } };
        });
        chart.setOption({
            tooltip: { trigger: 'axis' },
            legend: { data: fields, textStyle: { color: '#999' }, bottom: 0 },
            grid: { left: '8%', right: '5%', top: '8%', bottom: '22%' },
            xAxis: { type: 'category', data: dates, axisLabel: { fontSize: 8, rotate: 30 } },
            yAxis: { type: 'value', min: minV, max: maxV, splitLine: { lineStyle: { color: '#1a1a1a' } }, axisLabel: { fontSize: 9 } },
            series: series
        });
    }

    // ── 普通线图 ──
    function _renderLines(chart, dates, data, fields) {
        var series = fields.map(function(f, i) {
            var color = SERIES_COLORS[i % SERIES_COLORS.length];
            return { name: f, type: 'line', data: data.fields[f] || [], smooth: true, symbol: 'none', lineStyle: { color: color, width: 1.5 } };
        });
        chart.setOption({
            tooltip: { trigger: 'axis' },
            legend: { data: fields, textStyle: { color: '#999' }, bottom: 0 },
            grid: { left: '8%', right: '5%', top: '8%', bottom: '22%' },
            xAxis: { type: 'category', data: dates, axisLabel: { fontSize: 8, rotate: 30 } },
            yAxis: { type: 'value', scale: true, splitLine: { lineStyle: { color: '#1a1a1a' } }, axisLabel: { fontSize: 9 } },
            series: series
        });
    }

    // ═══ ★ V4: 筹码信息卡片 ═══

    function _renderChipCard() {
        var container = document.getElementById('chip-card');
        if (!container) return;
        var ind = _cachedSnapshot;
        if (!ind) {
            container.style.display = 'none';
            return;
        }
        container.style.display = '';

        var pattern = ind['chip_pattern'];
        var signal = ind['chip_signal'];
        var concen = ind['chip_concentration'];
        var peakPx = ind['chip_peak_price'];
        var avgCost = ind['chip_avg_cost'];
        var isSingle = ind['chip_is_single_peak'];

        var signalLabel = '';
        var signalColor = '';
        if (signal === 'BUY') { signalLabel = '买入'; signalColor = 'var(--accent-green)'; }
        else if (signal === 'SELL') { signalLabel = '卖出'; signalColor = 'var(--accent-red)'; }
        else { signalLabel = signal || '—'; signalColor = 'var(--text-dim)'; }

        var concenLabel = (concen != null) ? concen.toFixed(4) : '—';
        var concenDesc = '';
        if (concen != null) {
            concenDesc = concen < 0.12 ? '密集' : (concen > 0.20 ? '发散' : '较集中');
        }

        var html = '<div style="display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center;font-size:10px;padding:4px 0;">';
        if (pattern) {
            html += '<span><span style="color:var(--text-micro);">形态:</span> <span style="color:#a78bfa;">' + escHtml(pattern) + '</span></span>';
        }
        html += '<span><span style="color:var(--text-micro);">信号:</span> <span style="color:' + signalColor + ';font-weight:600;">' + signalLabel + '</span></span>';
        html += '<span><span style="color:var(--text-micro);">集中度:</span> <span style="color:var(--text-dim);font-family:var(--font-mono);">' + concenLabel + '</span> <span style="color:' + (concen < 0.12 ? 'var(--accent-green)' : 'var(--accent-red)') + ';font-size:8px;">(' + concenDesc + ')</span></span>';
        if (peakPx != null) {
            html += '<span><span style="color:var(--text-micro);">峰值:</span> <span style="color:var(--text-dim);font-family:var(--font-mono);">' + peakPx.toFixed(2) + '</span></span>';
        }
        if (avgCost != null) {
            html += '<span><span style="color:var(--text-micro);">均价:</span> <span style="color:var(--text-dim);font-family:var(--font-mono);">' + avgCost.toFixed(2) + '</span></span>';
        }
        if (isSingle != null) {
            html += '<span><span style="color:var(--text-micro);">单峰:</span> <span style="color:' + (isSingle ? 'var(--accent-green)' : 'var(--text-dim)') + ';">' + (isSingle ? '✓' : '—') + '</span></span>';
        }

        // chip_distribution 查看按钮
        html += '<span style="margin-left:auto;"><button onclick="TechInd._showChipDist(\'' + currentStock + '\')" style="background:transparent;border:1px solid var(--border-color);color:var(--text-dim);padding:2px 8px;border-radius:3px;cursor:pointer;font-size:9px;">📊 筹码分布图</button></span>';

        html += '</div>';
        container.innerHTML = html;
    }

    // ── 筹码分布图 (水平条形 + 峰谷标记) ──
    function _showChipDist(code) {
        _disposeAllCharts();
        document.getElementById('chart-title').innerHTML = code + ' — 筹码分布 <span onclick="TechInd.selectStock()" style="color:var(--accent-blue);cursor:pointer;font-size:10px;margin-left:12px;">← 返回主图</span>';
        document.getElementById('chart-info').textContent = '加载中...';

        var container = document.getElementById('main-chart');
        fetch(API + '/quant/indicators/chip-dist/' + code).then(function(r) { return r.json(); }).then(function(d) {
            var data = d.data;
            if (!data) { document.getElementById('chart-info').textContent = '无数据'; return; }

            // 峰值检测 (局部极大值)
            var pcts = data.chip_pct;
            var prices = data.prices;
            var peaks = [];
            var valleys = [];
            var maxPct = Math.max.apply(null, pcts);
            var pkThreshold = maxPct * 0.35;
            for (var i = 1; i < pcts.length - 1; i++) {
                if (pcts[i] > pcts[i-1] && pcts[i] > pcts[i+1] && pcts[i] > pkThreshold) {
                    peaks.push({ price: prices[i], pct: pcts[i], index: i });
                }
                if (pcts[i] < pcts[i-1] && pcts[i] < pcts[i+1] && pcts[i] < 1.0 && maxPct > 3) {
                    valleys.push({ price: prices[i], pct: pcts[i], index: i });
                }
            }
            peaks.sort(function(a, b) { return b.pct - a.pct; });
            peaks = peaks.slice(0, 6);
            peaks.sort(function(a, b) { return a.index - b.index; });

            document.getElementById('chart-info').textContent = '获利' + data.winner_close + '% | 均成本' + data.avg_cost +
                ' | 集中度' + data.concentration_90 + '% | 峰值' + peaks.length + '个 | 现价' + data.close.toFixed(2);

            var chart = echarts.init(container);
            _chartInstances.push(chart);

            // markLines: 峰值 + 成本 + 现价 + 5%/95% 分位
            var markLines = peaks.map(function(pk) { return {
                xAxis: parseFloat(pk.price),
                label: { formatter: '峰值 ' + pk.price + ' (' + pk.pct.toFixed(1) + '%)', color: '#22d3ee', fontSize: 8, position: 'insideEndTop' },
                lineStyle: { color: '#22d3ee', type: 'dashed', width: 0.8 }
            }; });
            markLines.push({ xAxis: data.avg_cost, label: { formatter: '成本 ' + data.avg_cost, color: '#fb6da7', fontSize: 8, position: 'insideEndTop' }, lineStyle: { color: '#fb6da7', type: 'solid', width: 1.5 } });
            markLines.push({ xAxis: data.close, label: { formatter: '现价 ' + data.close.toFixed(2), color: '#fff', fontSize: 8, position: 'insideEndTop' }, lineStyle: { color: '#fff', type: 'solid', width: 1.5 } });

            chart.setOption({
                tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' },
                    formatter: function(params) {
                        var p = params[0]; if (!p) return '';
                        var idx = p.dataIndex;
                        var isPeak = peaks.some(function(pk) { return Math.abs(pk.index - idx) < 2; });
                        var isValley = valleys.some(function(v) { return Math.abs(v.index - idx) < 2; });
                        var h = '<div style="font-size:11px;">价格: <b>' + prices[idx] + '</b></div>';
                        h += '筹码占比: ' + pcts[idx].toFixed(2) + '%';
                        if (isPeak) h += ' <span style="color:#22d3ee;">★峰值</span>';
                        if (isValley) h += ' <span style="color:#ffa502;">▽谷值</span>';
                        return h;
                    }
                },
                grid: { left: '10%', right: '10%', top: '8%', bottom: '8%' },
                xAxis: { type: 'value', splitLine: { lineStyle: { color: '#1a1a1a' } }, axisLabel: { fontSize: 9 } },
                yAxis: { type: 'category', data: prices, axisLabel: { fontSize: 8 }, splitLine: { show: false } },
                series: [{
                    type: 'bar', data: pcts, barWidth: '80%',
                    itemStyle: {
                        color: function(p) {
                            var idx = p.dataIndex;
                            var price = parseFloat(prices[idx]);
                            if (peaks.some(function(pk) { return Math.abs(pk.index - idx) < 2; })) return '#22d3ee';
                            if (valleys.some(function(v) { return Math.abs(v.index - idx) < 2; })) return '#ffa502';
                            return price < data.avg_cost ? 'rgba(20,177,67,0.7)' : 'rgba(239,35,42,0.7)';
                        }
                    },
                    markLine: { silent: true, symbol: 'none', data: markLines }
                }],
                graphic: [{
                    type: 'group', left: 8, bottom: 22,
                    children: [
                        { type: 'text', left: 0, style: { text: '■ 峰值', fill: '#22d3ee', fontSize: 9 } },
                        { type: 'text', left: 55, style: { text: '■ 谷值', fill: '#ffa502', fontSize: 9 } },
                        { type: 'text', left: 110, style: { text: '▲ 获利盘', fill: 'rgba(20,177,67,0.7)', fontSize: 9 } },
                        { type: 'text', left: 175, style: { text: '▼ 套牢盘', fill: 'rgba(239,35,42,0.7)', fontSize: 9 } },
                    ]
                }]
            });
        }).catch(function() {
            document.getElementById('chart-info').textContent = '加载失败';
        });
    }

    function _disposeAllCharts() {
        _chartInstances.forEach(function(c) { if (c) c.dispose(); });
        _chartInstances = [];
    }

    // ── 副图中的筹码分布 (单日切片, 纵轴价格, 横轴量) ──
    function _renderChipDistSubChart(container) {
        if (!currentStock) {
            container.innerHTML = '<div style="color:var(--text-micro);padding:20px;text-align:center;">请先选择股票</div>';
            return;
        }
        container.innerHTML = '<div style="color:var(--text-micro);padding:20px;text-align:center;">加载中...</div>';
        fetch(API + '/quant/indicators/chip-dist/' + currentStock).then(function(r) { return r.json(); }).then(function(d) {
            var data = d.data;
            if (!data) { container.innerHTML = '<div style="color:var(--text-micro);padding:20px;text-align:center;">暂无筹码分布数据</div>'; return; }

            // 下采样: 200 个价格点对副图太密, 降采样到约 60 点
            var binCount = data.prices.length;
            var step = Math.max(1, Math.floor(binCount / 60));
            var prices = [], pcts = [];
            for (var i = 0; i < binCount; i += step) {
                prices.push(data.prices[i]);
                var sum = 0;
                for (var j = 0; j < step && i + j < binCount; j++) sum += data.chip_pct[i + j];
                pcts.push(sum);
            }

            // 峰值检测 (原始数据上检测, 索引映射到下采样后)
            var peakThreshold = Math.max.apply(null, data.chip_pct) * 0.35;
            var rawPeaks = [];
            for (var i = 1; i < data.chip_pct.length - 1; i++) {
                if (data.chip_pct[i] > data.chip_pct[i-1] && data.chip_pct[i] > data.chip_pct[i+1] && data.chip_pct[i] > peakThreshold)
                    rawPeaks.push({ price: data.prices[i], pct: data.chip_pct[i], index: Math.floor(i / step) });
            }
            rawPeaks.sort(function(a,b) { return b.pct - a.pct; });
            rawPeaks = rawPeaks.slice(0, 5);
            var peaks = rawPeaks;

            var chart = echarts.init(container);
            _chartInstances.push(chart);

            var markLines = peaks.map(function(pk) { return {
                xAxis: parseFloat(pk.price),
                label: { formatter: '峰值 ' + pk.price + ' (' + pk.pct.toFixed(1) + '%)', color: '#22d3ee', fontSize: 7, position: 'insideEndTop' },
                lineStyle: { color: '#22d3ee', type: 'dashed', width: 0.6 }
            }; });
            markLines.push({ xAxis: data.avg_cost, label: { formatter: '成本', color: '#fb6da7', fontSize: 7 }, lineStyle: { color: '#fb6da7', type: 'solid', width: 1 } });
            markLines.push({ xAxis: data.close, label: { formatter: '现价', color: '#fff', fontSize: 7 }, lineStyle: { color: '#fff', type: 'solid', width: 1 } });

            chart.setOption({
                tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' },
                    formatter: function(params) {
                        var p = params[0]; if (!p) return '';
                        var idx = p.dataIndex;
                        var html = '<div style="font-size:10px;">价格: <b>' + prices[idx] + '</b></div>';
                        html += '筹码占比: ' + pcts[idx].toFixed(2) + '%';
                        if (peaks.some(function(pk) { return Math.abs(pk.index - idx) < 2; })) html += ' <span style="color:#22d3ee;">★峰值</span>';
                        return html;
                    }
                },
                grid: { left: '12%', right: '10%', top: '6%', bottom: '8%' },
                xAxis: { type: 'value', splitLine: { lineStyle: { color: '#1a1a1a' } }, axisLabel: { fontSize: 8 } },
                yAxis: { type: 'category', data: prices, axisLabel: { fontSize: 7 }, splitLine: { show: false } },
                series: [{
                    type: 'bar', data: pcts, barWidth: '75%',
                    itemStyle: {
                        color: function(p) {
                            var idx = p.dataIndex;
                            if (peaks.some(function(pk) { return Math.abs(pk.index - idx) < 2; })) return '#22d3ee';
                            return parseFloat(prices[idx]) < data.avg_cost ? 'rgba(20,177,67,0.6)' : 'rgba(239,35,42,0.6)';
                        }
                    },
                    markLine: { silent: true, symbol: 'none', data: markLines }
                }],
                graphic: [{
                    type: 'group', left: 8, bottom: 20,
                    children: [
                        { type: 'text', left: 0, style: { text: '■峰', fill: '#22d3ee', fontSize: 8 } },
                        { type: 'text', left: 30, style: { text: '获利' + data.winner_close + '%', fill: 'rgba(20,177,67,0.6)', fontSize: 8 } },
                        { type: 'text', left: 80, style: { text: '集中度' + data.concentration_90 + '%', fill: '#999', fontSize: 8 } },
                    ]
                }]
            });
        }).catch(function() {
            container.innerHTML = '<div style="color:var(--text-micro);padding:20px;text-align:center;">筹码分布加载失败</div>';
        });
    }

    // ══════════════════════════════════════════════════════════════
    // Field Mode (Enhanced: sortable table + filter + stats + CSV)
    // ══════════════════════════════════════════════════════════════
    function selectField() {
        var field = document.getElementById('field-select').value;
        if (!field) return;
        currentField = field;
        _sortCol = '';
        _sortDir = '';
        _filterOp = '';
        _filterVal = '';
        _loadFieldData(field);
    }

    function _loadFieldData(field) {
        var tableEl = document.getElementById('field-rank-table');
        tableEl.innerHTML = '<div style="color:var(--text-micro);padding:10px;">加载中...</div>';

        fetch(API + '/quant/indicators/field/' + field).then(function(r) { return r.json(); }).then(function(d) {
            var items = d.data || [];
            _fieldItems = items.map(function(i) {
                var raw = i.value;
                var numVal = (raw != null && typeof raw === 'number') ? raw : (raw != null && !isNaN(Number(raw)) ? Number(raw) : null);
                return {
                    code: i.code,
                    name: i.name || getStockName(i.code) || '',
                    value: raw,
                    numValue: numVal,
                    date: i.date || i.trade_date || ''
                };
            });
            _renderFieldUI(field, _fieldItems);
        }).catch(function() {
            tableEl.innerHTML = '<div style="color:var(--accent-red);padding:20px;">加载失败</div>';
        });
    }

    function _renderFieldUI(field, items) {
        var tableEl = document.getElementById('field-rank-table');
        var infoEl = document.getElementById('field-info-text');

        var filtered = _applyFilterToItems(items);

        if (_sortCol === 'value' && _sortDir) {
            filtered.sort(function(a, b) {
                var va = a.numValue, vb = b.numValue;
                if (va == null && vb == null) return 0;
                if (va == null) return 1;
                if (vb == null) return -1;
                return _sortDir === 'asc' ? va - vb : vb - va;
            });
        } else if (_sortCol === 'code' && _sortDir) {
            filtered.sort(function(a, b) {
                var c = a.code.localeCompare(b.code);
                return _sortDir === 'asc' ? c : -c;
            });
        }

        infoEl.textContent = filtered.length + ' / ' + items.length + ' 只股票有数据';

        var statsHtml = _renderStatsBar(filtered);
        var filterHtml = _renderFilterBar(field);
        var tableHtml = _renderRankingTable(filtered, field);
        var chartHtml = '<div id="field-chart-container" style="height:200px;margin-top:4px;"></div>';
        var exportHtml = '<div style="text-align:right;padding:4px 0;">';
        exportHtml += '<button onclick="TechInd._exportFieldCSV(\'' + field + '\')" style="background:transparent;border:1px solid var(--text-dim);color:var(--text-dim);padding:3px 10px;border-radius:3px;cursor:pointer;font-size:10px;">📥 导出CSV</button>';
        exportHtml += '</div>';

        tableEl.innerHTML = statsHtml + filterHtml + exportHtml + tableHtml + chartHtml;

        var top15 = filtered.slice(0, 15);
        _renderFieldChart(field, top15);
    }

    function _renderStatsBar(items) {
        var vals = items.map(function(i) { return i.numValue; }).filter(function(v) { return v != null && !isNaN(v); });
        if (!vals.length) return '<div style="font-size:10px;color:var(--text-micro);padding:4px 0;">无数值数据</div>';

        vals.sort(function(a, b) { return a - b; });
        var count = vals.length;
        var minV = vals[0];
        var maxV = vals[vals.length - 1];
        var sum = vals.reduce(function(a, b) { return a + b; }, 0);
        var avg = sum / count;
        var median;
        if (count % 2 === 0) {
            median = (vals[count / 2 - 1] + vals[count / 2]) / 2;
        } else {
            median = vals[Math.floor(count / 2)];
        }

        return '<div class="stats-bar" style="display:flex;gap:12px;font-size:10px;color:var(--text-dim);padding:4px 0;border-bottom:1px solid rgba(255,255,255,0.04);">' +
            '<span>📊 共 <b style="color:#fff;">' + count + '</b> 只</span>' +
            '<span>最小: <b style="color:var(--accent-blue);">' + _fmtValue(minV) + '</b></span>' +
            '<span>最大: <b style="color:var(--accent-blue);">' + _fmtValue(maxV) + '</b></span>' +
            '<span>均值: <b style="color:var(--accent-blue);">' + _fmtValue(avg) + '</b></span>' +
            '<span>中位数: <b style="color:var(--accent-blue);">' + _fmtValue(median) + '</b></span>' +
            '</div>';
    }

    function _renderFilterBar(field) {
        return '<div class="filter-bar" style="display:flex;gap:6px;align-items:center;padding:4px 0;font-size:10px;">' +
            '<span style="color:var(--text-micro);">筛选:</span>' +
            '<select id="filter-operator" style="background:#000;border:1px solid var(--border-color);color:#fff;padding:2px 6px;border-radius:3px;font-size:10px;width:50px;">' +
            '<option value="">—</option>' +
            '<option value=">" ' + (_filterOp === '>' ? 'selected' : '') + '>&gt;</option>' +
            '<option value=">=" ' + (_filterOp === '>=' ? 'selected' : '') + '>&gt;=</option>' +
            '<option value="<" ' + (_filterOp === '<' ? 'selected' : '') + '>&lt;</option>' +
            '<option value="<=" ' + (_filterOp === '<=' ? 'selected' : '') + '>&lt;=</option>' +
            '<option value="=" ' + (_filterOp === '=' ? 'selected' : '') + '>=</option>' +
            '</select>' +
            '<input type="text" id="filter-value" value="' + escHtml(_filterVal) + '" placeholder="数值" style="background:#000;border:1px solid var(--border-color);color:#fff;padding:2px 6px;border-radius:3px;font-size:10px;width:80px;">' +
            '<button onclick="TechInd._applyFilter()" style="background:transparent;border:1px solid var(--accent-green);color:var(--accent-green);padding:2px 8px;border-radius:3px;cursor:pointer;font-size:10px;">应用</button>' +
            '<button onclick="TechInd._resetFilter()" style="background:transparent;border:1px solid var(--text-micro);color:var(--text-micro);padding:2px 8px;border-radius:3px;cursor:pointer;font-size:10px;">重置</button>' +
            '</div>';
    }

    function _applyFilter() {
        var opEl = document.getElementById('filter-operator');
        var valEl = document.getElementById('filter-value');
        _filterOp = opEl ? opEl.value : '';
        _filterVal = valEl ? valEl.value : '';
        _renderFieldUI(currentField, _fieldItems);
    }

    function _resetFilter() {
        _filterOp = '';
        _filterVal = '';
        _renderFieldUI(currentField, _fieldItems);
    }

    function _applyFilterToItems(items) {
        if (!_filterOp || !_filterVal) return items.slice();
        var threshold = Number(_filterVal);
        if (isNaN(threshold)) return items.slice();
        return items.filter(function(i) {
            if (i.numValue == null) return false;
            switch (_filterOp) {
                case '>': return i.numValue > threshold;
                case '>=': return i.numValue >= threshold;
                case '<': return i.numValue < threshold;
                case '<=': return i.numValue <= threshold;
                case '=': return i.numValue === threshold;
                default: return true;
            }
        });
    }

    function _renderRankingTable(items, field) {
        var sortIcon = _sortCol === 'value' ? (_sortDir === 'asc' ? '↑' : '↓') : '⇅';
        var codeSortIcon = _sortCol === 'code' ? (_sortDir === 'asc' ? '↑' : '↓') : '⇅';

        var html = '<div class="fin-table-wrap" style="max-height:400px;"><table class="health-table" style="font-size:10px;"><thead><tr>' +
            '<th onclick="TechInd._onSortClick(\'code\')" style="cursor:pointer;user-select:none;">代码 ' + codeSortIcon + '</th>' +
            '<th>名称</th>' +
            '<th onclick="TechInd._onSortClick(\'value\')" style="cursor:pointer;text-align:right;user-select:none;">数值 ' + sortIcon + '</th>' +
            '<th>日期</th></tr></thead><tbody>';

        items.forEach(function(i) {
            var color = _valueColor(field, i.value);
            var valStr = _fmtValue(i.value, field);
            html += '<tr onclick="TechInd._viewStockFromField(\'' + i.code + '\')" style="cursor:pointer;" title="点击查看该股票全景">' +
                '<td style="color:var(--accent-blue);font-family:var(--font-mono);">' + escHtml(i.code) + '</td>' +
                '<td>' + escHtml(i.name) + '</td>' +
                '<td style="text-align:right;font-family:var(--font-mono);color:' + color + ';">' + valStr + '</td>' +
                '<td>' + (i.date || '') + '</td></tr>';
        });

        html += '</tbody></table></div>';
        return html;
    }

    function _onSortClick(col) {
        if (_sortCol === col) {
            _sortDir = _sortDir === 'asc' ? 'desc' : (_sortDir === 'desc' ? '' : 'asc');
            if (!_sortDir) _sortCol = '';
        } else {
            _sortCol = col;
            _sortDir = 'desc';
        }
        _renderFieldUI(currentField, _fieldItems);
    }

    function _viewStockFromField(code) {
        document.getElementById('stock-select').value = code;
        switchMode('stock');
        selectStock();
    }

    function _exportFieldCSV(field) {
        if (!_fieldItems.length) return;
        var lines = ['"代码","名称","数值","日期"'];
        _fieldItems.forEach(function(i) {
            lines.push('"' + i.code + '","' + (i.name || '') + '","' + _fmtValue(i.value) + '","' + (i.date || '') + '"');
        });
        _downloadCSV(lines.join('\n'), 'tech_field_' + field + '_' + _toDateStr() + '.csv');
    }

    function _renderFieldChart(field, items) {
        var container = document.getElementById('field-chart-container');
        if (!container) return;
        var existing = echarts.getInstanceByDom(container);
        if (existing) existing.dispose();

        if (!items.length) {
            container.innerHTML = '<div style="color:var(--text-micro);font-size:10px;text-align:center;padding:20px;">无数据</div>';
            return;
        }

        var chart = echarts.init(container);
        var names = items.map(function(i) { return i.code; }).reverse();
        var values = items.map(function(i) { return i.value; }).reverse();
        chart.setOption({
            tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
            grid: { left: '12%', right: '8%', top: '5%', bottom: '5%' },
            xAxis: { type: 'value', splitLine: { lineStyle: { color: '#1a1a1a' } }, axisLabel: { fontSize: 9 } },
            yAxis: { type: 'category', data: names, inverse: true, axisLabel: { fontSize: 9 } },
            series: [{
                type: 'bar', data: values,
                itemStyle: { color: function(p) { return new echarts.graphic.LinearGradient(0, 0, 1, 0, [{ offset: 0, color: '#60a5fa' }, { offset: 1, color: '#a78bfa' }]); } }
            }]
        });
    }

    // ══════════════════════════════════════════════════════════════
    // Cross Comparison (Tab 3)
    // ══════════════════════════════════════════════════════════════
    function _updateCompareUI() {
        var stockEl = document.getElementById('ti-compare-stocks');
        var indEl = document.getElementById('ti-compare-inds');

        if (stockEl) {
            if (compareStocks.length) {
                stockEl.innerHTML = compareStocks.map(function(code) {
                    var nm = getStockName(code);
                    return '<span style="display:inline-block;margin:2px;padding:2px 6px;background:rgba(255,255,255,0.05);border-radius:3px;font-size:10px;">' + escHtml(code) + ' ' + escHtml(nm) +
                        ' <span onclick="TechInd.removeStock(\'' + code + '\')" style="cursor:pointer;color:var(--accent-red);">&times;</span></span>';
                }).join('');
            } else {
                stockEl.innerHTML = '<span style="color:var(--text-micro);font-size:10px;">(空)</span>';
            }
        }
        if (indEl) {
            if (compareIndicators.length) {
                indEl.innerHTML = compareIndicators.map(function(name) {
                    var lbl = getFieldLabel(name) || name;
                    return '<span style="display:inline-block;margin:2px;padding:2px 6px;background:rgba(255,255,255,0.05);border-radius:3px;font-size:10px;">' + escHtml(lbl) +
                        ' <span onclick="TechInd.removeIndicator(\'' + name + '\')" style="cursor:pointer;color:var(--accent-red);">&times;</span></span>';
                }).join('');
            } else {
                indEl.innerHTML = '<span style="color:var(--text-micro);font-size:10px;">(空)</span>';
            }
        }
        var resultEl = document.getElementById('ti-compare-result');
        if (resultEl) resultEl.innerHTML = '';
    }

    function _saveCompareState() {
        localStorage.setItem('ti_compare_stocks', JSON.stringify(compareStocks));
        localStorage.setItem('ti_compare_inds', JSON.stringify(compareIndicators));
    }

    function addStock(code) {
        if (compareStocks.indexOf(code) >= 0) { Modal.alert('提示', '该股票已在列表中'); return; }
        if (compareStocks.length >= 6) { Modal.alert('提示', '最多比较 6 只股票'); return; }
        compareStocks.push(code);
        _saveCompareState();
        _updateCompareUI();
    }

    function removeStock(code) {
        compareStocks = compareStocks.filter(function(c) { return c !== code; });
        _saveCompareState();
        _updateCompareUI();
    }

    function addIndicator(name) {
        if (compareIndicators.indexOf(name) >= 0) { Modal.alert('提示', '该指标已在列表中'); return; }
        if (compareIndicators.length >= 10) { Modal.alert('提示', '最多比较 10 个指标'); return; }
        compareIndicators.push(name);
        _saveCompareState();
        _updateCompareUI();
    }

    function removeIndicator(name) {
        compareIndicators = compareIndicators.filter(function(i) { return i !== name; });
        _saveCompareState();
        _updateCompareUI();
    }

    function showAddStockDialog() {
        var html = '<div style="max-height:300px;overflow-y:auto;">';
        html += '<input type="text" id="compare-stock-search" placeholder="搜索..." oninput="TechInd._filterStockDialog(this.value)" style="width:100%;background:#000;border:1px solid var(--border-color);color:#fff;padding:4px 8px;border-radius:3px;font-size:11px;margin-bottom:6px;">';
        html += '<div id="compare-stock-list-container">';
        allStocksForCompare.forEach(function(s) {
            var selected = compareStocks.indexOf(s.stock_code) >= 0;
            html += '<div class="compare-stock-item" data-code="' + s.stock_code + '" data-name="' + escHtml(s.stock_name) + '" onclick="TechInd._pickStock(\'' + s.stock_code + '\')" style="padding:4px 6px;cursor:pointer;border-bottom:1px solid rgba(255,255,255,0.04);font-size:11px;' + (selected ? 'opacity:0.4;' : '') + '">';
            html += escHtml(s.stock_code) + ' ' + escHtml(s.stock_name);
            if (selected) html += ' <span style="color:var(--accent-green);font-size:9px;">✓</span>';
            html += '</div>';
        });
        html += '</div></div>';
        Modal.alert('选择股票（点击添加/移除）', html);
    }

    function _pickStock(code) {
        if (compareStocks.indexOf(code) >= 0) {
            removeStock(code);
        } else {
            if (compareStocks.length >= 6) { Modal.alert('提示', '最多比较 6 只股票'); return; }
            compareStocks.push(code);
            _saveCompareState();
        }
        _updateCompareUI();
        showAddStockDialog();
    }

    function _filterStockDialog(keyword) {
        var kw = keyword.toLowerCase();
        var items = document.querySelectorAll('.compare-stock-item');
        items.forEach(function(el) {
            var code = (el.dataset.code || '').toLowerCase();
            var name = (el.dataset.name || '').toLowerCase();
            el.style.display = (code.indexOf(kw) >= 0 || name.indexOf(kw) >= 0) ? '' : 'none';
        });
    }

    function showAddIndicatorDialog() {
        var html = '<div style="max-height:300px;overflow-y:auto;">';
        html += '<input type="text" id="compare-ind-search" placeholder="搜索..." oninput="TechInd._filterIndDialog(this.value)" style="width:100%;background:#000;border:1px solid var(--border-color);color:#fff;padding:4px 8px;border-radius:3px;font-size:11px;margin-bottom:6px;">';
        html += '<div id="compare-ind-container">';
        registry.forEach(function(ind) {
            var selected = compareIndicators.indexOf(ind.name) >= 0;
            html += '<div class="compare-ind-item" data-name="' + (ind.label || ind.name) + '" data-indname="' + ind.name + '" onclick="TechInd._pickIndicator(\'' + ind.name + '\')" style="padding:4px 6px;cursor:pointer;border-bottom:1px solid rgba(255,255,255,0.04);font-size:11px;' + (selected ? 'opacity:0.4;' : '') + '">';
            html += escHtml(ind.label || ind.name) + ' <span style="color:var(--text-micro);font-size:9px;">(' + ind.name + ')</span>';
            if (selected) html += ' <span style="color:var(--accent-green);font-size:9px;">✓</span>';
            html += '</div>';
        });
        html += '</div></div>';
        Modal.alert('选择指标（点击添加/移除）', html);
    }

    function _pickIndicator(name) {
        if (compareIndicators.indexOf(name) >= 0) {
            removeIndicator(name);
        } else {
            if (compareIndicators.length >= 10) { Modal.alert('提示', '最多比较 10 个指标'); return; }
            compareIndicators.push(name);
            _saveCompareState();
        }
        _updateCompareUI();
        showAddIndicatorDialog();
    }

    function _filterIndDialog(keyword) {
        var kw = keyword.toLowerCase();
        var items = document.querySelectorAll('.compare-ind-item');
        items.forEach(function(el) {
            var name = (el.dataset.name || '').toLowerCase();
            var indName = (el.dataset.indname || '').toLowerCase();
            el.style.display = (name.indexOf(kw) >= 0 || indName.indexOf(kw) >= 0) ? '' : 'none';
        });
    }

    async function runComparison() {
        if (!compareStocks.length || !compareIndicators.length) {
            Modal.alert('提示', '请先添加股票和指标');
            return;
        }

        var resultEl = document.getElementById('ti-compare-result');
        resultEl.innerHTML = '<div style="color:var(--text-micro);padding:10px;text-align:center;"><i class="fas fa-spinner fa-spin"></i> 加载比较数据...</div>';

        try {
            var res = await fetch(API + '/quant/indicators/compare', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ stocks: compareStocks, indicators: compareIndicators })
            });
            var d = await res.json();
            var data = d.data || {};
            var stocks = data.stocks || [];
            var rows = data.rows || [];

            if (!rows.length) {
                resultEl.innerHTML = '<div style="color:var(--text-micro);padding:20px;">无比较数据（请先计算指标）</div>';
                return;
            }

            var html = '<div class="fin-table-wrap" style="max-height:500px;"><table class="health-table" style="font-size:11px;"><thead><tr>';
            html += '<th style="position:sticky;left:0;background:#0a0a0a;z-index:2;">指标</th>';
            stocks.forEach(function(s) {
                html += '<th style="text-align:right;white-space:nowrap;">' + escHtml(s.code) + '<br><span style="font-size:9px;color:var(--text-micro);font-weight:normal;">' + escHtml(s.name) + '</span></th>';
            });
            html += '</tr></thead><tbody>';

            rows.forEach(function(row) {
                html += '<tr>';
                html += '<td style="position:sticky;left:0;background:#0a0a0a;z-index:1;white-space:nowrap;font-weight:600;">' + escHtml(row.label || row.indicator) + '</td>';
                stocks.forEach(function(s) {
                    var v = row.values ? row.values[s.code] : undefined;
                    var color = _valueColor(row.indicator, v);
                    var valStr = (v != null && v !== '') ? _fmtValue(v, row.indicator) : '—';
                    html += '<td style="text-align:right;font-family:var(--font-mono);color:' + color + ';">' + valStr + '</td>';
                });
                html += '</tr>';
            });

            html += '</tbody></table></div>';

            html += '<div style="margin-top:8px;text-align:center;font-size:10px;color:var(--text-micro);">';
            html += '<button onclick="TechInd._exportCompareCSV()" style="background:transparent;border:1px solid var(--text-dim);color:var(--text-dim);padding:4px 12px;border-radius:3px;cursor:pointer;font-size:10px;"><i class="fas fa-download"></i> 导出CSV</button>';
            html += '</div>';

            resultEl.innerHTML = html;
        } catch(e) {
            resultEl.innerHTML = '<div style="color:var(--accent-red);padding:20px;">比较失败: ' + escHtml(e.message) + '</div>';
        }
    }

    function _exportCompareCSV() {
        var table = document.querySelector('#ti-compare-result table');
        if (!table) return;
        var rows = table.querySelectorAll('tr');
        var csv = [];
        rows.forEach(function(tr) {
            var cells = tr.querySelectorAll('th, td');
            var row = [];
            cells.forEach(function(td) {
                var text = td.textContent.trim().replace(/,/g, ' ');
                row.push('"' + text + '"');
            });
            csv.push(row.join(','));
        });
        _downloadCSV(csv.join('\n'), 'tech_compare_' + _toDateStr() + '.csv');
    }

    // ══════════════════════════════════════════════════════════════
    // Public API
    // ══════════════════════════════════════════════════════════════
    return {
        init: init,
        switchMode: switchMode,
        selectStock: selectStock,
        selectField: selectField,
        _toggleOverlay: _toggleOverlay,
        _selectSubChart: _selectSubChart,
        _setTimeRange: _setTimeRange,
        _showChipDist: _showChipDist,
        _onSortClick: _onSortClick,
        _applyFilter: _applyFilter,
        _resetFilter: _resetFilter,
        _exportFieldCSV: _exportFieldCSV,
        _viewStockFromField: _viewStockFromField,
        _updateCompareUI: _updateCompareUI,
        showAddStockDialog: showAddStockDialog,
        showAddIndicatorDialog: showAddIndicatorDialog,
        addStock: addStock,
        removeStock: removeStock,
        addIndicator: addIndicator,
        removeIndicator: removeIndicator,
        runComparison: runComparison,
        _exportCompareCSV: _exportCompareCSV,
        _pickStock: _pickStock,
        _pickIndicator: _pickIndicator,
        _filterStockDialog: _filterStockDialog,
        _filterIndDialog: _filterIndDialog,
    };
})();
