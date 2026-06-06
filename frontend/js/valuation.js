/**
 * 定量估值前端模块 (Valuation) — V1.0
 *
 * 功能:
 *   - 估值方法注册表展示 (4 类分组)
 *   - 单股票估值计算 + 四象限仪表盘
 *   - PE/PB 百分位仪表盘图 (ECharts gauge)
 *   - 全部输出字段详情表
 *   - 多股票估值对比
 *
 * 命名空间: window.Valuation
 */
window.Valuation = {
    currentTab: 'dashboard',
    stockCode: '',
    lastResult: null,

    // ── 初始化 ──
    init: function() {
        this.loadMethodList();
        // 绑定回车键
        var codeInput = document.getElementById('val-code');
        if (codeInput) {
            codeInput.addEventListener('keyup', function(e) {
                if (e.key === 'Enter') Valuation.run();
            });
        }
    },

    // ── 工具 ──
    esc: function(s) {
        if (!s) return '';
        return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    },

    _v: function(v, decimals) {
        if (v == null) return '?';
        decimals = decimals || 2;
        if (typeof v === 'number') return v.toFixed(decimals);
        return v;
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
                        html += '<div class="name">' + Valuation.esc(m.label||m.name) + '</div>';
                        html += '<div class="desc">' + Valuation.esc((m.description||'').substring(0,60)) + '</div>';
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

        // 从注册表获取方法描述
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
                html += '<h4 style="color:#fff;">' + Valuation.esc(method.label||method.name) + '</h4>';
                html += '<p>' + Valuation.esc(method.description||'') + '</p>';
                html += '<table class="v-table"><tbody>';
                html += '<tr><td>识别名</td><td><code>' + Valuation.esc(method.name) + '</code></td></tr>';
                html += '<tr><td>类别</td><td>' + Valuation.esc(method.category) + '</td></tr>';
                html += '<tr><td>输出字段</td><td>' + (method.output||[]).map(function(f) {
                    var isText = (method.text_output||[]).indexOf(f) >= 0;
                    return '<code>' + f + '</code>' + (isText ? ' <span class="badge" style="color:var(--accent-gold);">text</span>' : '');
                }).join(', ') + '</td></tr>';
                html += '<tr><td>依赖字段</td><td>' + (method.requires||[]).map(function(f) { return '<code>' + f + '</code>'; }).join(', ') + '</td></tr>';
                html += '<tr><td>需日线历史</td><td>' + (method.requires_market_data ? '是' : '否') + '</td></tr>';
                html += '<tr><td>需财务数据</td><td>' + (method.requires_financial_data ? '是' : '否') + '</td></tr>';
                html += '<tr><td>参数</td><td>' + (method.params ? JSON.stringify(method.params) : '-') + '</td></tr>';
                html += '</tbody></table>';

                // 如果有当前数据, 显示该方法的实际输出
                if (Valuation.lastResult) {
                    var hasOutput = false;
                    var outHtml = '<h5 style="color:#ccc;margin-top:12px;">当前计算结果</h5><table class="v-table"><thead><tr><th>字段</th><th>值</th></tr></thead><tbody>';
                    (method.output||[]).forEach(function(f) {
                        if (Valuation.lastResult[f] != null) {
                            hasOutput = true;
                            outHtml += '<tr><td>' + f + '</td><td style="font-family:var(--font-mono);">' + Valuation.esc(String(Valuation.lastResult[f])) + '</td></tr>';
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

        // 切到仪表盘时如果有数据, 重新拉伸可能的 echarts
        if (tab === 'dashboard' && this.lastResult) {
            setTimeout(function() { /* resize any chart if needed */ }, 100);
        }
    },

    // ── 主计算入口 ──
    run: function() {
        var code = document.getElementById('val-code').value.trim();
        if (!code) { Modal.alert('提示', '请输入股票代码'); return; }
        this.stockCode = code;
        var mode = document.getElementById('val-mode').value;
        var statusEl = document.getElementById('val-status');
        var btn = document.getElementById('btn-val');
        statusEl.textContent = '计算中...';
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 计算中';

        // Step 1: 触发计算
        fetch(API_BASE + '/quant/valuation/compute/' + code + '?mode=' + mode, { method: 'POST' })
            .then(function(r) { return r.json(); })
            .then(function(d) {
                if (!d.success) throw new Error(d.error || '计算失败');
                // Step 2: 查询结果
                return fetch(API_BASE + '/quant/valuation/' + code);
            })
            .then(function(r) { return r.json(); })
            .then(function(d) {
                if (!d.success) throw new Error(d.error || '查询失败');
                Valuation.lastResult = d.data;
                Valuation.renderDashboard(d.data);
                Valuation.renderPEBand(d.data);
                // 如果当前在详情 tab, 刷新详情
                if (Valuation.currentTab === 'details') {
                    // re-show whatever method detail was showing
                }
                // 切到仪表盘
                Valuation.switchTab('dashboard');
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

    // ── 渲染估值仪表盘 (四象限) ──
    renderDashboard: function(data) {
        if (!data || data.message) {
            document.getElementById('val-empty').style.display = 'flex';
            document.getElementById('val-result').style.display = 'none';
            return;
        }
        document.getElementById('val-empty').style.display = 'none';
        document.getElementById('val-result').style.display = 'flex';

        var code = this.stockCode;
        var html = '';

        // 基础信息栏
        html += '<div style="display:flex;justify-content:space-between;align-items:center;padding:6px 0;">';
        html += '<div><span style="color:var(--accent-blue);font-weight:600;font-size:14px;">' + this.esc(code) + '</span>';
        html += '<span style="color:var(--text-dim);margin-left:8px;font-size:11px;">价格: ¥' + this._v(data.price) + '</span>';
        html += '<span style="color:var(--text-dim);margin-left:8px;font-size:11px;">PE: ' + this._v(data.pe_ttm) + ' | PB: ' + this._v(data.pb) + '</span>';
        if (data.industry) {
            html += '<span style="color:var(--text-dim);margin-left:8px;font-size:11px;">行业: ' + this.esc(data.industry) + '</span>';
        }
        html += '</div>';
        html += '<div style="font-size:11px;">';
        if (data.valuation_score != null) {
            var sc = data.valuation_score;
            var sv = data.valuation_verdict || '';
            var scColor = sc >= 75 ? 'var(--accent-green)' : (sc >= 55 ? 'var(--accent-gold)' : 'var(--accent-red)');
            html += '<span style="padding:4px 12px;border-radius:4px;background:' + scColor + '20;color:' + scColor + ';font-weight:600;">综合评分: ' + sc + ' (' + sv + ')</span>';
        }
        html += '</div></div>';

        // 四象限仪表盘
        html += '<div class="dashboard-grid">';

        // 1. 估值百分位 (PE/PB/PS)
        html += '<div class="v-metric-card">';
        html += '<div class="label"><i class="fas fa-percent"></i> 估值百分位 &nbsp;';
        html += '<span style="font-size:9px;color:var(--text-micro);">越低越低估</span></div>';
        html += '<div style="display:flex;gap:10px;margin-top:4px;">';
        ['pe_percentile','pb_percentile','ps_percentile'].forEach(function(k) {
            var v = data[k];
            var label = {pe_percentile:'PE',pb_percentile:'PB',ps_percentile:'PS'}[k];
            if (v == null) return;
            var cls = v > 80 ? 'status-over' : (v < 20 ? 'status-under' : 'status-fair');
            var statusText = v > 80 ? '⚠偏贵' : (v < 20 ? '✓便宜' : '●合理');
            html += '<div style="text-align:center;"><span style="font-size:10px;color:var(--text-micro);">' + label + '</span>';
            html += '<br><span class="' + cls + '" style="font-size:18px;font-weight:700;">' + v + '%</span>';
            html += '<br><span class="' + cls + '" style="font-size:9px;">' + statusText + '</span></div>';
        });
        html += '</div></div>';

        // 2. 目标价对比 (多方法)
        html += '<div class="v-metric-card">';
        html += '<div class="label"><i class="fas fa-crosshairs"></i> 目标价 &nbsp;';
        html += '<span style="font-size:9px;color:var(--text-micro);">↑安全边际正值</span></div>';
        html += '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:4px;">';
        var price = data.price || 0;
        var targets = [
            {k:'graham_number', l:'格雷厄姆'},
            {k:'rim_value', l:'剩余收益'},
            {k:'ddm_value', l:'DDM'},
            {k:'weighted_target', l:'三情景加权'},
            {k:'nav_per_share', l:'NAV'},
        ];
        targets.forEach(function(t) {
            var v = data[t.k];
            if (v == null) return;
            var diff = price > 0 ? ((v - price) / price * 100).toFixed(1) : '?';
            var cls = diff > 0 ? 'status-under' : 'status-over';
            html += '<div style="text-align:center;"><span style="font-size:9px;color:var(--text-micro);">' + t.l + '</span>';
            html += '<br><span style="font-size:13px;font-weight:600;">¥' + v + '</span>';
            html += '<br><span class="' + cls + '" style="font-size:9px;">' + (diff > 0 ? '+' : '') + diff + '%</span></div>';
        });
        html += '</div></div>';

        // 3. 专业指标
        html += '<div class="v-metric-card">';
        html += '<div class="label"><i class="fas fa-chart-bar"></i> 专业指标</div>';
        html += '<div style="display:flex;gap:10px;margin-top:4px;flex-wrap:wrap;">';
        var prof = [
            {k:'peg_ratio', l:'PEG', f:function(v){return v.toFixed(2)}},
            {k:'fcf_yield_pct', l:'FCF Yield', f:function(v){return v.toFixed(1)+'%'}},
            {k:'roic_spread_pct', l:'ROIC-WACC', f:function(v){return v.toFixed(1)+'%'}},
            {k:'ev_ic_ratio', l:'EV/IC', f:function(v){return v.toFixed(2)}},
            {k:'implied_value', l:'隐含价值', f:function(v){return '¥'+v.toFixed(2)}},
        ];
        prof.forEach(function(t) {
            var v = data[t.k];
            if (v == null) return;
            html += '<div style="text-align:center;"><span style="font-size:9px;color:var(--text-micro);">' + t.l + '</span>';
            html += '<br><span style="font-size:14px;font-weight:600;">' + t.f(v) + '</span></div>';
        });
        html += '</div></div>';

        // 4. 安全边际分析
        html += '<div class="v-metric-card">';
        html += '<div class="label"><i class="fas fa-shield-alt"></i> 安全边际分析</div>';
        html += '<div style="display:flex;gap:12px;margin-top:4px;">';
        var safetyItems = [
            {k:'safety_margin_pct', l:'格雷厄姆', u:'%'},
            {k:'nav_vs_price_pct', l:'NAV vs 价', u:'%'},
            {k:'graham_vs_price_pct', l:'距格雷厄姆', u:'%'},
            {k:'up_side_pct', l:'情景上行', u:'%'},
            {k:'down_side_pct', l:'情景下行', u:'%'},
        ];
        safetyItems.forEach(function(t) {
            var v = data[t.k];
            if (v == null) return;
            var cls = v > 0 ? 'status-under' : 'status-over';
            html += '<div style="text-align:center;"><span style="font-size:9px;color:var(--text-micro);">' + t.l + '</span>';
            html += '<br><span class="' + cls + '" style="font-size:14px;font-weight:600;">' + (v > 0 ? '+' : '') + v.toFixed(1) + t.u + '</span></div>';
        });
        html += '</div></div>';

        html += '</div>';

        // 估值健康评分进度条
        if (data.valuation_score != null) {
            var s = data.valuation_score;
            var barColor = s >= 75 ? 'var(--accent-green)' : (s >= 55 ? 'var(--accent-gold)' : 'var(--accent-red)');
            html += '<div style="margin-top:4px;">';
            html += '<div style="font-size:10px;color:var(--text-dim);margin-bottom:2px;">综合估值健康度 (' + data.valuation_verdict + ')</div>';
            html += '<div style="height:6px;background:rgba(255,255,255,0.06);border-radius:3px;overflow:hidden;">';
            html += '<div style="height:100%;width:' + s + '%;background:' + barColor + ';border-radius:3px;transition:width 0.5s;"></div></div>';
            html += '<div style="font-size:10px;color:var(--text-micro);margin-top:2px;">' + (data.valuation_summary || '') + '</div></div>';
        }

        // 行情对比信息
        if (data.upside_pct != null || data.weighted_target != null || data.premium_pct != null) {
            html += '<div style="display:flex;gap:10px;font-size:10px;color:var(--text-micro);padding-top:2px;border-top:1px solid rgba(255,255,255,0.04);">';
            if (data.weighted_target != null) html += '<span>三情景加权: ¥' + data.weighted_target + '</span>';
            if (data.bull_target != null) html += '<span>乐观: ¥' + data.bull_target + '</span>';
            if (data.bear_target != null) html += '<span>悲观: ¥' + data.bear_target + '</span>';
            if (data.premium_pct != null) {
                var pc = data.premium_pct;
                html += '<span>行业溢价: <span class="' + (pc > 0 ? 'status-over' : 'status-under') + '">' + (pc > 0 ? '+' : '') + pc.toFixed(1) + '%</span></span>';
            }
            html += '</div>';
        }

        document.getElementById('val-result').innerHTML = html;
    },

    // ── PE Band 仪表盘 (ECharts Gauge) ──
    renderPEBand: function(data) {
        var el = document.getElementById('peband-chart');
        if (!el) return;

        fetch(API_BASE + '/quant/valuation/percentile/' + this.stockCode)
            .then(function(r) { return r.json(); })
            .then(function(d) {
                if (!d.success || !d.data) {
                    document.getElementById('peband-info').textContent = '暂无 PE Band 数据';
                    return;
                }
                var info = [];
                var peData = d.data.pe_percentile;
                if (peData) {
                    info.push('PE 当前百分位: ' + peData.current_percentile + '% (' + peData.status + ')');
                    info.push('PE 中位数: ' + Valuation._v(peData.median) + ' | 范围: ' + Valuation._v(peData.min) + ' ~ ' + Valuation._v(peData.max));
                }
                if (d.data.valuation_score != null) {
                    info.push('综合评分: ' + d.data.valuation_score + '/' + d.data.valuation_verdict);
                }
                document.getElementById('peband-info').textContent = info.join(' | ');

                // ECharts 仪表盘 gauge
                if (typeof echarts !== 'undefined' && peData) {
                    try {
                        if (Valuation._peChart) Valuation._peChart.dispose();
                        Valuation._peChart = echarts.init(el);
                        Valuation._peChart.setOption({
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
                                data: [{ value: Math.round(peData.current_percentile||0), name: peData.status||'' }]
                            }]
                        });
                        // 响应式 resize
                        window.addEventListener('resize', function() {
                            if (Valuation._peChart) Valuation._peChart.resize();
                        });
                    } catch(e) { console.error('PE Band chart error:', e); }
                }
            })
            .catch(function(e) {
                document.getElementById('peband-info').textContent = '加载失败';
            });
    },

    // ── 方法详情表 ──
    renderDetails: function(data) {
        if (!data || data.message) {
            document.getElementById('val-details-content').innerHTML = '<div style="color:var(--text-dim);">暂无数据</div>';
            return;
        }
        var html = '<table class="v-table"><thead><tr><th>字段</th><th>值</th><th>判断</th></tr></thead><tbody>';
        var skip = ['stock_code','trade_date','price','valuation_summary'];

        // 定义友好字段名
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

            // 展示关键字段
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
                html += '<tr><td style="color:var(--accent-blue);font-weight:600;">' + Valuation.esc(r.stock_code) + '</td>';
                keyFields.forEach(function(k) {
                    var v = r[k];
                    var cls = Valuation.statusClass(typeof v === 'string' ? v : '');
                    var display = (v != null) ? (typeof v === 'number' ? v.toFixed(2) : Valuation.esc(String(v))) : '-';
                    html += '<td class="' + cls + '">' + display + '</td>';
                });
                html += '</tr>';
            });
            html += '</tbody></table>';

            // 添加评分图
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
