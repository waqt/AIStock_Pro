/**
 * Monte Carlo 仿真面板 — 对任意估值方法做参数不确定性分析
 *
 * 命名空间: window.ValuationSim
 * 依赖: Valuation 命名空间 (switchTab)
 */
window.ValuationSim = {
    /** 已加载的方法注册表 */
    registry: [],
    /** 当前选中的方法 */
    currentMethod: null,
    /** 生成的参数配置 DOM id 列表 */
    paramIds: [],
    /** ECharts 实例 */
    chart: null,

    // ── 初始化 ──
    init: function() {
        this.loadRegistry();
        this.bindEvents();
    },

    // ── 加载注册表 → 填充方法选择器 ──
    loadRegistry: function() {
        var sel = document.getElementById('sim-method');
        if (!sel) return;
        fetch(API_BASE + '/quant/valuation/registry')
            .then(function(r) { return r.json(); })
            .then(function(d) {
                ValuationSim.registry = d.data || [];
                var list = ValuationSim.registry;
                if (!list.length) {
                    sel.innerHTML = '<option value="">暂无方法</option>';
                    return;
                }
                // 按 category 分组
                var catNames = {relative:'相对估值', absolute:'绝对估值', advanced:'进阶估值', composite:'合成指标', dynamic:'动态估值'};
                var groups = {};
                list.forEach(function(m) {
                    var c = m.category || 'other';
                    if (!groups[c]) groups[c] = [];
                    groups[c].push(m);
                });
                var order = ['relative','absolute','advanced','composite','dynamic'];
                var html = '';
                order.forEach(function(c) {
                    if (!groups[c] || !groups[c].length) return;
                    html += '<optgroup label="' + (catNames[c] || c) + '">';
                    groups[c].forEach(function(m) {
                        html += '<option value="' + m.name + '">' + (m.label || m.name) + '</option>';
                    });
                    html += '</optgroup>';
                });
                sel.innerHTML = html;
                // 选中第一个方法并展示参数
                if (list.length) {
                    sel.value = list[0].name;
                    ValuationSim.onMethodChange();
                }
            })
            .catch(function(e) {
                sel.innerHTML = '<option value="">加载失败</option>';
                console.error('[Sim] Registry load failed:', e);
            });
    },

    // ── 方法切换 → 更新目标字段 + 参数配置 ──
    onMethodChange: function() {
        var sel = document.getElementById('sim-method');
        var name = sel ? sel.value : '';
        this.currentMethod = null;
        for (var i = 0; i < this.registry.length; i++) {
            if (this.registry[i].name === name) {
                this.currentMethod = this.registry[i];
                break;
            }
        }
        if (!this.currentMethod) return;

        // 更新目标字段
        this.updateTargetField();
        // 更新参数配置
        this.renderParams();
        // 更新方法说明
        var desc = document.getElementById('sim-method-desc');
        if (desc) {
            desc.textContent = this.currentMethod.description || '';
        }
    },

    // ── 更新目标字段下拉 ──
    updateTargetField: function() {
        var sel = document.getElementById('sim-target');
        if (!sel || !this.currentMethod) return;
        var outputs = this.currentMethod.output || [];
        var textOutputs = this.currentMethod.text_output || [];
        // 只列出数值字段
        var numericFields = outputs.filter(function(f) {
            return textOutputs.indexOf(f) < 0;
        });
        if (!numericFields.length) {
            sel.innerHTML = '<option value="">无非文本字段</option>';
            return;
        }
        // 从 output_fields 获取 label
        var fieldMeta = this.currentMethod.output_fields || {};
        sel.innerHTML = numericFields.map(function(f) {
            var label = fieldMeta[f] ? (fieldMeta[f].meaning || f) : f;
            return '<option value="' + f + '">' + label + '</option>';
        }).join('');
    },

    // ── 渲染参数配置卡片 ──
    renderParams: function() {
        var container = document.getElementById('sim-params');
        if (!container || !this.currentMethod) {
            if (container) container.innerHTML = '<div style="color:var(--text-micro);font-size:10px;">请先选择估值方法</div>';
            return;
        }
        var params = this.currentMethod.params || {};
        var paramKeys = Object.keys(params);
        // 过滤掉控制类参数 (use_continuous_compounding 等)
        var displayKeys = paramKeys.filter(function(k) {
            return k !== 'use_continuous_compounding';
        });
        if (!displayKeys.length) {
            container.innerHTML = '<div style="color:var(--text-micro);font-size:10px;">该方法无可调参数</div>';
            return;
        }
        var fieldMeta = this.currentMethod.output_fields || {};
        var html = displayKeys.map(function(k, idx) {
            var defaultVal = params[k];
            var meta = fieldMeta[k] || {};
            var label = meta.meaning || k;
            return '<div class="sim-param-card" style="background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.06);border-radius:4px;padding:8px;margin-bottom:6px;">' +
                '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">' +
                '<span style="color:#ccc;font-size:11px;font-weight:600;">' + ValuationSim.esc(label) + '</span>' +
                '<code style="font-size:9px;color:var(--text-micro);">' + k + '</code>' +
                '</div>' +
                '<div style="display:flex;gap:4px;flex-wrap:wrap;">' +
                '<select id="sim-dist-' + idx + '" style="background:#000;border:1px solid var(--border-color);color:#fff;padding:3px 6px;border-radius:3px;font-size:10px;" onchange="ValuationSim.onDistChange(' + idx + ')">' +
                '<option value="normal">正态</option>' +
                '<option value="uniform">均匀</option>' +
                '<option value="triangular">三角</option>' +
                '<option value="lognormal">对数正态</option>' +
                '<option value="fixed">固定</option>' +
                '</select>' +
                '<span id="sim-params-' + idx + '">' +
                '<input type="text" id="sim-p-mean-' + idx + '" value="' + defaultVal + '" placeholder="均值" style="width:60px;background:#000;border:1px solid var(--border-color);color:#fff;padding:3px 6px;border-radius:3px;font-size:10px;">' +
                '<input type="text" id="sim-p-std-' + idx + '" value="' + (defaultVal * 0.3).toFixed(1) + '" placeholder="标准差" style="width:55px;background:#000;border:1px solid var(--border-color);color:#fff;padding:3px 6px;border-radius:3px;font-size:10px;">' +
                '</span>' +
                '</div>' +
                '</div>';
        }).join('');
        container.innerHTML = html;
    },

    // ── 分布类型切换 → 更新参数输入框 ──
    onDistChange: function(idx) {
        var sel = document.getElementById('sim-dist-' + idx);
        var dist = sel ? sel.value : 'normal';
        var container = document.getElementById('sim-params-' + idx);
        if (!container) return;

        var html = '';
        switch (dist) {
            case 'normal':
                html = '<input type="text" id="sim-p-mean-' + idx + '" placeholder="均值" style="width:60px;background:#000;border:1px solid var(--border-color);color:#fff;padding:3px 6px;border-radius:3px;font-size:10px;">' +
                    '<input type="text" id="sim-p-std-' + idx + '" placeholder="标准差" style="width:55px;background:#000;border:1px solid var(--border-color);color:#fff;padding:3px 6px;border-radius:3px;font-size:10px;">';
                break;
            case 'uniform':
                html = '<input type="text" id="sim-p-min-' + idx + '" placeholder="下限" style="width:55px;background:#000;border:1px solid var(--border-color);color:#fff;padding:3px 6px;border-radius:3px;font-size:10px;">' +
                    '<input type="text" id="sim-p-max-' + idx + '" placeholder="上限" style="width:55px;background:#000;border:1px solid var(--border-color);color:#fff;padding:3px 6px;border-radius:3px;font-size:10px;">';
                break;
            case 'triangular':
                html = '<input type="text" id="sim-p-min-' + idx + '" placeholder="下限" style="width:50px;background:#000;border:1px solid var(--border-color);color:#fff;padding:3px 6px;border-radius:3px;font-size:10px;">' +
                    '<input type="text" id="sim-p-mode-' + idx + '" placeholder="众数" style="width:50px;background:#000;border:1px solid var(--border-color);color:#fff;padding:3px 6px;border-radius:3px;font-size:10px;">' +
                    '<input type="text" id="sim-p-max-' + idx + '" placeholder="上限" style="width:50px;background:#000;border:1px solid var(--border-color);color:#fff;padding:3px 6px;border-radius:3px;font-size:10px;">';
                break;
            case 'lognormal':
                html = '<input type="text" id="sim-p-mean-' + idx + '" placeholder="均值" style="width:60px;background:#000;border:1px solid var(--border-color);color:#fff;padding:3px 6px;border-radius:3px;font-size:10px;">' +
                    '<input type="text" id="sim-p-std-' + idx + '" placeholder="标准差" style="width:55px;background:#000;border:1px solid var(--border-color);color:#fff;padding:3px 6px;border-radius:3px;font-size:10px;">';
                break;
            case 'fixed':
                html = '<input type="text" id="sim-p-value-' + idx + '" placeholder="固定值" style="width:80px;background:#000;border:1px solid var(--border-color);color:#fff;padding:3px 6px;border-radius:3px;font-size:10px;">';
                break;
        }
        container.innerHTML = html;
    },

    // ── 解析参数配置 → 构造 API 请求 ──
    buildParamDefs: function() {
        if (!this.currentMethod) return null;
        var params = this.currentMethod.params || {};
        var paramKeys = Object.keys(params).filter(function(k) { return k !== 'use_continuous_compounding'; });
        var defs = {};

        paramKeys.forEach(function(k, idx) {
            var sel = document.getElementById('sim-dist-' + idx);
            if (!sel) return;
            var dist = sel.value;
            var def = {dist: dist};

            var getV = function(id) {
                var el = document.getElementById(id);
                if (!el) return null;
                var v = parseFloat(el.value);
                return isNaN(v) ? null : v;
            };

            switch (dist) {
                case 'normal':
                    def.mean = getV('sim-p-mean-' + idx);
                    def.std = getV('sim-p-std-' + idx);
                    break;
                case 'uniform':
                    def.min = getV('sim-p-min-' + idx);
                    def.max = getV('sim-p-max-' + idx);
                    break;
                case 'triangular':
                    def.min = getV('sim-p-min-' + idx);
                    def.mode = getV('sim-p-mode-' + idx);
                    def.max = getV('sim-p-max-' + idx);
                    break;
                case 'lognormal':
                    def.mean = getV('sim-p-mean-' + idx);
                    def.std = getV('sim-p-std-' + idx);
                    break;
                case 'fixed':
                    def.value = getV('sim-p-value-' + idx);
                    break;
            }
            // 去掉 null 字段
            var clean = {};
            for (var dk in def) {
                if (def[dk] != null) clean[dk] = def[dk];
            }
            defs[k] = clean;
        });

        return Object.keys(defs).length ? defs : null;
    },

    // ── 运行仿真 ──
    run: function() {
        var code = document.getElementById('val-code').value.trim();
        if (!code) { Modal.alert('提示', '请先在左侧输入股票代码'); return; }

        var sel = document.getElementById('sim-method');
        var methodName = sel ? sel.value : '';
        if (!methodName) { Modal.alert('提示', '请选择估值方法'); return; }

        var targetField = document.getElementById('sim-target');
        var target = targetField ? targetField.value : '';
        if (!target) { Modal.alert('提示', '请选择目标输出字段'); return; }

        var iterInput = document.getElementById('sim-iterations');
        var nIter = parseInt(iterInput ? iterInput.value : 5000);
        if (isNaN(nIter) || nIter < 100) nIter = 5000;
        if (nIter > 50000) nIter = 50000;
        if (iterInput) iterInput.value = nIter;

        var paramDefs = this.buildParamDefs();

        var statusEl = document.getElementById('sim-status');
        var resultEl = document.getElementById('sim-result');
        var btn = document.getElementById('btn-sim-run');
        if (statusEl) statusEl.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 仿真中... (约 5-15s)';
        if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 运行中'; }

        var body = {
            stock_code: code,
            method_name: methodName,
            n_iterations: nIter,
            target_field: target,
        };
        if (paramDefs) body.params = paramDefs;

        var self = this;
        fetch(API_BASE + '/quant/valuation/simulate', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body)
        })
        .then(function(r) { return r.json(); })
        .then(function(d) {
            if (!d.success) throw new Error(d.error || '仿真失败');
            self.renderResults(d.data, target, code);
            if (statusEl) statusEl.innerHTML = '✅ 仿真完成 (' + (d.data.n_valid || 0) + ' 有效样本)';
        })
        .catch(function(e) {
            if (statusEl) statusEl.innerHTML = '❌ ' + e.message;
            if (resultEl) resultEl.innerHTML = '<div style="color:var(--accent-red);text-align:center;padding:20px;">' + self.esc(e.message) + '</div>';
        })
        .finally(function() {
            if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-rocket"></i> 运行仿真'; }
        });
    },

    // ── 渲染仿真结果 ──
    renderResults: function(data, targetField, stockCode) {
        if (!data || data.error) {
            document.getElementById('sim-result').innerHTML = '<div style="color:var(--accent-red);text-align:center;padding:20px;">' + this.esc(data ? data.error : '无数据') + '</div>';
            return;
        }
        var el = document.getElementById('sim-result');
        if (!el) return;

        // 统计卡片
        var stats = [
            {l:'均值', v:data.mean, c:''},
            {l:'中位数', v:data.median, c:''},
            {l:'标准差', v:data.std, c:''},
            {l:'P10', v:data.p10, c:''},
            {l:'P25', v:data.p25, c:''},
            {l:'P75', v:data.p75, c:''},
            {l:'P90', v:data.p90, c:''},
            {l:'上行概率', v:data.upside_prob, u:'%', c:data.upside_prob > 50 ? 'status-under' : (data.upside_prob < 50 ? 'status-over' : 'status-fair')},
        ];

        var html = '';

        // 统计面板
        html += '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-bottom:10px;">';
        stats.forEach(function(s) {
            if (s.v == null) return;
            var val = s.v + (s.u || '');
            var cls = s.c || '';
            html += '<div class="v-metric-card" style="padding:8px;">';
            html += '<div class="label">' + s.l + '</div>';
            html += '<div class="value ' + cls + '" style="font-size:17px;">' + val + '</div>';
            html += '</div>';
        });
        html += '</div>';

        // 当前价格对比
        if (data.current_price != null) {
            var currentPrice = data.current_price;
            var meanVal = data.mean;
            var diff = meanVal ? ((meanVal - currentPrice) / currentPrice * 100).toFixed(1) : '?';
            var diffCls = diff > 0 ? 'status-under' : 'status-over';
            html += '<div style="display:flex;gap:10px;font-size:11px;margin-bottom:8px;padding:6px 10px;background:rgba(255,255,255,0.02);border-radius:4px;">';
            html += '<span>当前价: <strong style="color:#fff;">¥' + currentPrice.toFixed(2) + '</strong></span>';
            html += '<span>仿真均值: <strong style="color:var(--accent-blue);">¥' + (meanVal ? meanVal.toFixed(2) : '?') + '</strong></span>';
            html += '<span>潜在差异: <strong class="' + diffCls + '">' + (diff > 0 ? '+' : '') + diff + '%</strong></span>';
            if (data.upside_prob != null) {
                var pColor = data.upside_prob > 60 ? 'var(--accent-green)' : (data.upside_prob < 40 ? 'var(--accent-red)' : 'var(--accent-gold)');
                html += '<span>上行(>现价)概率: <strong style="color:' + pColor + ';">' + data.upside_prob + '%</strong></span>';
            }
            if (data.skew_indicator != null) {
                html += '<span>分布偏度: <strong style="color:var(--text-dim);">' + (data.skew_indicator > 0 ? '右偏+' : '左偏') + Math.abs(data.skew_indicator) + '%</strong></span>';
            }
            html += '</div>';
        }

        // ECharts histogram
        var samples = data.samples || [];
        if (samples.length > 10 && typeof echarts !== 'undefined') {
            html += '<div id="sim-histogram" style="height:260px;width:100%;"></div>';

            // Build histogram bins
            var binCount = 40;
            var min = Math.min.apply(null, samples);
            var max = Math.max.apply(null, samples);
            var range = max - min;
            if (range <= 0) range = 1;
            var binWidth = range / binCount;

            var bins = [];
            for (var i = 0; i < binCount; i++) {
                bins.push(0);
            }
            samples.forEach(function(s) {
                var idx = Math.min(Math.floor((s - min) / binWidth), binCount - 1);
                bins[idx]++;
            });

            var binLabels = [];
            for (var i = 0; i < binCount; i++) {
                binLabels.push('¥' + (min + i * binWidth).toFixed(1));
            }

            html += '<div style="font-size:9px;color:var(--text-micro);text-align:center;margin-top:4px;">';
            html += '样本数: ' + samples.length + ' | 范围: ¥' + data.min + ' ~ ¥' + data.max;
            html += '</div>';

            el.innerHTML = html;

            // Draw histogram
            try {
                if (this.chart) this.chart.dispose();
                this.chart = echarts.init(document.getElementById('sim-histogram'));

                var option = {
                    tooltip: {
                        trigger: 'axis',
                        formatter: function(params) {
                            var p = params[0];
                            var idx = p.dataIndex;
                            var lo = (min + idx * binWidth).toFixed(2);
                            var hi = (min + (idx + 1) * binWidth).toFixed(2);
                            return '¥' + lo + ' ~ ¥' + hi + '<br/>频次: ' + p.value;
                        }
                    },
                    grid: {left: 50, right: 20, top: 20, bottom: 30},
                    xAxis: {
                        type: 'category',
                        data: binLabels,
                        axisLabel: {rotate: 45, fontSize: 9, color: '#666', interval: Math.max(1, Math.floor(binCount / 15))},
                        axisLine: {lineStyle: {color: '#333'}},
                    },
                    yAxis: {
                        type: 'value',
                        axisLabel: {fontSize: 9, color: '#666'},
                        splitLine: {lineStyle: {color: 'rgba(255,255,255,0.04)'}},
                    },
                    series: [{
                        type: 'bar',
                        data: bins.map(function(c) { return c; }),
                        barWidth: '90%',
                        itemStyle: {
                            color: {
                                type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
                                colorStops: [
                                    {offset: 0, color: 'rgba(0,206,209,0.8)'},
                                    {offset: 1, color: 'rgba(0,136,204,0.3)'},
                                ]
                            }
                        },
                    }],
                    // 标记当前价格线
                };
                // 添加当前价格标记线
                if (data.current_price != null && data.current_price >= min && data.current_price <= max) {
                    option.series.push({
                        type: 'line',
                        markLine: {
                            silent: true,
                            symbol: 'none',
                            lineStyle: {color: '#ff4757', type: 'dashed', width: 2},
                            label: {formatter: '当前价 ¥' + data.current_price.toFixed(2), color: '#ff4757', fontSize: 10},
                            data: [{xAxis: Math.floor((data.current_price - min) / binWidth)}]
                        }
                    });
                }
                this.chart.setOption(option);
            } catch(e) { console.error('[Sim] Chart error:', e); }

        } else {
            // 样本不足时显示表格
            html += '<div style="font-size:10px;color:var(--text-dim);margin-top:8px;">有效样本: ' + samples.length + ' 个</div>';
            el.innerHTML = html;
        }
    },

    // ── 工具 ──
    esc: function(s) {
        if (!s) return '';
        return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    },

    // ── 绑定事件 ──
    bindEvents: function() {
        var sel = document.getElementById('sim-method');
        if (sel) {
            sel.addEventListener('change', function() { ValuationSim.onMethodChange(); });
        }
    },
};
