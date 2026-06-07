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
    /** 是否处于业务驱动仿真模式 */
    _driverMode: false,
    /** 业务驱动因素字段定义 (从后端加载) */
    driverFields: [],
    /** 驱动因素 idx 计数器 */
    _driverIdx: 0,

    // ── 初始化 ──
    init: function() {
        this.loadRegistry();
        this.loadDriverFields();
        this.bindEvents();
    },

    // ── 模式切换 (method / driver) ──
    switchMode: function(mode) {
        this._driverMode = (mode === 'driver');
        var methodBtn = document.getElementById('sim-mode-method');
        var driverBtn = document.getElementById('sim-mode-driver');
        var methodControls = document.getElementById('sim-method-controls');
        var driverControls = document.getElementById('sim-driver-controls');
        var paramsTitle = document.getElementById('sim-params-title');

        if (this._driverMode) {
            if (methodBtn) { methodBtn.style.background = 'transparent'; methodBtn.style.color = 'var(--text-dim)'; }
            if (driverBtn) { driverBtn.style.background = 'rgba(112,161,255,0.12)'; driverBtn.style.color = 'var(--accent-blue)'; }
            if (methodControls) methodControls.style.display = 'none';
            if (driverControls) driverControls.style.display = 'block';
            if (paramsTitle) paramsTitle.textContent = '业务驱动因素配置';
            this.renderDriverParams();
        } else {
            if (driverBtn) { driverBtn.style.background = 'transparent'; driverBtn.style.color = 'var(--text-dim)'; }
            if (methodBtn) { methodBtn.style.background = 'rgba(112,161,255,0.12)'; methodBtn.style.color = 'var(--accent-blue)'; }
            if (methodControls) methodControls.style.display = 'block';
            if (driverControls) driverControls.style.display = 'none';
            if (paramsTitle) paramsTitle.textContent = '参数分布配置';
            this.onMethodChange();
        }
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

    // ── 加载业务驱动因素字段定义 ──
    loadDriverFields: function() {
        var self = this;
        fetch(API_BASE + '/quant/valuation/driver-fields')
            .then(function(r) { return r.json(); })
            .then(function(d) {
                self.driverFields = d.data || [];
                if (self._driverMode) self.renderDriverParams();
            })
            .catch(function() {});
    },

    // ── 渲染业务驱动因素参数卡 (模拟 renderParams 风格) ──
    renderDriverParams: function() {
        var container = document.getElementById('sim-params');
        if (!container) return;
        var fields = this.driverFields;
        if (!fields.length) {
            container.innerHTML = '<div style="color:var(--text-micro);font-size:10px;">驱动因素加载中...</div>';
            return;
        }
        var self = this;
        var html = fields.map(function(f, idx) {
            var label = f.label || f.key;
            var unit = f.unit || '';
            var desc = f.desc || '';
            var defaultVal = f.default || 0;
            return '<div class="sim-param-card" style="background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.06);border-radius:4px;padding:8px;margin-bottom:6px;">' +
                '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">' +
                '<span style="color:#ccc;font-size:11px;font-weight:600;">' + self.esc(label) + '</span>' +
                '<span style="color:var(--text-micro);font-size:9px;">' + self.esc(unit) + ' | ' + self.esc(f.key) + '</span>' +
                '</div>' +
                '<div style="font-size:9px;color:var(--text-dim);margin-bottom:4px;">' + self.esc(desc) + '</div>' +
                '<div style="display:flex;gap:4px;flex-wrap:wrap;">' +
                '<select id="sim-dd-' + idx + '" style="background:#000;border:1px solid var(--border-color);color:#fff;padding:3px 6px;border-radius:3px;font-size:10px;" onchange="ValuationSim._onDriverDistChange(' + idx + ')">' +
                '<option value="normal">正态</option>' +
                '<option value="uniform">均匀</option>' +
                '<option value="triangular">三角</option>' +
                '<option value="lognormal">对数正态</option>' +
                '<option value="fixed">固定</option>' +
                '</select>' +
                '<span id="sim-dp-' + idx + '">' +
                '<input type="text" id="sim-dmean-' + idx + '" value="' + defaultVal + '" placeholder="均值" style="width:60px;background:#000;border:1px solid var(--border-color);color:#fff;padding:3px 6px;border-radius:3px;font-size:10px;">' +
                '<input type="text" id="sim-dstd-' + idx + '" value="' + (defaultVal * 0.3).toFixed(1) + '" placeholder="标准差" style="width:55px;background:#000;border:1px solid var(--border-color);color:#fff;padding:3px 6px;border-radius:3px;font-size:10px;">' +
                '</span>' +
                '</div>' +
                '</div>';
        }).join('');
        container.innerHTML = html;
    },

    // ── 驱动因素分布切换 → 更新参数输入框 ──
    _onDriverDistChange: function(idx) {
        var sel = document.getElementById('sim-dd-' + idx);
        var dist = sel ? sel.value : 'normal';
        var container = document.getElementById('sim-dp-' + idx);
        if (!container) return;
        var html = '';
        switch (dist) {
            case 'normal':
                html = '<input type="text" id="sim-dmean-' + idx + '" placeholder="均值" style="width:60px;background:#000;border:1px solid var(--border-color);color:#fff;padding:3px 6px;border-radius:3px;font-size:10px;">' +
                    '<input type="text" id="sim-dstd-' + idx + '" placeholder="标准差" style="width:55px;background:#000;border:1px solid var(--border-color);color:#fff;padding:3px 6px;border-radius:3px;font-size:10px;">';
                break;
            case 'uniform':
                html = '<input type="text" id="sim-dmin-' + idx + '" placeholder="下限" style="width:55px;background:#000;border:1px solid var(--border-color);color:#fff;padding:3px 6px;border-radius:3px;font-size:10px;">' +
                    '<input type="text" id="sim-dmax-' + idx + '" placeholder="上限" style="width:55px;background:#000;border:1px solid var(--border-color);color:#fff;padding:3px 6px;border-radius:3px;font-size:10px;">';
                break;
            case 'triangular':
                html = '<input type="text" id="sim-dmin-' + idx + '" placeholder="下限" style="width:50px;background:#000;border:1px solid var(--border-color);color:#fff;padding:3px 6px;border-radius:3px;font-size:10px;">' +
                    '<input type="text" id="sim-dmode-' + idx + '" placeholder="众数" style="width:50px;background:#000;border:1px solid var(--border-color);color:#fff;padding:3px 6px;border-radius:3px;font-size:10px;">' +
                    '<input type="text" id="sim-dmax-' + idx + '" placeholder="上限" style="width:50px;background:#000;border:1px solid var(--border-color);color:#fff;padding:3px 6px;border-radius:3px;font-size:10px;">';
                break;
            case 'lognormal':
                html = '<input type="text" id="sim-dmean-' + idx + '" placeholder="均值" style="width:60px;background:#000;border:1px solid var(--border-color);color:#fff;padding:3px 6px;border-radius:3px;font-size:10px;">' +
                    '<input type="text" id="sim-dstd-' + idx + '" placeholder="标准差" style="width:55px;background:#000;border:1px solid var(--border-color);color:#fff;padding:3px 6px;border-radius:3px;font-size:10px;">';
                break;
            case 'fixed':
                html = '<input type="text" id="sim-dvalue-' + idx + '" placeholder="固定值" style="width:80px;background:#000;border:1px solid var(--border-color);color:#fff;padding:3px 6px;border-radius:3px;font-size:10px;">';
                break;
        }
        container.innerHTML = html;
    },

    // ── 编译驱动因素分布定义 → API 请求参数 ──
    _buildDriverDefs: function() {
        var fields = this.driverFields;
        if (!fields.length) return null;
        var defs = {};
        fields.forEach(function(f, idx) {
            var sel = document.getElementById('sim-dd-' + idx);
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
                    def.mean = getV('sim-dmean-' + idx);
                    def.std = getV('sim-dstd-' + idx);
                    break;
                case 'uniform':
                    def.min = getV('sim-dmin-' + idx);
                    def.max = getV('sim-dmax-' + idx);
                    break;
                case 'triangular':
                    def.min = getV('sim-dmin-' + idx);
                    def.mode = getV('sim-dmode-' + idx);
                    def.max = getV('sim-dmax-' + idx);
                    break;
                case 'lognormal':
                    def.mean = getV('sim-dmean-' + idx);
                    def.std = getV('sim-dstd-' + idx);
                    break;
                case 'fixed':
                    def.value = getV('sim-dvalue-' + idx);
                    break;
            }
            var clean = {};
            for (var dk in def) { if (def[dk] != null) clean[dk] = def[dk]; }
            if (Object.keys(clean).length > 1) defs[f.key] = clean;
        });
        return Object.keys(defs).length ? defs : null;
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

    // ── 运行仿真 (根据模式分支) ──
    run: function() {
        if (this._driverMode) {
            this.runDriver();
        } else {
            this.runMethod();
        }
    },

    // ── 运行参数仿真 (原有逻辑) ──
    runMethod: function() {
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

    // ── 运行业务驱动仿真 ──
    runDriver: function() {
        var iterInput = document.getElementById('sim-iterations');
        var nIter = parseInt(iterInput ? iterInput.value : 5000);
        if (isNaN(nIter) || nIter < 100) nIter = 5000;
        if (nIter > 50000) nIter = 50000;
        if (iterInput) iterInput.value = nIter;

        var driverDefs = this._buildDriverDefs();
        if (!driverDefs) { Modal.alert('提示', '请配置至少一个驱动因素的分布参数'); return; }

        var statusEl = document.getElementById('sim-status');
        var resultEl = document.getElementById('sim-result');
        var btn = document.getElementById('btn-sim-run');
        if (statusEl) statusEl.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 业务仿真中... (约 5-15s)';
        if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 运行中'; }

        var self = this;
        fetch(API_BASE + '/quant/valuation/driver-simulate', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                n_iterations: nIter,
                drivers: driverDefs,
            })
        })
        .then(function(r) { return r.json(); })
        .then(function(d) {
            if (!d.success) throw new Error(d.error || '仿真失败');
            self._renderDriverResults(d.data);
            if (statusEl) statusEl.innerHTML = '✅ 业务仿真完成 (' + (d.data.n_valid || 0) + ' 有效样本)';
        })
        .catch(function(e) {
            if (statusEl) statusEl.innerHTML = '❌ ' + e.message;
            if (resultEl) resultEl.innerHTML = '<div style="color:var(--accent-red);text-align:center;padding:20px;">' + self.esc(e.message) + '</div>';
        })
        .finally(function() {
            if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-rocket"></i> 运行仿真'; }
        });
    },

    // ── 渲染业务驱动仿真结果 ──
    _renderDriverResults: function(data) {
        if (!data || data.error) {
            document.getElementById('sim-result').innerHTML = '<div style="color:var(--accent-red);text-align:center;padding:20px;">' + this.esc(data ? data.error : '无数据') + '</div>';
            return;
        }
        var el = document.getElementById('sim-result');
        if (!el) return;

        // 统计卡片
        var stats = [
            {l:'每股价值(均值)', v:data.mean, u:'¥'},
            {l:'中位数', v:data.median, u:'¥'},
            {l:'标准差', v:data.std, u:'¥'},
            {l:'P10', v:data.p10, u:'¥'},
            {l:'P25', v:data.p25, u:'¥'},
            {l:'P75', v:data.p75, u:'¥'},
            {l:'P90', v:data.p90, u:'¥'},
            {l:'偏度', v:data.skew_indicator, u:'%', c:data.skew_indicator > 0 ? 'status-under' : 'status-over'},
        ];

        var html = '';
        html += '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-bottom:10px;">';
        stats.forEach(function(s) {
            if (s.v == null) return;
            html += '<div class="v-metric-card" style="padding:8px;">';
            html += '<div class="label">' + s.l + '</div>';
            html += '<div class="value ' + (s.c||'') + '" style="font-size:17px;">' + s.v + (s.u||'') + '</div>';
            html += '</div>';
        });
        html += '</div>';

        // 样本信息
        html += '<div style="font-size:9px;color:var(--text-micro);text-align:center;margin-bottom:6px;">';
        html += '有效样本: ' + (data.n_valid || 0) + ' | 范围: ¥' + data.min + ' ~ ¥' + data.max;
        html += '</div>';

        // ECharts histogram (与 renderResults 相同逻辑)
        var samples = data.samples || [];
        if (samples.length > 10 && typeof echarts !== 'undefined') {
            html += '<div id="sim-histogram" style="height:240px;width:100%;"></div>';

            var binCount = 40;
            var min = Math.min.apply(null, samples);
            var max = Math.max.apply(null, samples);
            var range = max - min;
            if (range <= 0) range = 1;
            var binWidth = range / binCount;
            var bins = [];
            for (var i = 0; i < binCount; i++) bins.push(0);
            samples.forEach(function(s) {
                var idx = Math.min(Math.floor((s - min) / binWidth), binCount - 1);
                bins[idx]++;
            });
            var binLabels = [];
            for (var i = 0; i < binCount; i++) binLabels.push('¥' + (min + i * binWidth).toFixed(1));

            html += '<div style="margin-top:6px;border:1px solid rgba(255,255,255,0.06);border-radius:4px;overflow:hidden;">';
            html += '<div style="display:flex;align-items:center;padding:4px 8px;cursor:pointer;font-size:10px;color:var(--text-dim);background:rgba(255,255,255,0.02);user-select:none;" onclick="var b=this.nextElementSibling;b.classList.toggle(\'hidden\');this.querySelector(\'.arr\').classList.toggle(\'collapsed\');">';
            html += '<span class="arr" style="font-size:8px;margin-right:4px;transition:transform 0.2s;">&#9660;</span>';
            html += '<span style="color:var(--accent-green);">🏭</span> 结果解读 — 业务驱动仿真';
            html += '</div>';
            html += '<div class="hidden" style="padding:6px 8px;font-size:9px;color:var(--text-dim);line-height:1.6;border-top:1px solid rgba(255,255,255,0.04);">';
            html += '• 基于您设定的量价假设，系统自动构建了 DCF 估值模型<br>';
            html += '• <strong>均值/中位数</strong> — 最可能的每股价值，差值大说明分布不对称<br>';
            html += '• <strong>P10 / P90</strong> — 80% 置信区间，反映假设不确定性带来的价值范围<br>';
            html += '• <strong>偏度</strong> — 右偏(+)时上行潜力大于下行风险<br>';
            html += '💡 LLM Agent 场景: 将业务驱动因素作为 tool 参数，让 Agent 根据行业判断自主设定假设';
            html += '</div></div>';

            el.innerHTML = html;

            try {
                if (this.chart) this.chart.dispose();
                this.chart = echarts.init(document.getElementById('sim-histogram'));
                this.chart.setOption({
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
                        type: 'category', data: binLabels,
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
                                    {offset: 0, color: 'rgba(46,213,115,0.8)'},
                                    {offset: 1, color: 'rgba(0,136,204,0.3)'},
                                ]
                            }
                        },
                    }],
                });
            } catch(e) { console.error('[Sim] Driver chart error:', e); }
        } else {
            el.innerHTML = html + '<div style="font-size:10px;color:var(--text-dim);margin-top:6px;">有效样本: ' + samples.length + ' 个</div>';
        }
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

            // ═══ 结果解读指引 ═══
            html += '<div style="margin-top:6px;border:1px solid rgba(255,255,255,0.06);border-radius:4px;overflow:hidden;">';
            html += '<div style="display:flex;align-items:center;padding:4px 8px;cursor:pointer;font-size:10px;color:var(--text-dim);background:rgba(255,255,255,0.02);user-select:none;" onclick="var b=this.nextElementSibling;b.classList.toggle(\'hidden\');this.querySelector(\'.arr\').classList.toggle(\'collapsed\');">';
            html += '<span class="arr" style="font-size:8px;margin-right:4px;transition:transform 0.2s;">&#9660;</span>';
            html += '<span style="color:var(--accent-blue);">📊</span> 结果解读';
            html += '</div>';
            html += '<div class="hidden" style="padding:6px 8px;font-size:9px;color:var(--text-dim);line-height:1.6;border-top:1px solid rgba(255,255,255,0.04);">';
            html += '• <strong>均值/中位数</strong> — 最可能的估值参考，差值大=分布不对称<br>';
            html += '• <strong>P10 / P90</strong> — 80%置信区间。P10估值低于90%样本，P90高于90%样本<br>';
            html += '• <strong>上行概率</strong> — 仿真结果 > 当前价的占比。>60% = 市场可能低估<br>';
            html += '• <strong>直方图</strong> — 柱子越高代表该价格区间出现越频繁。虚线=当前价<br>';
            html += '• <strong>偏度</strong> — 右偏(大部分样本集中在左侧)通常意味着上行潜力大于下行';
            html += '</div></div>';

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

    // ── 帮助面板切换 ──
    toggleHelp: function() {
        var body = document.getElementById('sim-help-body');
        var arrow = document.getElementById('sim-help-arrow');
        if (!body || !arrow) return;
        var isHidden = (body.style.display === 'none');
        body.style.display = isHidden ? 'block' : 'none';
        arrow.innerHTML = isHidden ? '&#9660;' : '&#9654;';
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
