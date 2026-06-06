/**
 * 技术指标前端模块 (TechInd) — V3
 *
 * 功能:
 *   - 按股票: 自动分组显示(价格&均线/MACD/RSI/KDJ/布林带/…), 每组独立渲染
 *   - 按指标: 可排序排名表 + 阈值筛选 + 统计摘要 + CSV导出
 *   - 交叉比较: 多股票×多指标矩阵 + CSV导出 + localStorage持久化
 */
window.TechInd = (function() {
    'use strict';

    var API = window.API_BASE || '/api';

    // ── 常量 ──
    var CAT_NAMES = {
        trend: '趋势', momentum: '动量', volatility: '波动',
        volume: '量能', crowding: '拥挤度', chip: '筹码'
    };
    var CAT_ORDER = ['trend', 'momentum', 'volatility', 'volume', 'crowding', 'chip'];

    var SERIES_COLORS = ['#60a5fa', '#2ed573', '#ff4757', '#ffa502', '#a29bfe', '#fb6da7', '#00d2d3', '#f368e0'];

    // ── 指标分组定义 (★ V3: 按逻辑分组, 不同渲染方式) ──
    var FIELD_GROUPS = {
        price_ma:     { label: '价格与均线', fields: ['price','ma5','ma10','ma20','ma60','ma120','ma250'], style: 'multi_line' },
        bollinger:    { label: '布林带',     fields: ['bb_upper','bb_mid','bb_lower'],                    style: 'band' },
        vwap:         { label: 'VWAP',       fields: ['vwap'],                                           style: 'overlay', overlay: 'price_ma' },
        macd:         { label: 'MACD',       fields: ['macd','macd_signal','macd_hist'],                  style: 'macd' },
        kdj:          { label: 'KDJ',        fields: ['k','d','j'],                                      style: 'ranged', min: 0, max: 100 },
        rsi:          { label: 'RSI',        fields: ['rsi'],                                            style: 'rsi' },
        atr:          { label: 'ATR',        fields: ['atr'],                                            style: 'line' },
        cci:          { label: 'CCI',        fields: ['cci'],                                            style: 'line' },
        obv:          { label: 'OBV',        fields: ['obv'],                                            style: 'line' },
        volume_ma:    { label: '均量线',     fields: ['v_ma5','v_ma10','v_ma20'],                       style: 'line' },
        bb_width:     { label: '布林带宽',   fields: ['bb_width'],                                      style: 'line' },
        crowing_rat:  { label: '拥挤度',     fields: ['crowding_ratio'],                                 style: 'line' },
        sharpe:       { label: '夏普比',     fields: ['sharpe_60d'],                                     style: 'line' },
        turnover:     { label: '换手率',     fields: ['turnover_20d','turnover_120d'],                   style: 'line' },
        chip_conc:    { label: '筹码集中度', fields: ['chip_concentration'],                             style: 'line' },
        chip_price:   { label: '筹码价格',   fields: ['chip_peak_price','chip_avg_cost'],                style: 'line' },
    };

    var FIELD_TO_GROUP = {};
    (function buildMap() {
        for (var g in FIELD_GROUPS) {
            FIELD_GROUPS[g].fields.forEach(function(f) { FIELD_TO_GROUP[f] = g; });
        }
    })();

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

    // 图表状态
    var _chartFields = [];           // 当前勾选的指标字段
    var _chartDays = 180;           // 当前时间范围（默认近6个月）

    // 排序/筛选状态 (field mode)
    var _fieldItems = [];
    var _sortCol = '';
    var _sortDir = '';
    var _filterOp = '';
    var _filterVal = '';

    var _chartInstances = [];        // 当前所有 ECharts 实例
    var _resizeHandler = null;

    // ── 工具函数 ──
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
    function isPriceField(f) {
        var priceFields = ['price','ma5','ma10','ma20','ma60','ma120','ma250',
            'bb_upper','bb_mid','bb_lower','vwap','chip_avg_cost','chip_peak_price'];
        return priceFields.indexOf(f) >= 0;
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
            (posData.data || []).forEach(function(p) { map[p.stock_code] = p.stock_name || ''; });
            (wlData.data || []).forEach(function(w) { map[w.stock_code] = w.stock_name || ''; });
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

    // ══════════════════════════════════════════════════════════
    // Mode Switching
    // ══════════════════════════════════════════════════════════
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

    // ══════════════════════════════════════════════════════════
    // Stock Mode
    // ══════════════════════════════════════════════════════════
    function selectStock() {
        var code = document.getElementById('stock-select').value;
        if (!code) return;
        currentStock = code;
        _chartFields = [];
        document.getElementById('indicator-cards').innerHTML = '<div style="color:var(--text-micro);padding:20px;">加载中...</div>';

        fetch(API + '/quant/indicators/' + code).then(function(r) { return r.json(); }).then(function(d) {
            var ind = (d.data && d.data.indicators) ? d.data.indicators : null;
            if (!ind) {
                document.getElementById('indicator-cards').innerHTML = '<div style="color:var(--text-micro);padding:20px;">无指标数据</div>';
                return;
            }
            document.getElementById('stock-info-text').textContent = '最新: ' + (d.data.analysis_date || '?') + ' | 现价: ' + (ind.price ? ind.price.toFixed(2) : '?');
            _renderCards(ind);

            // ★ V3: 默认显示价格 + MA (price, ma5, ma10, ma20, ma60)
            var defaults = ['price', 'ma5', 'ma10', 'ma20', 'ma60'];
            _chartFields = defaults.filter(function(f) { return f in ind && ind[f] != null; });
            var cbs = document.querySelectorAll('.ind-checkbox');
            cbs.forEach(function(cb) {
                cb.checked = _chartFields.indexOf(cb.dataset.field) >= 0;
            });
            if (_chartFields.length) {
                _showMultiChart();
            }
        }).catch(function(e) {
            document.getElementById('indicator-cards').innerHTML = '<div style="color:var(--accent-red);">加载失败</div>';
        });
    }

    function _renderCards(ind) {
        var grouped = {};
        registry.forEach(function(ir) {
            var cat = ir.category;
            if (!grouped[cat]) grouped[cat] = [];
            ir.output.forEach(function(field) {
                if (field in ind && ind[field] != null && !field.startsWith('_')) {
                    grouped[cat].push({ name: field, label: ir.label || field, value: ind[field] });
                }
            });
        });

        var html = '';
        // Multi-select button bar
        html += '<div style="display:flex;gap:4px;padding:4px 10px 6px;align-items:center;border-bottom:1px solid rgba(255,255,255,0.04);">';
        html += '<span style="font-size:9px;color:var(--text-micro);">勾选指标分组显示:</span>';
        html += '<button onclick="TechInd._showMultiChart()" style="margin-left:auto;background:transparent;border:1px solid var(--accent-blue);color:var(--accent-blue);padding:3px 10px;border-radius:3px;cursor:pointer;font-size:10px;">📊 显示</button>';
        html += '<button onclick="TechInd._clearChecked()" style="background:transparent;border:1px solid var(--text-micro);color:var(--text-micro);padding:3px 10px;border-radius:3px;cursor:pointer;font-size:10px;">清除</button>';
        html += '</div>';

        for (var ci = 0; ci < CAT_ORDER.length; ci++) {
            var cat = CAT_ORDER[ci];
            var items = grouped[cat];
            if (!items || !items.length) continue;
            html += '<div class="cat-group"><div class="cat-title">' + (CAT_NAMES[cat] || cat) + ' (' + items.length + ')</div>';
            items.forEach(function(f) {
                var isNum = typeof f.value === 'number';
                var vs = isNum ? _fmtValue(f.value, f.name) : String(f.value).substring(0, 20);
                var isText = textFields[f.name];
                var checked = _chartFields.indexOf(f.name) >= 0 ? ' checked' : '';

                html += '<div class="ind-row" data-field="' + f.name + '">';
                html += '<input type="checkbox" class="ind-checkbox" data-field="' + f.name + '"' + checked + ' onchange="TechInd._toggleCheckbox(this)" style="margin:0;cursor:pointer;">';
                html += '<span class="name" style="margin-left:4px;' + (isText ? 'color:#a78bfa;' : '') + '">' + f.name + '</span>';
                html += '<span class="val" style="' + (isText ? 'color:#a78bfa;' : '') + '">' + vs + '</span>';
                html += '</div>';
            });
            html += '</div>';
        }
        document.getElementById('indicator-cards').innerHTML = html || '<div style="color:var(--text-micro);padding:10px;">暂无指标数据</div>';
    }

    function _toggleCheckbox(cb) {
        var field = cb.dataset.field;
        if (cb.checked) {
            if (_chartFields.indexOf(field) < 0) _chartFields.push(field);
        } else {
            _chartFields = _chartFields.filter(function(f) { return f !== field; });
        }
    }

    function _clearChecked() {
        _chartFields = [];
        var cbs = document.querySelectorAll('.ind-checkbox');
        cbs.forEach(function(cb) { cb.checked = false; });
        _disposeAllCharts();
        document.getElementById('main-chart').innerHTML = '<div style="color:var(--text-micro);padding:40px;text-align:center;">勾选左侧指标后点击"显示"</div>';
    }

    // ═══ Chart Controls ═══
    function _setTimeRange(days) {
        _chartDays = days;
        if (currentMode === 'stock' && currentStock && _chartFields.length) {
            _showMultiChart();
        }
    }

    function _renderChartControls() {
        var html = '<div class="chart-controls" style="display:flex;gap:6px;align-items:center;padding:4px 0;">';
        html += '<span style="font-size:9px;color:var(--text-micro);">时间范围:</span>';
        var ranges = [7, 30, 90, 180, 365, 0];
        var rangeLabels = ['7d', '30d', '90d', '180d', '365d', 'Max'];
        ranges.forEach(function(d, idx) {
            var active = _chartDays === d ? 'var(--accent-gold);border-color:var(--accent-gold);' : 'var(--text-micro);border-color:var(--border-color);';
            html += '<button onclick="TechInd._setTimeRange(' + d + ')" style="background:none;border:1px solid;padding:2px 6px;border-radius:3px;cursor:pointer;font-size:9px;color:' + active + '">' + rangeLabels[idx] + '</button>';
        });
        html += '</div>';
        return html;
    }

    // ══════════════════════════════════════════════════════════
    // ★ V3: 分组多图渲染 (取代旧的单图叠加)
    // ══════════════════════════════════════════════════════════
    function _showMultiChart() {
        if (!_chartFields.length) {
            Modal.alert('提示', '请勾选至少一个指标');
            return;
        }
        // 过滤掉文本字段（如 chip_pattern/chip_signal）, 无法绘制图表
        var chartableFields = _chartFields.filter(function(f) { return !textFields[f]; });
        if (chartableFields.length !== _chartFields.length) {
            var filteredCount = _chartFields.length - chartableFields.length;
            console.log('[TechInd] filtered ' + filteredCount + ' text fields');
        }
        if (!chartableFields.length) {
            Modal.alert('提示', '所选指标均为文本类型，无法绘制图表，请勾选数值类指标');
            return;
        }
        var code = currentStock;
        if (!code) return;

        var container = document.getElementById('main-chart');
        var titleEl = document.getElementById('chart-title');
        var infoEl = document.getElementById('chart-info');

        titleEl.innerHTML = code + ' — 指标分组视图' + _renderChartControls();
        infoEl.textContent = '加载中...';
        _disposeAllCharts();

        // 分组: chartableFields → 按 field group 归类
        var groups = {};
        chartableFields.forEach(function(f) {
            var g = FIELD_TO_GROUP[f];
            if (!g) { groups[f] = { groupKey: f, label: f, fields: [f], style: 'line' }; return; }
            if (!groups[g]) {
                groups[g] = { groupKey: g, label: FIELD_GROUPS[g].label, fields: [], style: FIELD_GROUPS[g].style };
            }
            groups[g].fields.push(f);
        });

        var fields = chartableFields.join(',');
        fetch(API + '/quant/indicators/history/' + code + '?fields=' + fields + '&days=' + _chartDays)
        .then(function(r) { return r.json(); })
        .then(function(d) {
            var data = d.data;
            if (!data || !data.dates || !data.dates.length) {
                infoEl.textContent = '无历史数据';
                return;
            }
            infoEl.textContent = data.dates.length + ' 天 | ' + chartableFields.length + ' 指标 | ' + Object.keys(groups).length + ' 组';

            // 按分组排序: price_ma 优先第一张图
            var groupOrder = Object.keys(FIELD_GROUPS);
            var sortedGroups = Object.keys(groups).sort(function(a, b) {
                var ia = groupOrder.indexOf(a);
                var ib = groupOrder.indexOf(b);
                return (ia < 0 ? 999 : ia) - (ib < 0 ? 999 : ib);
            });

            // 动态渲染每个分组
            var chartsHtml = '';
            sortedGroups.forEach(function(g) {
                var grp = groups[g];
                var style = grp.style;
                var height = (style === 'macd' || style === 'multi_line') ? 240 : 180;
                chartsHtml += '<div class="chart-section" style="margin-bottom:2px;">' +
                    '<div style="font-size:10px;color:var(--text-dim);padding:3px 8px;background:rgba(255,255,255,0.02);border-radius:3px 3px 0 0;border-bottom:1px solid var(--border-thin);">' +
                    '<span style="font-weight:600;color:#ccc;">' + escHtml(grp.label) + '</span></div>' +
                    '<div id="chart-' + g.replace(/[^a-z0-9_]/g,'') + '" style="height:' + height + 'px;width:100%;"></div></div>';
            });
            container.innerHTML = chartsHtml;

            // 渲染每个分组的图
            sortedGroups.forEach(function(g) {
                var grp = groups[g];
                var el = document.getElementById('chart-' + g.replace(/[^a-z0-9_]/g,''));
                if (!el) return;
                _renderGroupChart(el, grp, data);
            });
        })
        .catch(function() { infoEl.textContent = '加载失败'; });
    }

    function _renderGroupChart(el, grp, data) {
        var dates = data.dates;
        var fields = grp.fields;
        var style = grp.style;

        switch (style) {
            case 'macd':  _renderMACD(el, dates, data, fields); break;
            case 'rsi':   _renderRSI(el, dates, data, fields); break;
            case 'ranged': _renderRanged(el, dates, data, fields, 0, 100); break;
            case 'band':  _renderBand(el, dates, data, fields); break;
            case 'multi_line': _renderMultiLine(el, dates, data, fields); break;
            default:      _renderLines(el, dates, data, fields); break;
        }
    }

    // ── 专用渲染器: MACD (柱 + 线) ──
    function _renderMACD(el, dates, data, fields) {
        var hist = data.fields['macd_hist'] || [];
        var macd = data.fields['macd'] || [];
        var signal = data.fields['macd_signal'] || [];

        var chart = echarts.init(el);
        _chartInstances.push(chart);

        var option = {
            tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
            grid: { left: '8%', right: '5%', top: '8%', bottom: '10%' },
            xAxis: { type: 'category', data: dates, axisLabel: { fontSize: 8, rotate: 30, show: true } },
            yAxis: { type: 'value', scale: true, splitLine: { lineStyle: { color: '#1a1a1a' } }, axisLabel: { fontSize: 9 } },
            series: [
                {
                    name: 'MACD Hist',
                    type: 'bar',
                    data: hist,
                    itemStyle: {
                        color: function(p) { return p.value >= 0 ? 'rgba(46,213,115,0.7)' : 'rgba(255,71,87,0.7)'; }
                    }
                },
                {
                    name: 'MACD',
                    type: 'line', data: macd,
                    smooth: true, symbol: 'none',
                    lineStyle: { color: '#60a5fa', width: 1.5 }
                },
                {
                    name: 'Signal',
                    type: 'line', data: signal,
                    smooth: true, symbol: 'none',
                    lineStyle: { color: '#ffa502', width: 1.5 }
                }
            ]
        };
        chart.setOption(option);
    }

    // ── 专用渲染器: RSI (30/70 参考线) ──
    function _renderRSI(el, dates, data, fields) {
        var values = data.fields['rsi'] || [];
        var chart = echarts.init(el);
        _chartInstances.push(chart);

        chart.setOption({
            tooltip: { trigger: 'axis' },
            grid: { left: '8%', right: '5%', top: '8%', bottom: '10%' },
            xAxis: { type: 'category', data: dates, axisLabel: { fontSize: 8, rotate: 30 } },
            yAxis: { type: 'value', min: 0, max: 100,
                splitLine: { lineStyle: { color: '#1a1a1a' } },
                axisLabel: { fontSize: 9 } },
            visualMap: { show: false },
            series: [
                {
                    name: 'RSI', type: 'line', data: values,
                    smooth: true, symbol: 'none',
                    lineStyle: { color: '#a29bfe', width: 2 },
                    markLine: {
                        silent: true,
                        data: [
                            { yAxis: 70, label: { formatter: '超买 70', color: '#ff4757', fontSize: 9 }, lineStyle: { color: '#ff4757', type: 'dashed', width: 1 } },
                            { yAxis: 30, label: { formatter: '超卖 30', color: '#2ed573', fontSize: 9 }, lineStyle: { color: '#2ed573', type: 'dashed', width: 1 } },
                            { yAxis: 50, label: { formatter: '50', color: '#666', fontSize: 8 }, lineStyle: { color: '#333', type: 'dotted', width: 1 } }
                        ]
                    }
                }
            ]
        });
    }

    // ── 专用渲染器: 0-100 范围 (KDJ) ──
    function _renderRanged(el, dates, data, fields, minV, maxV) {
        var chart = echarts.init(el);
        _chartInstances.push(chart);

        var series = fields.map(function(f, i) {
            var color = ['#60a5fa', '#2ed573', '#ffa502'][i % 3];
            return {
                name: f, type: 'line', data: data.fields[f] || [],
                smooth: true, symbol: 'none',
                lineStyle: { color: color, width: 1.5 }
            };
        });

        chart.setOption({
            tooltip: { trigger: 'axis' },
            legend: { data: fields, textStyle: { color: '#999' }, bottom: 0 },
            grid: { left: '8%', right: '5%', top: '8%', bottom: '22%' },
            xAxis: { type: 'category', data: dates, axisLabel: { fontSize: 8, rotate: 30 } },
            yAxis: {
                type: 'value', min: minV, max: maxV,
                splitLine: { lineStyle: { color: '#1a1a1a' } },
                axisLabel: { fontSize: 9 }
            },
            series: series
        });
    }

    // ── 专用渲染器: 布林带 (带带宽填充) ──
    function _renderBand(el, dates, data, fields) {
        var upper = data.fields['bb_upper'] || [];
        var mid = data.fields['bb_mid'] || [];
        var lower = data.fields['bb_lower'] || [];

        var chart = echarts.init(el);
        _chartInstances.push(chart);

        // 填充区间: upper ~ lower
        var fillData = dates.map(function(_, i) {
            return [lower[i], upper[i]];
        });

        chart.setOption({
            tooltip: { trigger: 'axis' },
            legend: { data: ['上轨', '中轨', '下轨'], textStyle: { color: '#999' }, bottom: 0 },
            grid: { left: '8%', right: '5%', top: '8%', bottom: '22%' },
            xAxis: { type: 'category', data: dates, axisLabel: { fontSize: 8, rotate: 30 } },
            yAxis: { type: 'value', scale: true, splitLine: { lineStyle: { color: '#1a1a1a' } }, axisLabel: { fontSize: 9 } },
            series: [
                {
                    name: '上轨', type: 'line', data: upper,
                    smooth: true, symbol: 'none',
                    lineStyle: { color: 'rgba(255,71,87,0.5)', width: 1 },
                    areaStyle: { color: 'rgba(255,71,87,0.03)' }
                },
                {
                    name: '中轨', type: 'line', data: mid,
                    smooth: true, symbol: 'none',
                    lineStyle: { color: '#ffa502', width: 1.5 }
                },
                {
                    name: '下轨', type: 'line', data: lower,
                    smooth: true, symbol: 'none',
                    lineStyle: { color: 'rgba(46,213,115,0.5)', width: 1 },
                    areaStyle: { color: 'rgba(46,213,115,0.03)' }
                }
            ]
        });
    }

    // ── 多线叠加 (价格+均线) ──
    function _renderMultiLine(el, dates, data, fields) {
        var chart = echarts.init(el);
        _chartInstances.push(chart);

        var fieldColors = {
            'price': '#ffffff',
            'ma5': '#60a5fa',
            'ma10': '#2ed573',
            'ma20': '#ffa502',
            'ma60': '#ff4757',
            'ma120': '#a29bfe',
            'ma250': '#00d2d3'
        };

        var series = fields.map(function(f, i) {
            var color = fieldColors[f] || SERIES_COLORS[i % SERIES_COLORS.length];
            var isPrice = f === 'price';
            return {
                name: f, type: 'line', data: data.fields[f] || [],
                smooth: true, symbol: 'none',
                lineStyle: { color: color, width: isPrice ? 2 : 1, type: isPrice ? 'solid' : 'solid' },
                emphasis: { lineStyle: { width: isPrice ? 3 : 2 } }
            };
        });

        chart.setOption({
            tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
            legend: { data: fields, textStyle: { color: '#999' }, bottom: 0, type: 'scroll' },
            grid: { left: '8%', right: '5%', top: '8%', bottom: '22%' },
            dataZoom: [
                { type: 'inside' }
            ],
            xAxis: { type: 'category', data: dates, axisLabel: { fontSize: 8, rotate: 30 } },
            yAxis: { type: 'value', scale: true, splitLine: { lineStyle: { color: '#1a1a1a' } }, axisLabel: { fontSize: 9 } },
            series: series
        });
    }

    // ── 普通线图 (通用) ──
    function _renderLines(el, dates, data, fields) {
        var chart = echarts.init(el);
        _chartInstances.push(chart);

        var series = fields.map(function(f, i) {
            var color = SERIES_COLORS[i % SERIES_COLORS.length];
            return {
                name: f, type: 'line', data: data.fields[f] || [],
                smooth: true, symbol: 'none',
                lineStyle: { color: color, width: 1.5 }
            };
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

    function _disposeAllCharts() {
        _chartInstances.forEach(function(c) { if (c) c.dispose(); });
        _chartInstances = [];
    }

    // ══════════════════════════════════════════════════════════
    // Chip Distribution Chart (独立, 不从属分组)
    // ══════════════════════════════════════════════════════════
    function showChipChart(code) {
        document.getElementById('chart-title').textContent = code + ' — 筹码分布';
        document.getElementById('chart-info').textContent = '加载中...';
        _disposeAllCharts();

        fetch(API + '/quant/indicators/chip-dist/' + code).then(function(r) { return r.json(); }).then(function(d) {
            var data = d.data;
            if (!data) { document.getElementById('chart-info').textContent = '无数据'; return; }
            document.getElementById('chart-info').textContent = '获利' + data.winner_close + '% | 均成本' + data.avg_cost + ' | 集中度' + data.concentration_90 + '%';
            var chart = echarts.init(document.getElementById('main-chart'));
            _chartInstances.push(chart);
            chart.setOption({
                tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
                grid: { left: '12%', right: '5%', top: '5%', bottom: '5%' },
                xAxis: { type: 'value', splitLine: { lineStyle: { color: '#1a1a1a' } } },
                yAxis: { type: 'category', data: data.prices, axisLabel: { fontSize: 9 } },
                series: [{
                    type: 'bar', data: data.chip_pct, barWidth: '90%',
                    itemStyle: {
                        color: function(p) { return parseFloat(data.prices[p.dataIndex]) < data.avg_cost ? '#14b143' : '#ef232a'; }
                    }
                }]
            });
        });
    }

    // ══════════════════════════════════════════════════════════
    // Field Mode (Enhanced: sortable table + filter + stats + CSV)
    // ══════════════════════════════════════════════════════════
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

    // ═══ Field Bar Chart ═══
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
                itemStyle: {
                    color: function(p) {
                        return new echarts.graphic.LinearGradient(0, 0, 1, 0, [
                            { offset: 0, color: '#60a5fa' },
                            { offset: 1, color: '#a78bfa' }
                        ]);
                    }
                }
            }]
        });
    }

    // ══════════════════════════════════════════════════════════
    // Cross Comparison (Tab 3)
    // ══════════════════════════════════════════════════════════
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

    // ═══ Utilities ═══
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

    // ══════════════════════════════════════════════════════════
    // Public API
    // ══════════════════════════════════════════════════════════
    return {
        init: init,
        switchMode: switchMode,
        selectStock: selectStock,
        selectField: selectField,
        showChipChart: showChipChart,
        _showMultiChart: _showMultiChart,
        _setTimeRange: _setTimeRange,
        _toggleCheckbox: _toggleCheckbox,
        _clearChecked: _clearChecked,
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
