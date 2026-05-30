/**
 * 财务指标前端模块 (FinInd)
 * 三个核心功能:
 *   R1 - 算子详情: description + judgment + 跨个股按钮
 *   R2 - 跨个股时间序列表: 各股票 × 12Q
 *   R3 - 按股票全指标矩阵: 多张分类子表
 */
window.FinInd = (function() {
    'use strict';
    const API = window.API_BASE || '/api';

    // ── Cache ──
    var stockList = [];         // [{stock_code, stock_name}, ...]
    var stockNameMap = {};      // code → name
    var registry = [];          // registry items (from API)
    var fieldLabelMap = {};     // field_name → label

    // ── 字段分类 (R3 按股票全指标分组) ──
    var FIELD_CATEGORIES = {
        '核心价值': ['roic_pct', 'roic_pct_adjusted', 'roic_stability'],
        '成长扩张': ['roiic_pct', 'roiic_pct_adjusted', 'operating_leverage', 'revenue_yoy', 'revenue_acceleration', 'revenue_qoq'],
        '盈利质量': ['gross_margin', 'gross_margin_trend', 'operating_margin_stability', 'fcf_conversion'],
        '资产效率': ['working_capital_efficiency', 'inventory_revenue_ratio', 'inventory_yoy'],
        '早期信号': ['burn_rate_months', 'contract_liability_yoy', 'profit_turnaround'],
        '研发投入': ['rd_intensity', 'rd_growth', 'rd_to_revenue_trend', 'rd_to_opex']
    };

    // ── 工具函数 ──
    // 每个字段的显示小数位 (0=整数, 1=百分数/个位, 2=比率, 3=变异系数)
    var FIELD_DECIMALS = {
        'roic_pct': 1, 'roic_pct_adjusted': 1,
        'roiic_pct': 1, 'roiic_pct_adjusted': 1,
        'gross_margin': 1, 'rd_intensity': 1, 'rd_to_opex': 1,
        'revenue_yoy': 1, 'revenue_acceleration': 1, 'revenue_qoq': 1,
        'rd_growth': 1, 'contract_liability_yoy': 1, 'inventory_yoy': 1,
        'working_capital_efficiency': 1, 'rd_to_revenue_trend': 1,
        'burn_rate_months': 1, 'operating_margin_stability': 1,
        'operating_leverage': 2, 'fcf_conversion': 2,
        'roic_stability': 3,
        'profit_turnaround': 0,
    };

    function escHtml(s) {
        if (!s) return '';
        return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    }

    function _isETF(code) {
        return /^(159|510|512|513|560|588)/.test(code);
    }

    // 按字段类型格式化数值: 百分数1位, 比率2位, 变异系数3位, 整数0位
    function _fmtField(v, field) {
        if (v == null || v === '' || v === undefined) return null;
        if (typeof v === 'string') {
            var short = {
                'rising': '↑上升', 'declining': '↓下降', 'stable': '→稳定',
                'rising_alert': '↑预警', 'declining_bullish': '↓看涨'
            };
            return short[v] || v;
        }
        var n = Number(v);
        if (isNaN(n)) return String(v);
        var dec = FIELD_DECIMALS[field];
        if (dec === 0) return n.toFixed(0);
        if (dec !== undefined) return n.toFixed(dec);
        // 未知字段: 智能推断
        var abs = Math.abs(n);
        if (abs >= 100) return n.toFixed(0);
        if (abs >= 1) return n.toFixed(1);
        return n.toFixed(2);
    }

    // 越低越好的字段 (positive=red, negative=green)
    var LOWER_BETTER = ['working_capital_efficiency', 'inventory_yoy', 'roic_stability', 'operating_margin_stability'];

    function _valueColor(field, v) {
        if (v == null || v === '') return 'var(--text-micro)';

        if (typeof v === 'string') {
            if (v === 'rising' || v === 'declining_bullish') return 'var(--accent-green)';
            if (v === 'declining' || v === 'rising_alert') return 'var(--accent-red)';
            if (v === 'stable') return 'var(--text-dim)';
            return 'var(--text-dim)';
        }

        var n = Number(v);
        if (isNaN(n)) return 'var(--text-dim)';

        // profit_turnaround: 1=good, -1=bad, 0=neutral
        if (field === 'profit_turnaround') {
            if (n === 1) return 'var(--accent-green)';
            if (n === -1) return 'var(--accent-red)';
            return 'var(--text-dim)';
        }

        var invert = LOWER_BETTER.indexOf(field) >= 0;
        if (n > 0) return invert ? 'var(--accent-red)' : 'var(--accent-green)';
        if (n < 0) return invert ? 'var(--accent-green)' : 'var(--accent-red)';
        return 'var(--text-dim)';
    }

    function getFieldLabel(fieldName) {
        if (fieldLabelMap[fieldName]) return fieldLabelMap[fieldName];
        // Search registry for the indicator owning this output field
        for (var i = 0; i < registry.length; i++) {
            var ind = registry[i];
            if (ind.name === fieldName) return ind.label || fieldName;
            if ((ind.output || []).indexOf(fieldName) >= 0) return ind.label || fieldName;
        }
        return fieldName;
    }

    // ── 初始化数据 (stockList + registry 缓存) ──
    async function initData() {
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
        } catch(e) { console.error('[FinInd] stock list error:', e); }

        try {
            var res = await fetch(API + '/quant/financial-indicators/registry');
            var d = await res.json();
            registry = d.data || [];
            fieldLabelMap = {};
            registry.forEach(function(ind) {
                (ind.output || []).forEach(function(f) { fieldLabelMap[f] = ind.label; });
                if (ind.name) fieldLabelMap[ind.name] = ind.label;
            });
        } catch(e) { console.error('[FinInd] registry error:', e); }
    }

    // ════════════════════════════════════════════════
    // R1: 算子详情 — 指标说明 + 数据判断方法
    // ════════════════════════════════════════════════
    async function showIndicatorDetail(name) {
        var panelEmpty = document.getElementById('panel-empty');
        var panelDetail = document.getElementById('panel-detail');
        var detailTitle = document.getElementById('detail-title');
        var detailContent = document.getElementById('detail-content');

        panelEmpty.style.display = 'none';
        panelDetail.style.display = '';
        detailTitle.textContent = '财务算子: ' + name;
        detailContent.innerHTML = '<div style="color:var(--text-micro);padding:10px;text-align:center;"><i class="fas fa-spinner fa-spin"></i> 加载中...</div>';

        try {
            var res = await fetch(API + '/quant/financial-indicators/registry');
            var d = await res.json();
            var ind = (d.data || []).find(function(i) { return i.name === name; });
            if (!ind) {
                detailContent.innerHTML = '<div style="color:var(--text-dim);padding:20px;text-align:center;">指标未找到</div>';
                return;
            }

            var stages = (ind.applicable_stages || []).join(', ');
            var typeBadge = { moat: '护城河', prosperity: '高景气', both: '通用' };
            var typeClass = { moat: 'badge-trend', prosperity: 'badge-momentum', both: 'badge-crowding' };
            var typeLabel = typeBadge[ind.indicator_type] || ind.indicator_type || '';
            var primaryField = (ind.output || [])[0] || name;
            var desc = ind.description || '暂无说明';
            var judge = ind.judgment || '暂无判断标准';

            detailContent.innerHTML =
                '<div class="card">' +
                    '<div style="display:flex;justify-content:space-between;align-items:center;">' +
                        '<span class="card-title">' + escHtml(ind.label) + ' <span style="font-size:10px;color:var(--text-micro);">(' + escHtml(ind.name) + ')</span></span>' +
                        '<span class="badge ' + (typeClass[ind.indicator_type] || 'badge-trend') + '">' + typeLabel + '</span>' +
                    '</div>' +
                    '<div class="card-meta" style="margin-top:4px;">' +
                        '适用阶段: ' + stages +
                        ' | 依赖: ' + ((ind.requires || []).join(', ') || '无') +
                        ' | 输出: ' + ((ind.output || []).join(', ') || '无') +
                    '</div>' +
                '</div>' +
                '<div class="card" style="margin-top:8px;">' +
                    '<div style="display:flex;align-items:center;gap:4px;margin-bottom:6px;">' +
                        '<i class="fas fa-book-open" style="color:var(--accent-blue);font-size:11px;"></i>' +
                        '<span style="font-size:12px;color:#fff;font-weight:600;">指标说明</span>' +
                    '</div>' +
                    '<div style="font-size:11px;color:var(--text-dim);line-height:1.7;">' + escHtml(desc) + '</div>' +
                '</div>' +
                '<div class="card" style="margin-top:8px;">' +
                    '<div style="display:flex;align-items:center;gap:4px;margin-bottom:6px;">' +
                        '<i class="fas fa-chart-bar" style="color:var(--accent-gold);font-size:11px;"></i>' +
                        '<span style="font-size:12px;color:#fff;font-weight:600;">数据判断方法</span>' +
                    '</div>' +
                    '<div style="font-size:11px;color:var(--text-dim);line-height:1.7;">' + escHtml(judge) + '</div>' +
                '</div>' +
                '<div style="margin-top:10px;text-align:center;">' +
                    '<button onclick="FinInd.showCrossStockTable(\'' + primaryField + '\')" ' +
                        'style="background:transparent;border:1px solid var(--accent-blue);color:var(--accent-blue);padding:6px 16px;border-radius:4px;cursor:pointer;font-size:11px;">' +
                        '<i class="fas fa-table"></i> 查看跨个股时间序列 (' + escHtml(ind.label) + ')' +
                    '</button>' +
                '</div>' +
                '<div id="cross-stock-table-container" style="margin-top:10px;"></div>';

            document.getElementById('right-panel').scrollIntoView({behavior:'smooth'});
        } catch(e) {
            detailContent.innerHTML = '<div style="color:var(--accent-red);padding:20px;text-align:center;">加载失败: ' + escHtml(e.message) + '</div>';
        }
    }

    // ════════════════════════════════════════════════
    // R2: 跨个股时间序列表
    // ════════════════════════════════════════════════
    async function showCrossStockTable(fieldName) {
        var container = document.getElementById('cross-stock-table-container');
        if (!container) return;

        container.innerHTML = '<div style="color:var(--text-micro);padding:10px;text-align:center;"><i class="fas fa-spinner fa-spin"></i> 加载跨个股数据...</div>';

        if (!stockList.length) await initData();

        var ind = registry.find(function(i) { return i.name === fieldName || (i.output || []).indexOf(fieldName) >= 0; });
        var label = ind ? (ind.label || fieldName) : fieldName;

        var stocks = stockList.filter(function(s) { return !_isETF(s.stock_code); });
        if (!stocks.length) {
            container.innerHTML = '<div style="color:var(--text-micro);padding:20px;text-align:center;">无持仓或自选股</div>';
            return;
        }

        try {
            // Fetch all stocks in parallel (limited concurrency)
            var allResults = [];
            for (var i = 0; i < stocks.length; i += 15) {
                var batch = stocks.slice(i, i + 15);
                var batchResults = await Promise.all(batch.map(function(s) {
                    return fetch(API + '/quant/financial-indicators/history/' + s.stock_code + '?fields=' + fieldName)
                        .then(function(r) { return r.json(); })
                        .then(function(d) { return { stock: s, data: d.data || [] }; })
                        .catch(function() { return { stock: s, data: [] }; });
                }));
                allResults = allResults.concat(batchResults);
            }

            // Union of all report dates → sorted desc → top 12
            var dateSet = {};
            allResults.forEach(function(r) {
                r.data.forEach(function(row) {
                    if (row.report_date) dateSet[row.report_date] = true;
                });
            });
            var dates = Object.keys(dateSet).sort().reverse().slice(0, 12);

            if (!dates.length) {
                container.innerHTML = '<div style="color:var(--text-micro);padding:20px;text-align:center;">请先计算指标' +
                    ' <button onclick="FinInd.triggerCompute()" style="color:var(--accent-blue);background:none;border:1px solid var(--accent-blue);border-radius:3px;padding:2px 8px;cursor:pointer;font-size:10px;">去计算</button></div>';
                return;
            }

            // Build data map: stock_code → { report_date: value }
            var dataMap = {};
            allResults.forEach(function(r) {
                dataMap[r.stock.stock_code] = {};
                r.data.forEach(function(row) {
                    dataMap[r.stock.stock_code][row.report_date] = row[fieldName];
                });
            });

            var html = '<div style="font-size:10px;color:var(--text-micro);margin-bottom:6px;">' + escHtml(label) + ' — 跨个股时间序列 (' + dates.length + 'Q, 最新在前)</div>';
            html += '<div class="fin-table-wrap"><table class="health-table"><thead><tr>';
            html += '<th style="position:sticky;left:0;background:#111;z-index:2;">股票</th>';
            html += dates.map(function(d) { return '<th style="text-align:right;font-size:9px;">' + d.substring(0,7) + '</th>'; }).join('');
            html += '</tr></thead><tbody>';

            stocks.forEach(function(s) {
                html += '<tr>';
                var nm = stockNameMap[s.stock_code] || '';
                html += '<td style="position:sticky;left:0;background:#111;z-index:1;color:var(--accent-blue);white-space:nowrap;">' + escHtml(s.stock_code) + ' ' + escHtml(nm) + '</td>';
                dates.forEach(function(d) {
                    var v = dataMap[s.stock_code] ? dataMap[s.stock_code][d] : undefined;
                    var color = _valueColor(fieldName, v);
                    var valStr = (v != null && v !== '') ? _fmtField(v, fieldName) : '—';
                    html += '<td style="text-align:right;font-family:var(--font-mono);color:' + color + ';">' + valStr + '</td>';
                });
                html += '</tr>';
            });

            html += '</tbody></table></div>';
            container.innerHTML = html;
        } catch(e) {
            container.innerHTML = '<div style="color:var(--accent-red);padding:10px;">加载失败: ' + escHtml(e.message) + '</div>';
        }
    }

    // ════════════════════════════════════════════════
    // R3: 按股票全指标矩阵 (多张分类子表)
    // ════════════════════════════════════════════════
    async function loadStockFullView(code) {
        var el = document.getElementById('fin-data-content');
        var info = document.getElementById('fin-view-info');

        if (!code) {
            el.innerHTML = '<div style="color:var(--text-micro);padding:20px;text-align:center;">请选择股票</div>';
            if (info) info.textContent = '';
            return;
        }

        el.innerHTML = '<div style="color:var(--text-micro);padding:10px;text-align:center;"><i class="fas fa-spinner fa-spin"></i> 加载中...</div>';
        if (info) info.textContent = '加载中...';

        try {
            var res = await fetch(API + '/quant/financial-indicators/history/' + code);
            var d = await res.json();
            var rows = d.data || [];

            if (!rows.length) {
                el.innerHTML = '<div style="color:var(--text-micro);padding:20px;text-align:center;">无财务指标数据 (请先计算)<br><br>' +
                    '<button onclick="FinInd.triggerCompute()" style="background:transparent;border:1px solid var(--accent-green);color:var(--accent-green);padding:6px 16px;border-radius:4px;cursor:pointer;font-size:11px;">' +
                    '<i class="fas fa-calculator"></i> 计算指标</button></div>';
                if (info) info.textContent = '';
                return;
            }

            var latestRows = rows.slice(0, 12);
            if (info) info.textContent = latestRows.length + ' 期数据 (新→旧)';

            // Build label cache if needed
            if (!Object.keys(fieldLabelMap).length) {
                registry.forEach(function(ind) {
                    (ind.output || []).forEach(function(f) { fieldLabelMap[f] = ind.label; });
                    if (ind.name) fieldLabelMap[ind.name] = ind.label;
                });
            }

            var fullHtml = '';

            Object.keys(FIELD_CATEGORIES).forEach(function(catName) {
                var fields = FIELD_CATEGORIES[catName];
                var availableFields = fields.filter(function(f) {
                    return latestRows.some(function(r) { return r[f] !== undefined && r[f] !== null; });
                });
                if (!availableFields.length) return;

                fullHtml += '<div class="fin-cat-title">' + catName + '</div>';
                fullHtml += '<div class="fin-table-wrap" style="margin-bottom:8px;">';
                fullHtml += '<table class="health-table" style="font-size:10px;"><thead><tr>';
                fullHtml += '<th style="position:sticky;left:0;background:#111;z-index:1;">报告期</th>';
                availableFields.forEach(function(f) {
                    var lbl = getFieldLabel(f) || f;
                    fullHtml += '<th style="text-align:right;font-size:9px;">' + escHtml(lbl) + '</th>';
                });
                fullHtml += '</tr></thead><tbody>';

                latestRows.forEach(function(row) {
                    fullHtml += '<tr>';
                    fullHtml += '<td style="position:sticky;left:0;background:#111;z-index:1;white-space:nowrap;">' + (row.report_date || '?') + '</td>';
                    availableFields.forEach(function(f) {
                        var v = row[f];
                        var color = _valueColor(f, v);
                        var valStr = (v != null && v !== '') ? _fmtField(v, f) : '—';
                        fullHtml += '<td style="text-align:right;font-family:var(--font-mono);color:' + color + ';">' + valStr + '</td>';
                    });
                    fullHtml += '</tr>';
                });

                fullHtml += '</tbody></table></div>';
            });

            if (!fullHtml) {
                el.innerHTML = '<div style="color:var(--text-micro);padding:20px;text-align:center;">所有字段均为空</div>';
                return;
            }

            el.innerHTML = fullHtml;
        } catch(e) {
            el.innerHTML = '<div style="color:var(--accent-red);padding:20px;">加载失败: ' + escHtml(e.message) + '</div>';
            if (info) info.textContent = '错误';
        }
    }

    // ── 按指标排名 (原有功能增强 — 加颜色) ──
    function loadFieldRanking(field) {
        var el = document.getElementById('fin-data-content');
        var info = document.getElementById('fin-view-info');

        if (!field) {
            el.innerHTML = '<div style="color:var(--text-micro);padding:20px;text-align:center;">请选择指标</div>';
            if (info) info.textContent = '';
            return;
        }

        el.innerHTML = '<div style="color:var(--text-micro);padding:10px;text-align:center;"><i class="fas fa-spinner fa-spin"></i> 加载中...</div>';

        fetch(API + '/quant/financial-indicators/field/' + field)
            .then(function(r) { return r.json(); })
            .then(function(d) {
                var items = d.data || [];
                if (!items.length) {
                    el.innerHTML = '<div style="color:var(--text-micro);padding:20px;text-align:center;">无数据</div>';
                    if (info) info.textContent = '';
                    return;
                }
                if (info) info.textContent = items.length + ' 只股票 | 点击行查看全指标';
                var label = getFieldLabel(field) || field;

                el.innerHTML = '<div class="fin-table-wrap"><table class="health-table"><thead><tr>' +
                    '<th>代码</th><th>名称</th><th style="text-align:right;">' + escHtml(label) + '</th><th>报告期</th></tr></thead><tbody>' +
                    items.map(function(i) {
                        var v = i[field];
                        var color = _valueColor(field, v);
                        var valStr = (v != null && v !== '') ? _fmtField(v, field) : '—';
                        var nm = stockNameMap[i.stock_code] || '';
                        return '<tr onclick="FinInd.loadStockFullView(\'' + i.stock_code + '\')" style="cursor:pointer;" title="点击查看全指标">' +
                            '<td style="color:var(--accent-blue);">' + i.stock_code + '</td>' +
                            '<td>' + escHtml(nm) + '</td>' +
                            '<td style="text-align:right;font-family:var(--font-mono);color:' + color + ';">' + valStr + '</td>' +
                            '<td>' + (i.report_date || '') + '</td></tr>';
                    }).join('') + '</tbody></table></div>';
            })
            .catch(function(e) {
                el.innerHTML = '<div style="color:var(--accent-red);padding:20px;">加载失败: ' + escHtml(e.message) + '</div>';
            });
    }

    // ── 数据查看 Tab 切换 (by_stock / by_field) ──
    function switchView() {
        var mode = document.getElementById('fin-view-mode').value;
        document.getElementById('fin-stock-select').style.display = mode === 'by_stock' ? '' : 'none';
        document.getElementById('fin-field-select').style.display = mode === 'by_field' ? '' : 'none';
        var el = document.getElementById('fin-data-content');
        var info = document.getElementById('fin-view-info');
        if (el) el.innerHTML = '';
        if (info) info.textContent = '';
        if (mode === 'by_stock') {
            var code = document.getElementById('fin-stock-select').value;
            if (code) loadStockFullView(code);
        } else {
            var field = document.getElementById('fin-field-select').value;
            if (field) loadFieldRanking(field);
        }
    }

    // ── 触发计算 (切换到财务Tab并聚焦计算按钮) ──
    function triggerCompute() {
        var btn = document.getElementById('fin-btn-submit');
        if (btn) {
            btn.scrollIntoView({behavior: 'smooth'});
            // Trigger click if no selected codes
            FinCompute._onSubmit();
        }
    }

    // ── 在右侧详情面板显示全指标 (R3 在ranking点击后) ──
    async function loadStockFullViewInPanel(code) {
        var panelEmpty = document.getElementById('panel-empty');
        var panelDetail = document.getElementById('panel-detail');
        var detailTitle = document.getElementById('detail-title');
        var detailContent = document.getElementById('detail-content');

        panelEmpty.style.display = 'none';
        panelDetail.style.display = '';
        detailTitle.textContent = '财务指标: ' + code;
        detailContent.innerHTML = '<div style="color:var(--text-micro);padding:10px;text-align:center;"><i class="fas fa-spinner fa-spin"></i> 加载中...</div>';

        try {
            var res = await fetch(API + '/quant/financial-indicators/history/' + code);
            var d = await res.json();
            var rows = d.data || [];

            if (!rows.length) {
                detailContent.innerHTML = '<div style="color:var(--text-micro);padding:20px;text-align:center;">无财务指标数据 (请先计算)</div>';
                return;
            }

            var latestRows = rows.slice(0, 12);

            // Build label cache if needed
            if (!Object.keys(fieldLabelMap).length) {
                registry.forEach(function(ind) {
                    (ind.output || []).forEach(function(f) { fieldLabelMap[f] = ind.label; });
                    if (ind.name) fieldLabelMap[ind.name] = ind.label;
                });
            }

            var fullHtml = '';

            Object.keys(FIELD_CATEGORIES).forEach(function(catName) {
                var fields = FIELD_CATEGORIES[catName];
                var availableFields = fields.filter(function(f) {
                    return latestRows.some(function(r) { return r[f] !== undefined && r[f] !== null; });
                });
                if (!availableFields.length) return;

                fullHtml += '<div class="fin-cat-title">' + catName + '</div>';
                fullHtml += '<div class="fin-table-wrap" style="margin-bottom:8px;">';
                fullHtml += '<table class="health-table" style="font-size:10px;"><thead><tr>';
                fullHtml += '<th style="position:sticky;left:0;background:#0a0a0a;z-index:1;">报告期</th>';
                availableFields.forEach(function(f) {
                    var lbl = getFieldLabel(f) || f;
                    fullHtml += '<th style="text-align:right;font-size:9px;">' + escHtml(lbl) + '</th>';
                });
                fullHtml += '</tr></thead><tbody>';

                latestRows.forEach(function(row) {
                    fullHtml += '<tr>';
                    fullHtml += '<td style="position:sticky;left:0;background:#0a0a0a;z-index:1;white-space:nowrap;">' + (row.report_date || '?') + '</td>';
                    availableFields.forEach(function(f) {
                        var v = row[f];
                        var color = _valueColor(f, v);
                        var valStr = (v != null && v !== '') ? _fmtField(v, f) : '—';
                        fullHtml += '<td style="text-align:right;font-family:var(--font-mono);color:' + color + ';">' + valStr + '</td>';
                    });
                    fullHtml += '</tr>';
                });

                fullHtml += '</tbody></table></div>';
            });

            if (!fullHtml) {
                detailContent.innerHTML = '<div style="color:var(--text-micro);padding:20px;text-align:center;">所有字段均为空</div>';
                return;
            }

            detailContent.innerHTML = fullHtml;
        } catch(e) {
            detailContent.innerHTML = '<div style="color:var(--accent-red);padding:20px;">加载失败: ' + escHtml(e.message) + '</div>';
        }
    }

    // ── 暴露公共 API ──
    return {
        initData: initData,
        showIndicatorDetail: showIndicatorDetail,
        showCrossStockTable: showCrossStockTable,
        loadStockFullView: loadStockFullView,
        loadStockFullViewInPanel: loadStockFullViewInPanel,
        loadFieldRanking: loadFieldRanking,
        switchView: switchView,
        triggerCompute: triggerCompute
    };
})();
