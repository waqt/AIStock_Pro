/**
 * 定量估值前端模块 (Valuation) — V1.1
 *
 * 功能:
 *   - 估值方法注册表展示 (4 类分组)
 *   - 单股票估值计算 + 按类型分组仪表盘
 *   - PE/PB 百分位仪表盘图 (ECharts gauge)
 *   - 全部输出字段详情表
 *   - 多股票估值对比
 *   - 股票代码自动补全
 *
 * 命名空间: window.Valuation
 */
window.Valuation = {
    currentTab: 'dashboard',
    stockCode: '',
    stockName: '',
    lastResult: null,
    methodMeta: {},  // 估值方法元数据缓存, GET /registry

    // ── 初始化 ──
    init: function() {
        try {
            this.loadMethodList();
            this._setupAutocomplete();
            this._loadMethodMeta();  // cache method metadata for tooltips
            var codeInput = document.getElementById('val-code');
            if (codeInput) {
                codeInput.addEventListener('keyup', function(e) {
                    if (e.key === 'Enter') Valuation.run();
                });
            }
        } catch(e) {
            console.error('[Valuation] init error:', e);
        }
    },

    /** 缓存估值方法元数据（用于 dashboard tooltip） */
    _loadMethodMeta: function() {
        var self = this;
        fetch(API_BASE + '/quant/valuation/registry')
            .then(function(r) { return r.json(); })
            .then(function(d) {
                var meta = {};
                (d.data || []).forEach(function(m) { meta[m.name] = m; });
                self.methodMeta = meta;
            })
            .catch(function() { self.methodMeta = {}; });
    },

    /** 点击 (?) 弹出字段含义说明 */
    _showFieldHelp: function(fieldName) {
        try {
            if (!fieldName) {
                Modal.alert('帮助说明', '暂无对应字段的说明');
                return;
            }
            var fh = Valuation.fieldHelp || {};
            var fieldDesc = fh[fieldName];
            if (!fieldDesc) {
                Modal.alert('帮助说明', '暂无该字段的详细说明');
                return;
            }
            // 查找该字段对应的估值方法
            var methodName = null;
            for (var mn in Valuation.methodMeta) {
                var outputs = Valuation.methodMeta[mn].output || [];
                if (outputs.indexOf(fieldName) >= 0) { methodName = mn; break; }
            }
            // 构造帮助内容: 字段说明 + 方法背景
            var html = '<div style="font-size:12px;line-height:1.7;">';
            html += '<div style="background:rgba(78,158,255,0.06);padding:10px 12px;border-radius:6px;margin-bottom:10px;border-left:3px solid var(--accent-blue);">';
            html += '<div style="color:var(--text-micro);font-size:10px;margin-bottom:2px;">📌 这个数字代表</div>';
            html += '<div style="color:#ddd;font-size:12px;">' + Valuation.esc(fieldDesc) + '</div></div>';
            if (methodName) {
                var meta = Valuation.methodMeta[methodName];
                var mLabel = meta.label || methodName;
                html += '<div style="background:rgba(255,255,255,0.02);padding:8px 10px;border-radius:4px;margin-top:6px;">';
                html += '<div style="color:var(--text-micro);font-size:10px;margin-bottom:4px;">计算方法: ' + Valuation.esc(mLabel) + '</div>';
                if (meta.description) {
                    html += '<div style="color:#999;font-size:10px;margin-bottom:3px;">' + Valuation.esc(meta.description) + '</div>';
                }
                if (meta.judgment) {
                    html += '<div style="color:#777;font-size:10px;">判读: ' + Valuation.esc(meta.judgment) + '</div>';
                }
                html += '</div>';
            }
            html += '</div>';
            Modal.alert('📖 ' + Valuation.esc(fieldName), html);
        } catch(e) {
            console.error('[Valuation] _showFieldHelp error:', e);
            Modal.alert('字段说明', '无法加载详情, 请重试。');
        }
    },

    _autocompleteTimer: null,

    _setupAutocomplete: function() {
        var input = document.getElementById('val-code');
        var list = document.getElementById('val-stock-list');
        if (!input || !list) return;
        input.addEventListener('input', function() {
            var q = this.value.trim();
            if (q.length < 1) { list.innerHTML = ''; return; }
            if (Valuation._autocompleteTimer) clearTimeout(Valuation._autocompleteTimer);
            Valuation._autocompleteTimer = setTimeout(function() {
                fetch(API_BASE + '/data/stock-list/search?q=' + encodeURIComponent(q) + '&limit=20')
                .then(function(r) { return r.json(); })
                .then(function(items) {
                    list.innerHTML = items.map(function(i) {
                        var label = i.code + ' - ' + (i.name || '?');
                        return '<option value="' + i.code + '" data-name="' + (i.name || '') + '">' + label + '</option>';
                    }).join('');
                })
                .catch(function() {});
            }, 200);
        });
        // 选中后设置 stockName
        input.addEventListener('change', function() {
            var val = this.value.trim();
            if (!val) return;
            var opts = list.querySelectorAll('option');
            for (var i = 0; i < opts.length; i++) {
                if (opts[i].value === val) {
                    Valuation.stockName = opts[i].getAttribute('data-name') || '';
                    break;
                }
            }
        });
    },

    // ── 工具 ──
    esc: function(s) {
        if (!s) return '';
        return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    },

    _v: function(v, decimals) {
        if (v == null) return null;
        decimals = decimals || 2;
        if (typeof v === 'number') return v.toFixed(decimals);
        var n = parseFloat(v);
        return isNaN(n) ? v : n.toFixed(decimals);
    },

    _fmt: function(v, unit) {
        if (v == null || v === '') return '<span class="null-placeholder">—</span>';
        var s = typeof v === 'number' ? v : parseFloat(v);
        if (isNaN(s)) return '<span class="null-placeholder">—</span>';
        if (unit === '¥') return '¥' + s.toFixed(2);
        if (unit === '%' || unit === '% (百分位)') return s.toFixed(1) + '%';
        if (unit === '倍') return s.toFixed(2) + 'x';
        if (unit === '亿元') return s.toFixed(1) + '亿';
        if (unit === '分') return s.toFixed(0);
        return s.toFixed(2);
    },

    _judgeValue: function(v, fieldName) {
        if (v == null || isNaN(v)) return {cls: '', label: ''};
        v = typeof v === 'number' ? v : parseFloat(v);
        if (isNaN(v)) return {cls: '', label: ''};
        // PE/PB/PS 百分位判断
        if (fieldName.indexOf('percentile') >= 0) {
            if (v > 80) return {cls: 'status-over', label: '⚠偏贵'};
            if (v < 20) return {cls: 'status-under', label: '✓便宜'};
            return {cls: 'status-fair', label: '●合理'};
        }
        // 安全边际 / upsdie / vs_price 等 (正值=好)
        if (fieldName.indexOf('pct') >= 0 || fieldName.indexOf('margin') >= 0 || fieldName.indexOf('upside') >= 0 || fieldName.indexOf('vs_price') >= 0) {
            if (v > 15) return {cls: 'status-under', label: '✓充裕'};
            if (v > 0) return {cls: 'status-fair', label: '●尚可'};
            return {cls: 'status-over', label: '⚠不足'};
        }
        // PEG
        if (fieldName === 'peg_ratio') {
            if (v < 1) return {cls: 'status-under', label: '✓低估'};
            if (v < 2) return {cls: 'status-fair', label: '●合理'};
            return {cls: 'status-over', label: '⚠高估'};
        }
        // EV/IC
        if (fieldName === 'ev_ic_ratio') {
            if (v < 1.5) return {cls: 'status-under', label: '✓低估'};
            if (v < 3) return {cls: 'status-fair', label: '●合理'};
            return {cls: 'status-over', label: '⚠高估'};
        }
        return {cls: '', label: ''};
    },

    statusClass: function(v) {
        if (!v) return '';
        var s = String(v).toLowerCase();
        if (s.indexOf('低估')>=0 || s.indexOf('折价')>=0 || s.indexOf('buy')>=0 || s.indexOf('便宜')>=0 || s.indexOf('创造价值')>=0) {
            return 'status-under';
        }
        if (s.indexOf('高估')>=0 || s.indexOf('溢价')>=0 || s.indexOf('泡沫')>=0 || s.indexOf('sell')>=0 || s.indexOf('贵')>=0 || s.indexOf('毁损价值')>=0) {
            return 'status-over';
        }
        return 'status-fair';
    },

    // ── 加载方法注册表 ──
    loadMethodList: function() {
        var el = document.getElementById('val-method-list');
        if (!el) return;
        var self = this;
        fetch(API_BASE + '/quant/valuation/registry')
            .then(function(r) { return r.json(); })
            .then(function(d) {
                var list = d.data || [];
                var catNames = {relative:'相对估值', absolute:'绝对估值', advanced:'进阶估值', composite:'合成指标', dynamic:'动态估值'};
                var catBadges = {relative:'badge-relative', absolute:'badge-absolute', advanced:'badge-advanced', composite:'badge-composite', dynamic:'badge-dynamic'};
                var groups = {};
                list.forEach(function(m) {
                    var c = m.category || 'other';
                    if (!groups[c]) groups[c] = [];
                    groups[c].push(m);
                });
                var html = '';
                var order = ['relative','absolute','advanced','composite','dynamic'];
                order.forEach(function(c) {
                    if (!groups[c]) return;
                    html += '<div class="cat-group">';
                    html += '<div class="cat-group-title">' + (catNames[c]||c) + ' (' + groups[c].length + ')</div>';
                    groups[c].forEach(function(m) {
                        html += '<div class="v-method-card" onclick="Valuation.showMethodDetail(\'' + m.name + '\')">';
                        html += '<div class="cat"><span class="badge ' + (catBadges[c]||'') + '">' + (catNames[c]||c) + '</span></div>';
                        html += '<div class="name">' + self.esc(m.label||m.name) + '</div>';
                        html += '<div class="desc">' + self.esc((m.description||'').substring(0,60)) + '</div>';
                        html += '</div>';
                    });
                    html += '</div>';
                });
                el.innerHTML = html || '<div style="color:var(--text-micro);text-align:center;padding:20px;">暂无估值方法</div>';
            })
            .catch(function(e) { el.innerHTML = '<div style="color:var(--accent-red);">加载失败</div>'; });
    },

    // ── 方法详情跳转 ──
    showMethodDetail: function(name) {
        this.switchTab('details');
        var el = document.getElementById('val-details-content');
        if (!el) return;
        el.innerHTML = '<div style="color:var(--text-dim);">加载中...</div>';
        var self = this;
        fetch(API_BASE + '/quant/valuation/registry')
            .then(function(r) { return r.json(); })
            .then(function(d) {
                var list = d.data || [];
                var method = null;
                for (var i = 0; i < list.length; i++) {
                    if (list[i].name === name) { method = list[i]; break; }
                }
                if (!method) { el.innerHTML = '<div style="color:var(--text-dim);">未找到方法</div>'; return; }

                var html = '<div class="detail-section">';
                html += '<h4 style="color:#fff;">' + self.esc(method.label||method.name) + '</h4>';
                html += '<p>' + self.esc(method.description||'') + '</p>';
                html += '<table class="v-table"><tbody>';
                html += '<tr><td>识别名</td><td><code>' + self.esc(method.name) + '</code></td></tr>';
                html += '<tr><td>类别</td><td>' + self.esc(method.category) + '</td></tr>';
                html += '<tr><td>输出字段</td><td>' + (method.output||[]).map(function(f) {
                    var isText = (method.text_output||[]).indexOf(f) >= 0;
                    return '<code>' + f + '</code>' + (isText ? ' <span class="badge" style="color:var(--accent-gold);">text</span>' : '');
                }).join(', ') + '</td></tr>';
                html += '<tr><td>依赖字段</td><td>' + (method.requires||[]).map(function(f) { return '<code>' + f + '</code>'; }).join(', ') + '</td></tr>';
                html += '<tr><td>需日线历史</td><td>' + (method.requires_market_data ? '是' : '否') + '</td></tr>';
                html += '<tr><td>需财务数据</td><td>' + (method.requires_financial_data ? '是' : '否') + '</td></tr>';
                html += '<tr><td>参数</td><td>' + (method.params ? JSON.stringify(method.params) : '-') + '</td></tr>';
                html += '</tbody></table>';

                if (Valuation.lastResult) {
                    var hasOutput = false;
                    var outHtml = '<h5 style="color:#ccc;margin-top:12px;">当前计算结果</h5><table class="v-table"><thead><tr><th>字段</th><th>值</th></tr></thead><tbody>';
                    (method.output||[]).forEach(function(f) {
                        if (Valuation.lastResult[f] != null) {
                            hasOutput = true;
                            outHtml += '<tr><td>' + f + '</td><td style="font-family:var(--font-mono);">' + self.esc(String(Valuation.lastResult[f])) + '</td></tr>';
                        }
                    });
                    outHtml += '</tbody></table>';
                    if (hasOutput) html += outHtml;
                }

                html += '</div>';
                el.innerHTML = html;
            })
            .catch(function(e) { el.innerHTML = '<div style="color:var(--accent-red);">加载失败: ' + e.message + '</div>'; });
    },

    // ── Tab 切换 ──
    switchTab: function(tab) {
        this.currentTab = tab;
        var btns = document.querySelectorAll('.right-panel .tab-btn');
        for (var i = 0; i < btns.length; i++) { btns[i].classList.remove('active'); }
        var btn = document.getElementById('vt-' + tab);
        if (btn) btn.classList.add('active');

        var panels = document.querySelectorAll('.right-panel .tab-panel');
        for (var i = 0; i < panels.length; i++) { panels[i].style.display = 'none'; }
        var panel = document.getElementById('vtab-' + tab);
        if (panel) panel.style.display = 'flex';

        if (tab === 'dashboard' && this.lastResult) {
            setTimeout(function() { }, 100);
        }
    },

    // ── 主计算入口 ──
    run: function() {
        var code = document.getElementById('val-code').value.trim();
        if (!code) { Modal.alert('提示', '请输入股票代码'); return; }
        this.stockCode = code;
        // Try to get stock_name from datalist
        var list = document.getElementById('val-stock-list');
        if (list) {
            var opts = list.querySelectorAll('option');
            for (var i = 0; i < opts.length; i++) {
                if (opts[i].value === code) {
                    this.stockName = opts[i].getAttribute('data-name') || '';
                    break;
                }
            }
        }
        var statusEl = document.getElementById('val-status');
        var btn = document.getElementById('btn-val');
        statusEl.textContent = '全量重算中...';
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 重算中';
        var self = this;

        fetch(API_BASE + '/quant/valuation/compute/' + code + '?mode=historical', { method: 'POST' })
            .then(function(r) { return r.json(); })
            .then(function(d) {
                if (!d.success) throw new Error(d.error || '计算失败');
                return fetch(API_BASE + '/quant/valuation/' + code);
            })
            .then(function(r) { return r.json(); })
            .then(function(d) {
                if (!d.success) throw new Error(d.error || '查询失败');
                self.lastResult = d.data;
                self.stockName = self.stockName || (d.data.stock_name || '');
                self.renderDashboard(d.data);
                self.renderPEBand(d.data);
                self.switchTab('dashboard');
                statusEl.textContent = '计算完成: ' + (d.data.trade_date || '');
            })
            .catch(function(e) {
                statusEl.textContent = '错误: ' + e.message;
                Modal.alert('计算失败', e.message);
            })
            .finally(function() {
                btn.disabled = false;
                btn.innerHTML = '<i class="fas fa-calculator"></i> 计算';
            });
    },

    // ── 渲染估值仪表盘 (动态分组) ──
    renderDashboard: function(data) {
        if (!data || data.message) {
            document.getElementById('val-empty').style.display = 'flex';
            document.getElementById('val-result').style.display = 'none';
            return;
        }
        document.getElementById('val-empty').style.display = 'none';
        document.getElementById('val-result').style.display = 'flex';

        var code = this.stockCode;
        var sname = this.stockName || data.stock_name || '';
        var displayName = sname ? sname + ' (' + code + ')' : code;

        // ── 分类配置 ──
        var catConfig = [
            { key: 'relative',  label: '相对估值',   badge: 'badge-relative',  defaultOpen: true  },
            { key: 'absolute',  label: '绝对估值',   badge: 'badge-absolute',  defaultOpen: true  },
            { key: 'advanced',  label: '进阶指标',   badge: 'badge-advanced',  defaultOpen: false },
            { key: 'dynamic',   label: '动态估值',   badge: 'badge-dynamic',   defaultOpen: false },
        ];

        // 各方法的主要输出字段 (取第一个非 text_output 的字段作为代表值)
        var methodPrimaryFields = {
            'pe_percentile':     ['pe_percentile'],
            'pb_percentile':     ['pb_percentile'],
            'ps_valuation':      ['ps_percentile', 'ps_ttm'],
            'peg_analysis':      ['peg_ratio'],
            'fcf_yield':         ['fcf_yield_pct', 'implied_value'],
            'ev_ic':             ['ev_ic_ratio'],
            'industry_premium':  ['premium_pct'],
            'graham_number':     ['graham_number'],
            'residual_income':   ['rim_value'],
            'gordon_growth':     ['ddm_value'],
            'net_asset_value':   ['nav_per_share'],
            'scenario_estimate': ['weighted_target', 'bull_target', 'bear_target'],
            'quality_adjusted':  ['adjusted_pe', 'quality_bonus_pct'],
            'roic_spread':       ['roic_spread_pct'],
            'three_stage_growth': ['three_stage_value'],
            'gross_margin_adjustment': ['gm_target_price'],
            'scissor_gap_inflection':  ['scissor_target_price'],
            'growth_adjusted_peg':     ['growth_peg_target_price'],
            'dol_adjusted_valuation':  ['dol_target_price'],
            'risk_adjusted_npv':       ['rgv_target_price'],
            'revenue_growth_framework': ['rgf_target_price'],
        };

        // 方法 → category 映射 (从 registry 加载)
        var methodCat = {};
        var self = this;

        // 先从 data 推断方法类别: 如果 data 中已有 field, 按 field name 前缀匹配
        var fieldToMethod = {};
        for (var k in methodPrimaryFields) {
            var fields = methodPrimaryFields[k];
            fields.forEach(function(f) {
                if (f) fieldToMethod[f] = k;
            });
        }
        // 补充 methodMeta 中所有 output 字段映射（用于 tooltip lookup）
        var mm = self.methodMeta || {};
        for (var mn in mm) {
            var mFields = mm[mn].output || [];
            mFields.forEach(function(f) {
                if (f && !fieldToMethod[f]) fieldToMethod[f] = mn;
            });
        }

        var totalShares = data.total_shares; // 亿股 (来自 StockMaster)
        var price = data.price;
        if (totalShares && price) {
            data._current_mcap_yi = (price * totalShares / 1e8).toFixed(1);
            // 实际上 price = mcap_yi * 1e8 / total_shares, 所以 mcap_yi = price * total_shares / 1e8
            data._current_mcap_yi = (price * totalShares / 1e8).toFixed(1);
        }

        // ── 构建分组数据 ──
        var groups = {};
        catConfig.forEach(function(c) { groups[c.key] = { items: [], label: c.label, badge: c.badge, defaultOpen: c.defaultOpen }; });

        // 遍历 data 中的所有字段, 按 field → method → category 分组
        var fieldCats = {
            'pe_percentile':'relative', 'pe_median':'relative', 'pe_min':'relative', 'pe_max':'relative', 'pe_status':'relative',
            'pb_percentile':'relative', 'pb_median':'relative', 'pb_min':'relative', 'pb_max':'relative', 'pb_status':'relative',
            'ps_percentile':'relative', 'ps_ttm':'relative', 'ps_status':'relative',
            'peg_ratio':'relative', 'peg_verdict':'relative',
            'fcf_yield_pct':'relative', 'fcf_est_yi':'relative', 'implied_value':'relative',
            'ev_yi':'relative', 'ic_yi':'relative', 'ev_ic_ratio':'relative', 'ev_ic_verdict':'relative',
            'industry_pe_median':'advanced', 'premium_pct':'advanced', 'industry_verdict':'advanced',
            'adjusted_pe':'advanced', 'quality_detail':'advanced', 'quality_bonus_pct':'advanced',
            'roic_spread_pct':'advanced', 'wacc_est':'advanced', 'value_creation_label':'advanced',
            'bull_target':'absolute', 'base_target':'absolute', 'bear_target':'absolute', 'weighted_target':'absolute',
            'upside_pct':'absolute', 'downside_pct':'absolute', 'asymmetry':'absolute',
            'graham_number':'absolute', 'graham_vs_price_pct':'absolute', 'safety_margin_pct':'absolute',
            'rim_value':'absolute', 'rim_vs_price_pct':'absolute',
            'ddm_value':'absolute', 'ddm_vs_price_pct':'absolute', 'dps_est':'absolute', 'implied_growth_rate':'absolute',
            'nav_per_share':'absolute', 'nav_vs_price_pct':'absolute',
            'three_stage_value':'dynamic', 'three_stage_upside':'dynamic',
            'gm_target_price':'dynamic', 'gm_upside':'dynamic',
            'scissor_target_price':'dynamic', 'scissor_upside':'dynamic',
            'growth_peg_target_price':'dynamic', 'growth_peg_upside':'dynamic',
            'dol_target_price':'dynamic', 'dol_upside':'dynamic',
            'rgv_target_price':'dynamic', 'rgv_upside':'dynamic',
            'rgf_target_price':'dynamic', 'rgf_upside':'dynamic',
        };

        // 友好字段名
        var fieldLabels = {
            pe_percentile:'PE百分位', pe_median:'PE中位数', pe_min:'PE最低', pe_max:'PE最高', pe_status:'PE状态',
            pb_percentile:'PB百分位', pb_median:'PB中位数', pb_min:'PB最低', pb_max:'PB最高', pb_status:'PB状态',
            ps_percentile:'PS百分位', ps_ttm:'PS(TTM)', ps_status:'PS状态',
            peg_ratio:'PEG', peg_verdict:'PEG判断',
            fcf_yield_pct:'FCF收益率', fcf_est_yi:'FCF估算(亿)', implied_value:'隐含价值',
            ev_yi:'EV(亿)', ic_yi:'IC(亿)', ev_ic_ratio:'EV/IC', ev_ic_verdict:'EV/IC判断',
            industry_pe_median:'行业PE中位数', premium_pct:'行业溢价', industry_verdict:'行业判断',
            adjusted_pe:'调整后PE', quality_detail:'质量细节', quality_bonus_pct:'质量溢价',
            roic_spread_pct:'ROIC-WACC', wacc_est:'WACC', value_creation_label:'价值创造',
            bull_target:'乐观', base_target:'基准', bear_target:'悲观', weighted_target:'加权',
            upside_pct:'上行空间', downside_pct:'下行空间', asymmetry:'非对称性',
            graham_number:'格雷厄姆', graham_vs_price_pct:'距格雷厄姆', safety_margin_pct:'安全边际',
            rim_value:'剩余收益', rim_vs_price_pct:'RIM vs价',
            ddm_value:'DDM价值', ddm_vs_price_pct:'DDM vs价', dps_est:'DPS(估)', implied_growth_rate:'隐含增速',
            nav_per_share:'NAV/股', nav_vs_price_pct:'NAV vs价',
            three_stage_value:'三阶段增长', three_stage_upside:'三阶段上行',
            gm_target_price:'毛利率调整', gm_upside:'毛利率上行',
            scissor_target_price:'剪刀差框架', scissor_upside:'剪刀差上行',
            growth_peg_target_price:'增长PEG', growth_peg_upside:'增长PEG上行',
            dol_target_price:'经营杠杆调整', dol_upside:'经营杠杆上行',
            rgv_target_price:'风险调整NPV', rgv_upside:'rNPV上行',
            rgf_target_price:'营收框架', rgf_upside:'营收框架上行',
        };

        // 字段说明 (点击 (?) 显示) — 在 Valuation 上共享
        var fh = Valuation.fieldHelp || {};

        // 字段单位
        var fieldUnits = {};

        // 估值 method → display label
        var methodLabels = {
            pe_percentile:'PE百分位', pb_percentile:'PB百分位', ps_valuation:'PS估值',
            peg_analysis:'PEG', fcf_yield:'FCF收益率', ev_ic:'EV/IC',
            industry_premium:'行业溢价', quality_adjusted:'质量调整', roic_spread:'ROIC-WACC',
            graham_number:'格雷厄姆', residual_income:'剩余收益', gordon_growth:'DDM',
            net_asset_value:'NAV', scenario_estimate:'情景加权',
            three_stage_growth:'三阶段增长', gross_margin_adjustment:'毛利率调整',
            scissor_gap_inflection:'剪刀差', growth_adjusted_peg:'增长调整PEG',
            dol_adjusted_valuation:'经营杠杆', risk_adjusted_npv:'风险调整NPV',
            revenue_growth_framework:'营收框架',
        };

        // 组织字段到分组
        var processed = {};
        for (var key in data) {
            if (key === 'stock_code' || key === 'stock_name' || key === 'trade_date' || key === 'price' ||
                key === 'message' || key === 'valuation_score' || key === 'valuation_verdict' || key === 'valuation_summary' ||
                key === 'total_shares' || key === 'industry' || key === '_current_mcap_yi') continue;

            var cat = fieldCats[key];
            if (!cat) continue;
            if (!groups[cat]) continue;

            var v = data[key];
            if (v == null) continue; // 跳过 null 值

            var label = fieldLabels[key] || key;
            // 取单位
            var unit = '?';
            if (key.indexOf('percentile') >= 0 || key.indexOf('pct') >= 0 || key.indexOf('yield') >= 0 || key.indexOf('bonus') >= 0 || key.indexOf('margin') >= 0 || key.indexOf('upside') >= 0 || key.indexOf('downside') >= 0 || key.indexOf('premium') >= 0 || key.indexOf('vs_price') >= 0) unit = '%';
            else if (key.indexOf('value') >= 0 || key.indexOf('_number') >= 0 || key.indexOf('target') >= 0 || key.indexOf('_price') >= 0) unit = '¥';
            else if (key.indexOf('ratio') >= 0 || key.indexOf('peg') >= 0 || key.indexOf('_pe') >= 0 || key.indexOf('_pb') >= 0 || key.indexOf('_ps') >= 0) unit = '倍';
            else if (key.indexOf('_yi') >= 0) unit = '亿元';

            groups[cat].items.push({
                field: key,
                label: label,
                value: v,
                unit: unit,
                judge: self._judgeValue(v, key),
            });
        }

        // ── 渲染 ──
        var html = '';

        // 头部信息栏
        html += '<div class="info-header" style="display:flex;justify-content:space-between;align-items:center;padding:6px 10px;background:rgba(255,255,255,0.02);border-radius:6px;margin-bottom:6px;">';
        html += '<div>';
        html += '<span style="color:var(--accent-blue);font-weight:600;font-size:15px;">' + self.esc(displayName) + '</span>';
        if (data.trade_date) html += '<span style="color:var(--text-micro);margin-left:8px;font-size:10px;">估值日: ' + data.trade_date + '</span>';
        html += '<div style="font-size:11px;color:var(--text-dim);margin-top:2px;">';
        html += '价格: <b style="color:#fff;">¥' + self._v(price, 2) + '</b>';
        if (data._current_mcap_yi) html += ' | 总市值: <b style="color:#fff;">' + data._current_mcap_yi + '亿</b>';
        if (data.pe_ttm != null) html += ' | PE: ' + data.pe_ttm;
        if (data.pb != null) html += ' | PB: ' + data.pb;
        if (data.industry) html += ' | ' + self.esc(data.industry);
        html += '</div></div>';

        // 综合评分 + 推荐方法
        html += '<div style="text-align:right;">';
        if (data.valuation_score != null) {
            var sc = data.valuation_score;
            var sv = data.valuation_verdict || '';
            var scColor = sc >= 75 ? 'var(--accent-green)' : (sc >= 55 ? 'var(--accent-gold)' : 'var(--accent-red)');
            html += '<div style="font-size:11px;color:' + scColor + ';font-weight:600;">综合评分: ' + sc + ' (' + sv + ')</div>';
        }
        html += '</div></div>';

        // 评分进度条
        if (data.valuation_score != null) {
            var s = data.valuation_score;
            var barColor = s >= 75 ? 'var(--accent-green)' : (s >= 55 ? 'var(--accent-gold)' : 'var(--accent-red)');
            html += '<div style="height:4px;background:rgba(255,255,255,0.06);border-radius:2px;overflow:hidden;margin-bottom:8px;">';
            html += '<div style="height:100%;width:' + s + '%;background:' + barColor + ';border-radius:2px;transition:width 0.5s;"></div></div>';
        }
        if (data.valuation_summary) {
            html += '<div style="font-size:10px;color:var(--text-micro);margin-bottom:6px;">' + self.esc(data.valuation_summary) + '</div>';
        }

        // 各分组
        catConfig.forEach(function(cfg) {
            var g = groups[cfg.key];
            if (!g || !g.items.length) return;

            var isOpen = cfg.defaultOpen;
            var arrowClass = isOpen ? '' : 'collapsed';
            var bodyClass = isOpen ? '' : 'hidden';

            html += '<div class="val-group">';
            html += '<div class="val-group-header" onclick="Valuation._toggleGroup(this)">';
            html += '<span class="arrow ' + arrowClass + '">&#9660;</span>';
            html += '<span class="badge ' + cfg.badge + '">' + cfg.label + '</span>';
            html += '<span class="count">' + g.items.length + ' 项</span>';
            html += '</div>';
            html += '<div class="val-group-body ' + bodyClass + '">';

            g.items.forEach(function(item) {
                var unit = item.unit;
                var valStr = '';

                if (unit === '¥') {
                    valStr = '¥' + self._v(item.value, 2);
                } else if (unit === '%') {
                    valStr = self._v(item.value, 1) + '%';
                } else if (unit === '倍') {
                    valStr = self._v(item.value, 2) + 'x';
                } else if (unit === '亿元') {
                    valStr = self._v(item.value, 1) + '亿';
                } else {
                    valStr = self._v(item.value, 2);
                }

                html += '<div class="val-method-row">';
                html += '<span class="ml">' + self.esc(item.label) + '</span>';

                // Tooltip icon: click for field meaning
                if (item.field && (fh[item.field] || fieldToMethod[item.field])) {
                    html += '<span class="hlp-icon" onclick="Valuation._showFieldHelp(\'' + item.field + '\')" title="点击查看含义">(?)</span>';
                }
                html += '<span class="mv ' + item.judge.cls + '">' + valStr + '</span>';

                // 对于目标价类字段, 显示预估市值
                if (unit === '¥' && totalShares && item.value != null) {
                    var mcapEst = (parseFloat(item.value) * totalShares / 1e8);
                    if (!isNaN(mcapEst) && mcapEst > 0) {
                        html += '<span class="mcap">~' + mcapEst.toFixed(1) + '亿</span>';
                    } else {
                        html += '<span class="mcap"></span>';
                    }
                } else {
                    html += '<span class="mcap"></span>';
                }

                if (item.judge.label) {
                    html += '<span class="ms ' + item.judge.cls + '">' + item.judge.label + '</span>';
                } else {
                    html += '<span class="ms"></span>';
                }
                html += '</div>';
            });

            html += '</div></div>';
        });

        document.getElementById('val-result').innerHTML = html;
    },

    _toggleGroup: function(headerEl) {
        var arrow = headerEl.querySelector('.arrow');
        var body = headerEl.nextElementSibling;
        if (!arrow || !body) return;
        var isCollapsed = arrow.classList.toggle('collapsed');
        body.classList.toggle('hidden');
    },

    // ── PE Band 仪表盘 (ECharts Gauge) ──
    renderPEBand: function(data) {
        var el = document.getElementById('peband-chart');
        if (!el) return;
        var self = this;

        // 从已有数据中提取百分位信息，避免额外 API 调用
        var pePct = data.pe_percentile;
        var pbPct = data.pb_percentile;
        var psPct = data.ps_percentile;
        var valScore = data.valuation_score;
        var valVerdict = data.valuation_verdict;

        if (pePct == null) {
            document.getElementById('peband-info').textContent = '暂无 PE 百分位数据';
            document.getElementById('peband-help').style.display = 'none';
            return;
        }

        var info = [];
        var peStatus = pePct > 80 ? '高估' : (pePct < 20 ? '低估' : '合理');
        info.push('PE 当前百分位: ' + pePct + '% (' + peStatus + ')');
        if (data.pe_median != null) info.push('PE 中位数: ' + self._v(data.pe_median));
        if (data.pe_min != null) info.push('PE 范围: ' + self._v(data.pe_min) + ' ~ ' + self._v(data.pe_max));
        if (valScore != null) info.push('综合评分: ' + valScore + (valVerdict ? '/' + valVerdict : ''));
        document.getElementById('peband-info').textContent = info.join(' | ');
        document.getElementById('peband-help').style.display = 'block';

        if (typeof echarts !== 'undefined' && pePct != null) {
            try {
                if (self._peChart) self._peChart.dispose();
                self._peChart = echarts.init(el);
                self._peChart.setOption({
                    series: [{
                        type: 'gauge',
                        startAngle: 180, endAngle: 0,
                        min: 0, max: 100,
                        center: ['50%','60%'], radius: '80%',
                        axisLine: {
                            lineStyle: { width: 12, color: [
                                [0.2, '#2ed573'], [0.8, '#ffa502'], [1, '#ff4757']
                            ]}
                        },
                        pointer: { length: '50%', width: 4 },
                        axisTick: { distance: -8 },
                        splitLine: { distance: -10, length: 8 },
                        detail: {
                            formatter: function(value) {
                                return value + '%\nPE 百分位';
                            },
                            fontSize: 14, color: '#fff', offsetCenter: [0, 30]
                        },
                        title: { offsetCenter: [0, 55], fontSize: 11, color: '#999' },
                        data: [{ value: Math.round(pePct), name: peStatus }]
                    }]
                });
                window.addEventListener('resize', function() {
                    if (self._peChart) self._peChart.resize();
                });
            } catch(e) { console.error('PE Band chart error:', e); }
        }
    },

    // ── 方法详情表 ──
    renderDetails: function(data) {
        if (!data || data.message) {
            document.getElementById('val-details-content').innerHTML = '<div style="color:var(--text-dim);">暂无数据</div>';
            return;
        }
        var html = '<table class="v-table"><thead><tr><th>字段</th><th>值</th><th>判断</th></tr></thead><tbody>';
        var skip = ['stock_code','stock_name','trade_date','price','valuation_summary'];
        var self = this;

        var fieldLabels = {
            pe_percentile:'PE百分位', pe_median:'PE中位数', pe_min:'PE最小值',
            pe_max:'PE最大值', pe_status:'PE状态',
            pb_percentile:'PB百分位', pb_median:'PB中位数', pb_status:'PB状态',
            ps_ttm:'PS(TTM)', ps_percentile:'PS百分位', ps_status:'PS状态',
            peg_ratio:'PEG', peg_verdict:'PEG判断',
            fcf_yield_pct:'FCF收益率', fcf_est_yi:'FCF估算(亿)', implied_value:'隐含价值(¥)',
            ev_yi:'EV(亿)', ic_yi:'IC(亿)', ev_ic_ratio:'EV/IC', ev_ic_verdict:'EV/IC判断',
            graham_number:'格雷厄姆数(¥)', graham_vs_price_pct:'距格雷厄姆价%', safety_margin_pct:'安全边际%',
            rim_value:'剩余收益价值(¥)', rim_vs_price_pct:'RIM vs 价%',
            ddm_value:'DDM价值(¥)', ddm_vs_price_pct:'DDM vs 价%', dps_est:'DPS估算', implied_growth_rate:'隐含增长率',
            nav_per_share:'NAV/股(¥)', nav_vs_price_pct:'NAV vs 价%',
            industry_pe_median:'行业PE中位数', premium_pct:'行业溢价%', industry_verdict:'行业判断',
            adjusted_pe:'调整后PE', quality_detail:'质量详情', quality_bonus_pct:'质量溢价%',
            bull_target:'乐观目标(¥)', base_target:'基准目标(¥)', bear_target:'悲观目标(¥)',
            weighted_target:'加权目标(¥)', upside_pct:'上行空间%', downside_pct:'下行空间%', asymmetry:'非对称性',
            roic_spread_pct:'ROIC-WACC%', wacc_est:'WACC估算', value_creation_label:'价值创造',
            valuation_score:'综合评分', valuation_verdict:'综合判断',
            industry:'行业',
            three_stage_value:'三阶段增长(¥)', three_stage_upside:'三阶段上行%',
            gm_target_price:'毛利率调整(¥)', gm_upside:'毛利率上行%',
            scissor_target_price:'剪刀差目标(¥)', scissor_upside:'剪刀差上行%',
            growth_peg_target_price:'增长PEG(¥)', growth_peg_upside:'增长PEG上行%',
            dol_target_price:'经营杠杆调整(¥)', dol_upside:'经营杠杆上行%',
            rgv_target_price:'风险调整NPV(¥)', rgv_upside:'rNPV上行%',
            rgf_target_price:'营收框架(¥)', rgf_upside:'营收框架上行%',
        };

        for (var k in data) {
            if (skip.indexOf(k) >= 0) continue;
            if (data[k] == null) continue;
            var v = data[k];
            var label = fieldLabels[k] || k;
            var cls = this.statusClass(typeof v === 'string' ? v : '');
            html += '<tr><td style="color:#ccc;">' + this.esc(label) + '</td>';
            html += '<td style="font-family:var(--font-mono);">' + this.esc(String(v)) + '</td>';
            html += '<td class="' + cls + '">' + (cls ? (cls === 'status-under' ? '✓' : cls === 'status-over' ? '⚠' : '●') : '') + '</td></tr>';
        }
        html += '</tbody></table>';
        document.getElementById('val-details-content').innerHTML = html;
    },

    // ── 多股对比 ──
    runCompare: function() {
        var codeStr = document.getElementById('cmp-codes').value.trim();
        if (!codeStr) { Modal.alert('提示', '请输入股票代码'); return; }
        var codeList = codeStr.split(',').map(function(c) { return c.trim(); }).filter(function(c) { return c; });
        if (codeList.length < 2) { Modal.alert('提示', '至少输入 2 个股票代码'); return; }

        var el = document.getElementById('cmp-result');
        el.innerHTML = '<div style="color:var(--text-dim);">加载中...</div>';
        var self = this;

        fetch(API_BASE + '/quant/valuation/compare', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({codes: codeList})
        })
        .then(function(r) { return r.json(); })
        .then(function(d) {
            if (!d.success) throw new Error(d.error);
            var rows = d.data || [];
            if (!rows.length) {
                el.innerHTML = '<div style="color:var(--text-dim);">暂无对比数据（请先计算各股票估值）</div>';
                return;
            }

            var keyFields = ['price','pe_percentile','pb_percentile','peg_ratio','fcf_yield_pct',
                'graham_number','weighted_target','valuation_score','valuation_verdict'];

            var html = '<table class="v-table"><thead><tr><th>代码</th>';
            keyFields.forEach(function(k) {
                var fl = {price:'股价',pe_percentile:'PE分位',pb_percentile:'PB分位',
                    peg_ratio:'PEG',fcf_yield_pct:'FCF Yield',
                    graham_number:'格雷厄姆',weighted_target:'加权目标',
                    valuation_score:'评分',valuation_verdict:'判断'}[k] || k;
                html += '<th>' + fl + '</th>';
            });
            html += '</tr></thead><tbody>';
            rows.forEach(function(r) {
                html += '<tr><td style="color:var(--accent-blue);font-weight:600;">' + self.esc(r.stock_code) + '</td>';
                keyFields.forEach(function(k) {
                    var v = r[k];
                    var cls = self.statusClass(typeof v === 'string' ? v : '');
                    var display = (v != null) ? (typeof v === 'number' ? v.toFixed(2) : self.esc(String(v))) : '-';
                    html += '<td class="' + cls + '">' + display + '</td>';
                });
                html += '</tr>';
            });
            html += '</tbody></table>';

            var scoreRow = rows.filter(function(r) { return r.valuation_score != null; });
            if (scoreRow.length > 1 && typeof echarts !== 'undefined') {
                html += '<div id="cmp-chart" style="height:200px;margin-top:8px;"></div>';
                el.innerHTML = html;
                try {
                    var chart = echarts.init(document.getElementById('cmp-chart'));
                    chart.setOption({
                        xAxis: { type: 'category', data: scoreRow.map(function(r){return r.stock_code;}), axisLabel: {color:'#999'} },
                        yAxis: { type: 'value', min: 0, max: 100, axisLabel: {color:'#999'} },
                        series: [{
                            type: 'bar',
                            data: scoreRow.map(function(r){
                                var s = r.valuation_score;
                                var color = s >= 75 ? '#2ed573' : (s >= 55 ? '#ffa502' : '#ff4757');
                                return {value: s, itemStyle: {color: color}};
                            }),
                            barWidth: 30,
                            label: {show: true, position: 'top', color:'#ccc', formatter: function(p){return p.value;}}
                        }],
                        grid: {top: 20, bottom: 20, left: 40, right: 10}
                    });
                } catch(e) { console.error('Compare chart error:', e); }
            } else {
                el.innerHTML = html;
            }
        })
        .catch(function(e) {
            document.getElementById('cmp-result').innerHTML = '<div style="color:var(--accent-red);">错误: ' + e.message + '</div>';
        });
    },
};

