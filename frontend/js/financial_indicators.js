/**
 * 财务指标前端模块 (FinInd) — V2
 *
 * Phase 1-3 重构:
 *   - 动态分类分组 (废弃硬编码 FIELD_CATEGORIES)
 *   - 指标详情展示全部 output 字段
 *   - 跨个股时间序列支持字段切换
 *   - 三子标签布局: 指标目录 / 股票查询 / 交叉比较
 *   - 交叉比较矩阵 + localStorage 持久化
 */
window.FinInd = (function() {
    'use strict';

    var API = window.API_BASE || '/api';

    // ── 状态 ──
    var stockList = [];           // [{stock_code, stock_name}, ...]
    var stockNameMap = {};        // code → name
    var registry = [];            // registry items (from API)
    var fieldLabelMap = {};       // field_name → label
    var registryMap = {};         // name → meta
    var currentSubTab = 'directory';

    // 最近查看 (localStorage)
    var recentStocks = JSON.parse(localStorage.getItem('fin_recent') || '[]');

    // 交叉比较
    var compareStocks = JSON.parse(localStorage.getItem('fin_compare_stocks') || '[]');
    var compareIndicators = JSON.parse(localStorage.getItem('fin_compare_inds') || '[]');
    var allStocksForCompare = [];

    // ── 分类配置 (动态映射) ──
    var CATEGORY_LABELS = {
        profitability: '盈利能力',
        growth:        '成长扩张',
        health:        '财务健康',
        quality:       '盈利质量',
        profile:       '企业概览',
    };
    var CATEGORY_BADGES = {
        profitability: 'badge-trend',
        growth:        'badge-momentum',
        health:        'badge-chip',
        quality:       'badge-crowding',
        profile:       'badge-volatility',
    };
    var TYPE_LABELS = { moat: '护城河', prosperity: '高景气', both: '通用' };
    var TYPE_CLASSES = { moat: 'badge-trend', prosperity: 'badge-momentum', both: 'badge-crowding' };

    // ── 工具函数 ──
    function escHtml(s) { if (!s) return ''; return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

    function getStockName(code) { return stockNameMap[code] || code; }

    function _isETF(code) { return /^(159|510|512|513|560|588)/.test(code); }

    function getFieldLabel(fieldName) {
        if (fieldLabelMap[fieldName]) return fieldLabelMap[fieldName];
        for (var i = 0; i < registry.length; i++) {
            var ind = registry[i];
            if (ind.name === fieldName) return ind.label || fieldName;
            if ((ind.output || []).indexOf(fieldName) >= 0) return ind.label || fieldName;
        }
        return fieldName;
    }

    var LOWER_BETTER = ['working_capital_efficiency', 'inventory_yoy', 'roic_stability', 'operating_margin_stability'];

    function _fmtField(v, field) {
        if (v == null || v === '' || v === undefined) return '—';
        if (typeof v === 'string') {
            var short = { 'rising': '↑上升', 'declining': '↓下降', 'stable': '→稳定', 'rising_alert': '↑预警', 'declining_bullish': '↓看涨' };
            return short[v] || v;
        }
        var n = Number(v);
        if (isNaN(n)) return String(v);
        var abs = Math.abs(n);
        if (abs >= 100) return n.toFixed(0);
        if (abs >= 1) return n.toFixed(1);
        return n.toFixed(2);
    }

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

    // ── 初始化 ──
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
            // All stocks for compare dialog (same pool)
            allStocksForCompare = stockList.slice();
        } catch(e) { console.error('[FinInd] stock list error:', e); }

        try {
            var res = await fetch(API + '/quant/financial-indicators/registry');
            var d = await res.json();
            registry = d.data || [];
            fieldLabelMap = {};
            registryMap = {};
            registry.forEach(function(ind) {
                registryMap[ind.name] = ind;
                var fieldsMeta = ind.output_fields || {};
                (ind.output || []).forEach(function(f) {
                    var meta = fieldsMeta[f] || {};
                    var meaning = meta.meaning || '';
                    fieldLabelMap[f] = meaning ? (ind.label + ' - ' + meaning) : (ind.label + ' (' + f + ')');
                });
                if (ind.name) fieldLabelMap[ind.name] = ind.label;
            });
        } catch(e) { console.error('[FinInd] registry error:', e); }
    }

    // ══════════════════════════════════════════════════════════
    // Sub-tab switching
    // ══════════════════════════════════════════════════════════
    function switchSubTab(sub) {
        currentSubTab = sub;
        var tabs = ['directory', 'query', 'compare'];
        tabs.forEach(function(t) {
            var btn = document.getElementById('fin-subtab-' + t);
            if (btn) btn.classList.toggle('active', t === sub);
        });
        document.getElementById('fin-directory').style.display = sub === 'directory' ? '' : 'none';
        document.getElementById('fin-query-panel').style.display = sub === 'query' ? '' : 'none';
        document.getElementById('fin-compare-panel').style.display = sub === 'compare' ? '' : 'none';

        if (sub === 'directory') loadDirectory();
        else if (sub === 'query') { loadHotStocks(); }
        else if (sub === 'compare') { updateCompareUI(); }
    }

    // ══════════════════════════════════════════════════════════
    // Tab 1: Indicator Directory (动态分类分组)
    // ══════════════════════════════════════════════════════════
    function loadDirectory() {
        var el = document.getElementById('fin-directory');
        if (!el) return;
        if (!registry.length) {
            el.innerHTML = '<div style="color:var(--text-micro);text-align:center;padding:20px;">加载中...<br><br><button onclick="FinInd.initData().then(function(){FinInd.loadDirectory();})" style="background:transparent;border:1px solid var(--accent-blue);color:var(--accent-blue);padding:5px 12px;border-radius:3px;cursor:pointer;font-size:10px;">重试</button></div>';
            return;
        }

        // 按 category 分组 (动态, 废弃硬编码)
        var groups = {};
        registry.forEach(function(ind) {
            var cat = ind.category || 'other';
            if (!groups[cat]) groups[cat] = [];
            groups[cat].push(ind);
        });

        var catOrder = ['profitability', 'growth', 'health', 'quality', 'profile'];

        var html = '';
        catOrder.forEach(function(cat) {
            var items = groups[cat] || [];
            if (!items.length) return;
            var label = CATEGORY_LABELS[cat] || cat;
            var badgeClass = CATEGORY_BADGES[cat] || 'badge-trend';

            html += '<div class="card" style="padding:0;overflow:hidden;margin-bottom:4px;">';
            // 可折叠标题栏
            html += '<div class="fin-dir-header" style="display:flex;justify-content:space-between;align-items:center;padding:8px 12px;cursor:pointer;background:rgba(255,255,255,0.03);" onclick="FinInd._toggleGroup(this)">';
            html += '<span><span class="badge ' + badgeClass + '" style="margin-right:6px;">' + label + '</span><span style="font-size:10px;color:var(--text-micro);">' + items.length + ' 个指标</span></span>';
            html += '<span style="color:var(--text-micro);font-size:9px;"><i class="fas fa-chevron-down"></i></span>';
            html += '</div>';
            // 指标列表
            html += '<div class="fin-dir-items" style="display:block;">';
            items.forEach(function(ind) {
                var outputCount = (ind.output || []).length;
                html += '<div class="fin-dir-item" style="display:flex;justify-content:space-between;align-items:center;padding:6px 12px 6px 20px;cursor:pointer;border-top:1px solid rgba(255,255,255,0.04);" onclick="FinInd.showIndicatorDetail(\'' + ind.name + '\')" title="' + escHtml(ind.description || '') + '">';
                html += '<div>';
                html += '<span style="color:#fff;font-size:11px;">' + escHtml(ind.label || ind.name) + '</span>';
                html += '<span style="color:var(--text-micro);font-size:9px;margin-left:6px;">(' + ind.name + ')</span>';
                html += '</div>';
                html += '<span style="color:var(--text-micro);font-size:9px;">' + outputCount + ' 字段 <span class="badge ' + (TYPE_CLASSES[ind.indicator_type] || 'badge-trend') + '">' + (TYPE_LABELS[ind.indicator_type] || '') + '</span></span>';
                html += '</div>';
            });
            html += '</div></div>';
        });

        el.innerHTML = html;
    }

    // 折叠/展开分组
    function _toggleGroup(headerEl) {
        var items = headerEl.nextElementSibling;
        if (!items) return;
        var isHidden = items.style.display === 'none';
        items.style.display = isHidden ? 'block' : 'none';
        var icon = headerEl.querySelector('.fa-chevron-down, .fa-chevron-right');
        if (icon) {
            icon.className = isHidden ? 'fas fa-chevron-down' : 'fas fa-chevron-right';
        }
    }

    // ══════════════════════════════════════════════════════════
    // Right Panel: Indicator Detail (Phase 1.3: 全字段展示)
    // ══════════════════════════════════════════════════════════
    async function showIndicatorDetail(name) {
        var panelEmpty = document.getElementById('panel-empty');
        var panelDetail = document.getElementById('panel-detail');
        var detailTitle = document.getElementById('detail-title');
        var detailContent = document.getElementById('detail-content');

        panelEmpty.style.display = 'none';
        panelDetail.style.display = '';
        detailTitle.textContent = '财务算子: ' + name;
        detailContent.innerHTML = '<div style="color:var(--text-micro);padding:10px;text-align:center;"><i class="fas fa-spinner fa-spin"></i> 加载中...</div>';

        var ind = registryMap[name];
        if (!ind) {
            detailContent.innerHTML = '<div style="color:var(--text-dim);padding:20px;text-align:center;">指标未找到</div>';
            return;
        }

        var stages = (ind.applicable_stages || []).join(', ');
        var typeLabel = TYPE_LABELS[ind.indicator_type] || ind.indicator_type || '';
        var typeClass = TYPE_CLASSES[ind.indicator_type] || 'badge-trend';
        var catLabel = CATEGORY_LABELS[ind.category] || ind.category || '';
        var desc = ind.description || '暂无说明';
        var judge = ind.judgment || '暂无判断标准';

        // 获取实际数值 (跨股票均值, 方便参考)
        var fieldValues = {};
        try {
            // 取第一个数值字段的排名数据
            var outputFields = ind.output || [];
            var textFields = new Set(ind.text_output || []);
            var numFields = outputFields.filter(function(f) { return !textFields.has(f); });
            if (numFields.length) {
                var rankRes = await fetch(API + '/quant/financial-indicators/field/' + numFields[0]);
                var rankData = await rankRes.json();
                var rankItems = rankData.data || [];
                fieldValues.count = rankItems.length;
                var vals = rankItems.map(function(r) { return r[numFields[0]]; }).filter(function(v) { return v != null && typeof v === 'number'; });
                if (vals.length) {
                    var sum = vals.reduce(function(a, b) { return a + b; }, 0);
                    fieldValues.avg = sum / vals.length;
                    fieldValues.max = Math.max.apply(null, vals);
                    fieldValues.min = Math.min.apply(null, vals);
                }
            }
        } catch(e) { /* 静默失败 */ }

        var html = '';

        // 头部
        html += '<div class="card">';
        html += '<div style="display:flex;justify-content:space-between;align-items:center;">';
        html += '<span class="card-title">' + escHtml(ind.label) + ' <span style="font-size:10px;color:var(--text-micro);">(' + escHtml(ind.name) + ')</span></span>';
        html += '<span><span class="badge ' + typeClass + '">' + typeLabel + '</span> <span class="badge ' + (CATEGORY_BADGES[ind.category] || 'badge-trend') + '">' + catLabel + '</span></span>';
        html += '</div>';
        html += '<div class="card-meta" style="margin-top:4px;">适用阶段: ' + (stages || '无限制') + ' | 依赖: ' + ((ind.requires || []).join(', ') || '无') + '</div>';
        if (fieldValues.count != null) {
            html += '<div class="card-meta" style="margin-top:2px;">覆盖 ' + fieldValues.count + ' 只股票 | 均值: ' + (fieldValues.avg != null ? fieldValues.avg.toFixed(2) : '?') + ' | 范围: [' + (fieldValues.min != null ? fieldValues.min.toFixed(2) : '?') + ' ~ ' + (fieldValues.max != null ? fieldValues.max.toFixed(2) : '?') + ']</div>';
        }
        html += '</div>';

        // 全部输出字段说明
        html += '<div class="card" style="margin-top:8px;">';
        html += '<div style="display:flex;align-items:center;gap:4px;margin-bottom:6px;"><i class="fas fa-list" style="color:var(--accent-blue);font-size:11px;"></i><span style="font-size:12px;color:#fff;font-weight:600;">输出字段 (' + (ind.output || []).length + ' 个)</span></div>';
        html += '<table class="health-table" style="font-size:10px;"><thead><tr><th>字段名</th><th>类型</th><th>含义</th></tr></thead><tbody>';

        var perField = (ind.output_fields || {});
        (ind.output || []).forEach(function(f) {
            var finfo = perField[f] || {};
            var isText = (ind.text_output || []).indexOf(f) >= 0;
            var typeStr = isText ? 'TEXT' : 'NUMERIC';
            var unit = finfo.unit || (isText ? '' : '?');
            var meaning = finfo.meaning || '';
            html += '<tr><td style="color:var(--accent-blue);font-family:var(--font-mono);">' + escHtml(f) + '</td>';
            html += '<td><span class="badge ' + (isText ? 'badge-chip' : 'badge-trend') + '">' + typeStr + '</span></td>';
            html += '<td style="color:var(--text-dim);">' + escHtml(meaning) + (unit && unit !== '?' ? ' (' + unit + ')' : '') + '</td></tr>';
        });

        html += '</tbody></table></div>';

        // 指标说明
        html += '<div class="card" style="margin-top:8px;">';
        html += '<div style="display:flex;align-items:center;gap:4px;margin-bottom:6px;"><i class="fas fa-book-open" style="color:var(--accent-blue);font-size:11px;"></i><span style="font-size:12px;color:#fff;font-weight:600;">指标说明</span></div>';
        html += '<div style="font-size:11px;color:var(--text-dim);line-height:1.7;">' + escHtml(desc) + '</div>';
        html += '</div>';

        // 判断方法
        html += '<div class="card" style="margin-top:8px;">';
        html += '<div style="display:flex;align-items:center;gap:4px;margin-bottom:6px;"><i class="fas fa-chart-bar" style="color:var(--accent-gold);font-size:11px;"></i><span style="font-size:12px;color:#fff;font-weight:600;">数据判断方法</span></div>';
        html += '<div style="font-size:11px;color:var(--text-dim);line-height:1.7;">' + escHtml(judge) + '</div>';
        html += '</div>';

        // 操作按钮
        html += '<div style="margin-top:10px;display:flex;gap:6px;flex-wrap:wrap;">';
        var firstField = (ind.output || [])[0] || name;
        html += '<button onclick="FinInd.showCrossStockTable(\'' + ind.name + '\', \'' + firstField + '\')" style="background:transparent;border:1px solid var(--accent-blue);color:var(--accent-blue);padding:6px 16px;border-radius:4px;cursor:pointer;font-size:11px;"><i class="fas fa-table"></i> 跨个股时间序列</button>';
        html += '<button onclick="FinInd.loadFieldRanking(\'' + firstField + '\')" style="background:transparent;border:1px solid var(--accent-green);color:var(--accent-green);padding:6px 16px;border-radius:4px;cursor:pointer;font-size:11px;"><i class="fas fa-list-ol"></i> 全股票排名</button>';
        html += '<button onclick="FinInd.addToCompare(\'' + ind.name + '\')" style="background:transparent;border:1px solid var(--accent-gold);color:var(--accent-gold);padding:6px 16px;border-radius:4px;cursor:pointer;font-size:11px;"><i class="fas fa-plus"></i> 加入比较</button>';
        html += '</div>';

        // 跨个股时间序列容器
        html += '<div id="cross-stock-table-container" style="margin-top:10px;"></div>';

        detailContent.innerHTML = html;
        document.getElementById('right-panel').scrollIntoView({behavior:'smooth'});
    }

    // ══════════════════════════════════════════════════════════
    // Right Panel: Cross-stock Time Series (Phase 1.4: 字段切换)
    // ══════════════════════════════════════════════════════════
    async function showCrossStockTable(indicatorName, fieldName) {
        var container = document.getElementById('cross-stock-table-container');
        if (!container) return;

        container.innerHTML = '<div style="color:var(--text-micro);padding:10px;text-align:center;"><i class="fas fa-spinner fa-spin"></i> 加载跨个股数据...</div>';

        if (!stockList.length) await initData();

        var ind = registryMap[indicatorName];
        if (!ind) {
            container.innerHTML = '<div style="color:var(--text-dim);padding:10px;">指标未找到</div>';
            return;
        }

        var outputFields = ind.output || [];
        var textFields = new Set(ind.text_output || []);
        var numericFields = outputFields.filter(function(f) { return !textFields.has(f); });
        var label = ind.label || indicatorName;

        var stocks = stockList.filter(function(s) { return !_isETF(s.stock_code); });
        if (!stocks.length) {
            container.innerHTML = '<div style="color:var(--text-micro);padding:20px;text-align:center;">无持仓或自选股</div>';
            return;
        }

        // 字段选择器
        var activeField = fieldName || numericFields[0] || outputFields[0];
        if (!activeField) {
            container.innerHTML = '<div style="color:var(--text-dim);padding:10px;">无可用字段</div>';
            return;
        }

        try {
            // 并行获取所有股票数据
            var allResults = [];
            for (var i = 0; i < stocks.length; i += 15) {
                var batch = stocks.slice(i, i + 15);
                var batchResults = await Promise.all(batch.map(function(s) {
                    return fetch(API + '/quant/financial-indicators/history/' + s.stock_code + '?fields=' + activeField)
                        .then(function(r) { return r.json(); })
                        .then(function(d) { return { stock: s, data: d.data || [] }; })
                        .catch(function() { return { stock: s, data: [] }; });
                }));
                allResults = allResults.concat(batchResults);
            }

            // Union of dates → top 12
            var dateSet = {};
            allResults.forEach(function(r) {
                r.data.forEach(function(row) {
                    if (row.report_date) dateSet[row.report_date] = true;
                });
            });
            var dates = Object.keys(dateSet).sort().reverse().slice(0, 12);

            if (!dates.length) {
                container.innerHTML = '<div style="color:var(--text-micro);padding:10px;">请先计算指标</div>';
                return;
            }

            var dataMap = {};
            allResults.forEach(function(r) {
                dataMap[r.stock.stock_code] = {};
                r.data.forEach(function(row) {
                    dataMap[r.stock.stock_code][row.report_date] = row[activeField];
                });
            });

            // 字段切换下拉 + 表格
            var html = '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">';
            html += '<span style="font-size:10px;color:var(--text-micro);">' + escHtml(label) + ' — ' + escHtml(activeField) + ' (' + dates.length + 'Q)</span>';
            html += '<select onchange="FinInd.showCrossStockTable(\'' + indicatorName + '\', this.value)" style="background:#000;border:1px solid var(--border-color);color:#fff;padding:3px 8px;border-radius:3px;font-size:10px;">';
            numericFields.forEach(function(f) {
                html += '<option value="' + f + '"' + (f === activeField ? ' selected' : '') + '>' + escHtml(f) + '</option>';
            });
            html += '</select>';
            html += '</div>';

            html += '<div class="fin-table-wrap"><table class="health-table" style="font-size:10px;"><thead><tr>';
            html += '<th style="position:sticky;left:0;background:#111;z-index:2;">股票</th>';
            html += dates.map(function(d) { return '<th style="text-align:right;font-size:9px;">' + d.substring(0,7) + '</th>'; }).join('');
            html += '</tr></thead><tbody>';

            stocks.forEach(function(s) {
                html += '<tr>';
                var nm = getStockName(s.stock_code);
                html += '<td style="position:sticky;left:0;background:#111;z-index:1;color:var(--accent-blue);white-space:nowrap;cursor:pointer;" onclick="FinInd.loadStockFullViewInPanel(\'' + s.stock_code + '\')" title="点击查看全指标">' + escHtml(s.stock_code) + ' ' + escHtml(nm) + '</td>';
                dates.forEach(function(d) {
                    var v = dataMap[s.stock_code] ? dataMap[s.stock_code][d] : undefined;
                    var color = _valueColor(activeField, v);
                    var valStr = (v != null && v !== '') ? _fmtField(v, activeField) : '—';
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

    // ══════════════════════════════════════════════════════════
    // Tab 2: Stock Query (股票搜索 + 最近查看 + 热门)
    // ══════════════════════════════════════════════════════════
    var searchTimer = null;

    function debounceSearch() {
        clearTimeout(searchTimer);
        searchTimer = setTimeout(function() {
            var kw = document.getElementById('fin-query-search').value.trim();
            if (kw) searchStocks(kw);
            else loadHotStocks();
        }, 300);
    }

    function loadHotStocks() {
        var el = document.getElementById('fin-query-results');
        if (!el) return;

        var html = '';

        // 最近查看
        if (recentStocks.length) {
            html += '<div style="font-size:9px;color:var(--text-micro);margin:6px 0 4px 4px;">最近查看</div>';
            html += '<div style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:8px;">';
            recentStocks.forEach(function(code) {
                var nm = getStockName(code);
                html += '<span onclick="FinInd.loadStockFullViewInPanel(\'' + code + '\')" style="cursor:pointer;padding:3px 8px;background:rgba(255,255,255,0.04);border-radius:3px;font-size:10px;color:var(--accent-blue);">' + escHtml(code) + ' ' + escHtml(nm) + '</span>';
            });
            html += '</div>';
        }

        // 热门股票 (从 stockList 取前 10)
        var hot = stockList.slice(0, 10);
        if (hot.length) {
            html += '<div style="font-size:9px;color:var(--text-micro);margin:6px 0 4px 4px;">持仓/自选股</div>';
            html += '<div style="display:flex;flex-wrap:wrap;gap:4px;">';
            hot.forEach(function(s) {
                html += '<span onclick="FinInd.loadStockFullViewInPanel(\'' + s.stock_code + '\')" style="cursor:pointer;padding:3px 8px;background:rgba(255,255,255,0.04);border-radius:3px;font-size:10px;color:var(--accent-blue);">' + escHtml(s.stock_code) + ' ' + escHtml(s.stock_name) + '</span>';
            });
            html += '</div>';
        }

        if (!html) {
            html = '<div style="color:var(--text-micro);text-align:center;padding:20px;">输入关键词搜索股票</div>';
        }

        el.innerHTML = html;
    }

    async function searchStocks(keyword) {
        var el = document.getElementById('fin-query-results');
        if (!el) return;

        var kw = keyword.toLowerCase();
        var matched = stockList.filter(function(s) {
            return s.stock_code.indexOf(kw) >= 0 || (s.stock_name || '').toLowerCase().indexOf(kw) >= 0;
        }).slice(0, 30);

        if (!matched.length) {
            el.innerHTML = '<div style="color:var(--text-micro);text-align:center;padding:20px;">无匹配结果</div>';
            return;
        }

        var html = '<div style="font-size:9px;color:var(--text-micro);margin:4px;">搜索结果: ' + matched.length + ' 只</div>';
        matched.forEach(function(s) {
            html += '<div onclick="FinInd.loadStockFullViewInPanel(\'' + s.stock_code + '\')" style="display:flex;justify-content:space-between;align-items:center;padding:6px 8px;cursor:pointer;border-bottom:1px solid rgba(255,255,255,0.04);">';
            html += '<span style="color:var(--accent-blue);font-size:11px;">' + escHtml(s.stock_code) + ' ' + escHtml(s.stock_name) + '</span>';
            html += '<span style="color:var(--text-micro);font-size:9px;"><i class="fas fa-chevron-right"></i></span>';
            html += '</div>';
        });

        el.innerHTML = html;
    }

    // ══════════════════════════════════════════════════════════
    // Right Panel: Stock Full View (展开完整历史)
    // ══════════════════════════════════════════════════════════
    async function loadStockFullViewInPanel(code) {
        // 记录最近查看
        recentStocks = recentStocks.filter(function(c) { return c !== code; });
        recentStocks.unshift(code);
        if (recentStocks.length > 10) recentStocks = recentStocks.slice(0, 10);
        localStorage.setItem('fin_recent', JSON.stringify(recentStocks));

        var panelEmpty = document.getElementById('panel-empty');
        var panelDetail = document.getElementById('panel-detail');
        var detailTitle = document.getElementById('detail-title');
        var detailContent = document.getElementById('detail-content');

        panelEmpty.style.display = 'none';
        panelDetail.style.display = '';
        detailTitle.textContent = '财务指标: ' + code + ' ' + getStockName(code);
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

            // 动态分组: 从 registry 按 category 组织
            var catOrder = ['profitability', 'growth', 'health', 'quality', 'profile'];

            // Build field → category mapping from registry
            var fieldCatMap = {};
            registry.forEach(function(ind) {
                var cat = ind.category || 'other';
                (ind.output || []).forEach(function(f) {
                    if (!fieldCatMap[cat]) fieldCatMap[cat] = [];
                    if (fieldCatMap[cat].indexOf(f) < 0) fieldCatMap[cat].push(f);
                });
            });

            var fullHtml = '';
            fullHtml += '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;padding:8px 12px;background:rgba(255,255,255,0.03);border-radius:4px;">';
            fullHtml += '<div><span style="font-size:14px;color:var(--accent-blue);font-weight:600;">' + escHtml(code) + ' ' + escHtml(getStockName(code)) + '</span>';
            fullHtml += '<span style="font-size:10px;color:var(--text-micro);margin-left:8px;">' + rows.length + ' 期 | 最新: ' + (rows[0].report_date || '?') + '</span></div>';
            fullHtml += '</div>';

            catOrder.forEach(function(cat) {
                var fields = fieldCatMap[cat] || [];
                var availableFields = fields.filter(function(f) {
                    return latestRows.some(function(r) { return r[f] !== undefined && r[f] !== null; });
                });
                if (!availableFields.length) return;

                var catLabel = CATEGORY_LABELS[cat] || cat;
                fullHtml += '<div class="fin-cat-title" style="margin-top:4px;">' + catLabel + '</div>';
                fullHtml += '<div class="fin-table-wrap" style="margin-bottom:4px;">';
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

    // ══════════════════════════════════════════════════════════
    // Right Panel: Field Ranking (Phase 1.1: 含 stock_name)
    // ══════════════════════════════════════════════════════════
    async function loadFieldRanking(field) {
        var panelEmpty = document.getElementById('panel-empty');
        var panelDetail = document.getElementById('panel-detail');
        var detailTitle = document.getElementById('detail-title');
        var detailContent = document.getElementById('detail-content');

        panelEmpty.style.display = 'none';
        panelDetail.style.display = '';
        var lbl = getFieldLabel(field) || field;
        detailTitle.textContent = '排名: ' + lbl;
        detailContent.innerHTML = '<div style="color:var(--text-micro);padding:10px;text-align:center;"><i class="fas fa-spinner fa-spin"></i> 加载中...</div>';

        try {
            var res = await fetch(API + '/quant/financial-indicators/field/' + field);
            var d = await res.json();
            var items = d.data || [];

            if (!items.length) {
                detailContent.innerHTML = '<div style="color:var(--text-micro);padding:20px;text-align:center;">无数据</div>';
                return;
            }

            // 找关联 indicator 的其他字段, 供切换
            var relatedFields = [];
            for (var key in registryMap) {
                var ind = registryMap[key];
                if ((ind.output || []).indexOf(field) >= 0) {
                    relatedFields = (ind.output || []).filter(function(f) { return f !== field; });
                    break;
                }
            }

            var html = '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">';
            html += '<span style="font-size:10px;color:var(--text-micro);">' + items.length + ' 只股票</span>';
            if (relatedFields.length) {
                html += '<select onchange="FinInd.loadFieldRanking(this.value)" style="background:#000;border:1px solid var(--border-color);color:#fff;padding:3px 8px;border-radius:3px;font-size:10px;">';
                html += '<option value="' + field + '">' + escHtml(lbl) + ' (当前)</option>';
                relatedFields.forEach(function(f) {
                    html += '<option value="' + f + '">' + escHtml(getFieldLabel(f) || f) + '</option>';
                });
                html += '</select>';
            }
            html += '</div>';

            html += '<div class="fin-table-wrap"><table class="health-table" style="font-size:10px;"><thead><tr>';
            html += '<th>#</th><th>代码</th><th>名称</th><th style="text-align:right;">' + escHtml(lbl) + '</th><th>报告期</th></tr></thead><tbody>';

            items.forEach(function(i, idx) {
                var v = i[field] || i.value;
                var color = _valueColor(field, v);
                var valStr = (v != null && v !== '') ? _fmtField(v, field) : '—';
                var nm = i.stock_name || getStockName(i.stock_code) || '';
                html += '<tr onclick="FinInd.loadStockFullViewInPanel(\'' + i.stock_code + '\')" style="cursor:pointer;" title="点击查看全指标">';
                html += '<td style="color:var(--text-micro);">' + (idx + 1) + '</td>';
                html += '<td style="color:var(--accent-blue);font-family:var(--font-mono);">' + i.stock_code + '</td>';
                html += '<td>' + escHtml(nm) + '</td>';
                html += '<td style="text-align:right;font-family:var(--font-mono);color:' + color + ';">' + valStr + '</td>';
                html += '<td>' + (i.report_date || '') + '</td></tr>';
            });

            html += '</tbody></table></div>';
            detailContent.innerHTML = html;
        } catch(e) {
            detailContent.innerHTML = '<div style="color:var(--accent-red);padding:20px;">加载失败: ' + escHtml(e.message) + '</div>';
        }
    }

    // ══════════════════════════════════════════════════════════
    // Tab 3: Cross Comparison (Phase 3)
    // ══════════════════════════════════════════════════════════
    function updateCompareUI() {
        var stockEl = document.getElementById('compare-stock-list');
        var indEl = document.getElementById('compare-indicator-list');

        if (stockEl) {
            if (compareStocks.length) {
                stockEl.innerHTML = compareStocks.map(function(code) {
                    var nm = getStockName(code);
                    return '<span style="display:inline-block;margin:2px;padding:2px 6px;background:rgba(255,255,255,0.05);border-radius:3px;font-size:10px;">' + escHtml(nm) + ' <span onclick="FinInd.removeStock(\'' + code + '\')" style="cursor:pointer;color:var(--accent-red);">&times;</span></span>';
                }).join('');
            } else {
                stockEl.innerHTML = '<span style="color:var(--text-micro);font-size:10px;">(空)</span>';
            }
        }

        if (indEl) {
            if (compareIndicators.length) {
                indEl.innerHTML = compareIndicators.map(function(name) {
                    var lbl = getFieldLabel(name) || name;
                    return '<span style="display:inline-block;margin:2px;padding:2px 6px;background:rgba(255,255,255,0.05);border-radius:3px;font-size:10px;">' + escHtml(lbl) + ' <span onclick="FinInd.removeIndicator(\'' + name + '\')" style="cursor:pointer;color:var(--accent-red);">&times;</span></span>';
                }).join('');
            } else {
                indEl.innerHTML = '<span style="color:var(--text-micro);font-size:10px;">(空)</span>';
            }
        }
    }

    function _saveCompareState() {
        localStorage.setItem('fin_compare_stocks', JSON.stringify(compareStocks));
        localStorage.setItem('fin_compare_inds', JSON.stringify(compareIndicators));
    }

    function addToCompare(name) {
        if (compareIndicators.indexOf(name) >= 0) {
            Modal.alert('提示', '该指标已在比较列表中');
            return;
        }
        compareIndicators.push(name);
        _saveCompareState();
        updateCompareUI();
        Modal.alert('已添加', '指标已加入交叉比较列表，请切换到 [交叉比较] 标签查看');
    }

    function addStock(code) {
        if (compareStocks.indexOf(code) >= 0) { Modal.alert('提示', '该股票已在列表中'); return; }
        if (compareStocks.length >= 6) { Modal.alert('提示', '最多比较 6 只股票'); return; }
        compareStocks.push(code);
        _saveCompareState();
        updateCompareUI();
    }

    function removeStock(code) {
        compareStocks = compareStocks.filter(function(c) { return c !== code; });
        _saveCompareState();
        updateCompareUI();
    }

    function addIndicator(name) {
        if (compareIndicators.indexOf(name) >= 0) { Modal.alert('提示', '该指标已在列表中'); return; }
        if (compareIndicators.length >= 10) { Modal.alert('提示', '最多比较 10 个指标'); return; }
        compareIndicators.push(name);
        _saveCompareState();
        updateCompareUI();
    }

    function removeIndicator(name) {
        compareIndicators = compareIndicators.filter(function(i) { return i !== name; });
        _saveCompareState();
        updateCompareUI();
    }

    function showAddStockDialog() {
        // 用 Modal 展示可选股票
        var html = '<div style="max-height:300px;overflow-y:auto;">';
        html += '<input type="text" id="compare-stock-search" placeholder="搜索..." oninput="FinInd._filterStockDialog(this.value)" style="width:100%;background:#000;border:1px solid var(--border-color);color:#fff;padding:4px 8px;border-radius:3px;font-size:11px;margin-bottom:6px;">';
        html += '<div id="compare-stock-list-container">';
        allStocksForCompare.forEach(function(s) {
            var selected = compareStocks.indexOf(s.stock_code) >= 0 ? ' style="opacity:0.4;"' : '';
            html += '<div class="compare-stock-item" data-code="' + s.stock_code + '" data-name="' + escHtml(s.stock_name) + '"' + selected + ' onclick="FinInd._pickStock(\'' + s.stock_code + '\')" style="padding:4px 6px;cursor:pointer;border-bottom:1px solid rgba(255,255,255,0.04);font-size:11px;">';
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
        updateCompareUI();
        // 刷新 dialog
        showAddStockDialog();
    }

    function _filterStockDialog(keyword) {
        var kw = keyword.toLowerCase();
        var items = document.querySelectorAll('.compare-stock-item');
        items.forEach(function(el) {
            var code = el.dataset.code || '';
            var name = (el.dataset.name || '').toLowerCase();
            el.style.display = (code.indexOf(kw) >= 0 || name.indexOf(kw) >= 0) ? '' : 'none';
        });
    }

    function showAddIndicatorDialog() {
        var html = '<div style="max-height:300px;overflow-y:auto;">';
        html += '<input type="text" id="compare-ind-search" placeholder="搜索..." oninput="FinInd._filterIndDialog(this.value)" style="width:100%;background:#000;border:1px solid var(--border-color);color:#fff;padding:4px 8px;border-radius:3px;font-size:11px;margin-bottom:6px;">';
        html += '<div id="compare-ind-container">';
        registry.forEach(function(ind) {
            var selected = compareIndicators.indexOf(ind.name) >= 0 ? ' style="opacity:0.4;"' : '';
            html += '<div class="compare-ind-item" data-name="' + (ind.label || ind.name) + '"' + selected + ' onclick="FinInd._pickIndicator(\'' + ind.name + '\')" style="padding:4px 6px;cursor:pointer;border-bottom:1px solid rgba(255,255,255,0.04);font-size:11px;">';
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
        updateCompareUI();
        showAddIndicatorDialog();
    }

    function _filterIndDialog(keyword) {
        var kw = keyword.toLowerCase();
        var items = document.querySelectorAll('.compare-ind-item');
        items.forEach(function(el) {
            var name = (el.dataset.name || '').toLowerCase();
            el.style.display = name.indexOf(kw) >= 0 ? '' : 'none';
        });
    }

    async function runComparison() {
        if (!compareStocks.length || !compareIndicators.length) {
            Modal.alert('提示', '请先添加股票和指标');
            return;
        }

        // 显示结果到右侧面板
        var panelEmpty = document.getElementById('panel-empty');
        var panelDetail = document.getElementById('panel-detail');
        var detailTitle = document.getElementById('detail-title');
        var detailContent = document.getElementById('detail-content');

        panelEmpty.style.display = 'none';
        panelDetail.style.display = '';
        detailTitle.textContent = '交叉比较: ' + compareStocks.length + ' 只股票 × ' + compareIndicators.length + ' 个指标';
        detailContent.innerHTML = '<div style="color:var(--text-micro);padding:10px;text-align:center;"><i class="fas fa-spinner fa-spin"></i> 加载比较数据...</div>';

        try {
            var res = await fetch(API + '/quant/financial-indicators/compare', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    stocks: compareStocks,
                    indicators: compareIndicators
                })
            });
            var d = await res.json();
            var data = d.data || {};

            var stocks = data.stocks || [];
            var rows = data.rows || [];

            if (!rows.length) {
                detailContent.innerHTML = '<div style="color:var(--text-micro);padding:20px;">无比较数据</div>';
                return;
            }

            var html = '<div style="margin-bottom:8px;font-size:10px;color:var(--text-micro);">';

            // 比较矩阵表
            html += '<div class="fin-table-wrap"><table class="health-table" style="font-size:11px;"><thead><tr>';
            html += '<th style="position:sticky;left:0;background:#0a0a0a;z-index:1;">指标</th>';
            stocks.forEach(function(s) {
                html += '<th style="text-align:right;white-space:nowrap;">' + escHtml(s.code) + '<br><span style="font-size:9px;color:var(--text-micro);font-weight:normal;">' + escHtml(s.name) + '</span></th>';
            });
            html += '</tr></thead><tbody>';

            rows.forEach(function(row) {
                html += '<tr>';
                html += '<td style="position:sticky;left:0;background:#0a0a0a;z-index:1;white-space:nowrap;font-weight:600;">' + escHtml(row.label || row.indicator) + '</td>';
                stocks.forEach(function(s) {
                    var v = row.values ? row.values[s.code] : undefined;
                    // Find the right value
                    var val = v;
                    if (val === undefined) {
                        // Try to look up differently
                        for (var key in row.values) {
                            if (key.indexOf(s.code) >= 0 || s.code.indexOf(key) >= 0) {
                                val = row.values[key];
                                break;
                            }
                        }
                    }
                    var color = _valueColor(row.indicator, val);
                    var valStr = (val != null && val !== '') ? _fmtField(val, row.indicator) : '—';
                    html += '<td style="text-align:right;font-family:var(--font-mono);color:' + color + ';">' + valStr + '</td>';
                });
                html += '</tr>';
            });

            html += '</tbody></table></div>';

            // 操作提示
            html += '<div style="margin-top:8px;text-align:center;font-size:10px;color:var(--text-micro);">';
            html += '<button onclick="FinInd._exportCompareCSV()" style="background:transparent;border:1px solid var(--text-dim);color:var(--text-dim);padding:4px 12px;border-radius:3px;cursor:pointer;font-size:10px;"><i class="fas fa-download"></i> 导出CSV</button>';
            html += '</div>';

            detailContent.innerHTML = html;
        } catch(e) {
            detailContent.innerHTML = '<div style="color:var(--accent-red);padding:20px;">比较失败: ' + escHtml(e.message) + '</div>';
        }
    }

    function _exportCompareCSV() {
        var table = document.querySelector('#detail-content table');
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
        var blob = new Blob([csv.join('\n')], { type: 'text/csv;charset=utf-8;' });
        var link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = 'fin_compare_' + new Date().toISOString().slice(0, 10) + '.csv';
        link.click();
    }

    // ══════════════════════════════════════════════════════════
    // Public API
    // ══════════════════════════════════════════════════════════
    return {
        initData: initData,
        switchSubTab: switchSubTab,
        loadDirectory: loadDirectory,
        _toggleGroup: _toggleGroup,
        showIndicatorDetail: showIndicatorDetail,
        showCrossStockTable: showCrossStockTable,
        debounceSearch: debounceSearch,
        searchStocks: searchStocks,
        loadStockFullViewInPanel: loadStockFullViewInPanel,
        loadFieldRanking: loadFieldRanking,
        addToCompare: addToCompare,
        updateCompareUI: updateCompareUI,
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
        // 保留旧接口兼容
        switchView: switchSubTab,
    };
})();