// ═══ 字段级别含义说明 (点击 ? 时显示) ═══
Valuation.fieldHelp = {
    // ── PE/PB/PS 百分位 ──
    pe_percentile:'PE百分位=当前市盈率在近3年历史中的位置。>80%=比80%时间贵(高估区), <20%=比80%时间便宜(低估区)',
    pe_median:'近3年PE历史中位数, 用于衡量当前PE在历史中处于什么水平',
    pe_min:'近3年PE历史最低值',
    pe_max:'近3年PE历史最高值',
    pe_status:'PE估值状态: 高估(百分位>80%)/合理/低估(<20%)',
    pb_percentile:'PB百分位=当前市净率在近3年历史中的位置。>80%=高估, <20%=低估',
    pb_median:'近3年PB历史中位数',
    pb_min:'近3年PB历史最低值',
    pb_max:'近3年PB历史最高值',
    pb_status:'PB估值状态: 高估/合理/低估',
    ps_percentile:'PS百分位=当前市销率在近3年历史中的位置。适合尚未盈利公司的估值参考',
    ps_ttm:'市销率(TTM)=总市值/近12个月营收。营收导向的估值指标',
    ps_status:'PS估值状态: 高估/合理/低估',
    peg_ratio:'PEG=PE/净利润增速。PEG<1=低估, PEG>2=可能高估, 考虑了成长性的PE修正',
    peg_verdict:'基于PEG比率对估值水平的定性判断',
    // ── FCF ──
    fcf_yield_pct:'FCF收益率=自由现金流/总市值。>5%可能低估, <2%可能高估, 类似股息率但基于现金流',
    fcf_est_yi:'估算年度自由现金流(亿元)。自由现金流=经营现金流-资本支出',
    implied_value:'FCF折现隐含价值(元/股)。将未来自由现金流折现后估算的每股内在价值',
    // ── EV/IC ──
    ev_yi:'企业价值EV(亿元)=总市值+有息负债-现金。反映公司整体市场价值(含负债), 比市值更全面',
    ic_yi:'投入资本IC(亿元)=总资产-无息负债。公司运营中实际占用的资本总额',
    ev_ic_ratio:'EV/IC倍率=企业价值/投入资本。>2可能高估, <1可能低估, 类似PB的替代指标',
    ev_ic_verdict:'基于EV/IC比率对估值水平的定性判断',
    // ── 行业对比 ──
    industry_pe_median:'同行业所有可比公司PE的中位值, 用于横向对比判断贵贱',
    premium_pct:'行业溢价=(当前PE-行业PE中位数)/行业PE中位数。正值=比行业贵, 负值=比行业便宜',
    industry_verdict:'基于行业PE对比的定性判断结论',
    // ── 质量调整 ──
    adjusted_pe:'质量调整后PE=原始PE×(1-质量溢价)。考虑了公司质量修正后的PE',
    quality_detail:'质量评分细节: 盈利质量、治理水平等的综合评分明细',
    quality_bonus_pct:'质量溢价(%)=质量评分带来的估值溢价比例。优质公司可享受更高PE',
    roic_spread_pct:'ROIC-WACC价差=投入资本回报率-加权平均资本成本。正值=公司创造价值, 负值=毁灭价值',
    wacc_est:'加权平均资本成本WACC(%), 公司融资的综合成本, 用于估值折现',
    value_creation_label:'价值创造判断: ROIC是否大于WACC, 公司是否为股东创造价值',
    // ── 三情景目标价 ──
    bull_target:'乐观情景目标价(元/股), 基于最有利的行业/公司假设',
    base_target:'基准情景目标价(元/股), 基于最可能的中性假设',
    bear_target:'悲观情景目标价(元/股), 基于最不利的假设条件',
    weighted_target:'加权目标价(元/股)=三种情景按概率加权后的期望值, 是综合参考价',
    upside_pct:'上行空间=(加权目标价-当前价)/当前价。正值=预期还有上涨空间',
    downside_pct:'下行空间=(当前价-悲观目标价)/当前价。衡量最坏情况下可能下跌的幅度',
    asymmetry:'非对称性=上行空间/下行空间。>1表示上行潜力大于下行风险',
    // ── 格雷厄姆 ──
    graham_number:'格雷厄姆数(元/股)=√(22.5×每股收益×每股净资产)。价值投资鼻祖的保守估值参考价',
    graham_vs_price_pct:'距格雷厄姆=(格雷厄姆数-当前价)/当前价。正值=股价低于格雷厄姆估值',
    safety_margin_pct:'安全边际=(格雷厄姆数-当前价)/格雷厄姆数。格雷厄姆投资体系的核心风控指标',
    // ── 剩余收益 ──
    rim_value:'剩余收益模型估值(元/股)=账面净资产+未来剩余收益的现值。基于会计数据的估值模型',
    rim_vs_price_pct:'RIM偏离度=(RIM估值-当前价)/当前价。正值=股价低于RIM估值',
    // ── DDM ──
    ddm_value:'DDM戈登模型估值(元/股)=预期股息/(折现率-增长率)。适用于稳定派息的成熟公司',
    ddm_vs_price_pct:'DDM偏离度=(DDM估值-当前价)/当前价。正值=股价低于DDM估值',
    dps_est:'每股股息估算(元), 基于历史派息率和盈利预测估计的分红金额',
    implied_growth_rate:'隐含增长率(%), 从当前股价反推的市场对未来增长的预期。越高=市场期待越高',
    // ── NAV ──
    nav_per_share:'NAV每股净资产(元)=净资产/总股本。相当于公司清算时每股可分配的价值',
    nav_vs_price_pct:'NAV偏离度=(NAV-当前价)/当前价。正值=股价低于每股净资产, 破净状态',
    // ── 动态模型 ──
    three_stage_value:'三阶段增长模型估值(元/股): 高增长→过渡→永续增长三段式折现',
    three_stage_upside:'三阶段估值上行空间=(估值-当前价)/当前价',
    gm_target_price:'毛利率调整估值(元/股), 基于毛利率与同业比较的估值修正',
    gm_upside:'毛利率估值上行空间(%)',
    scissor_target_price:'剪刀差框架估值(元/股), 基于营收增速与利润率剪刀差的分析',
    scissor_upside:'剪刀差估值上行空间(%)',
    growth_peg_target_price:'增长调整PEG估值(元/股), PEG结合增长持续性的修正估值',
    growth_peg_upside:'增长PEG上行空间(%)',
    dol_target_price:'经营杠杆调整估值(元/股), 考虑固定成本杠杆效应对估值的影响',
    dol_upside:'经营杠杆估值上行空间(%)',
    rgv_target_price:'rNPV风险调整估值(元/股), 按成功概率调整后的净现值',
    rgv_upside:'rNPV上行空间(%)',
    rgf_target_price:'营收增长框架估值(元/股), 从营收驱动因素推算的估值',
    rgf_upside:'营收框架上行空间(%)',
};


