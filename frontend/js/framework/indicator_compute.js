/**
 * 指标计算公共组件 — 统一前端入口
 * 依赖: api.js (API_BASE)
 *
 * 用法:
 *   // 方式1: 完整控制面板
 *   IndicatorCompute.render('container-id');
 *
 *   // 方式2: 直接提交 (无 UI)
 *   IndicatorCompute.submit({ mode: 'historical' }, function(msg, type) { ... });
 */
var IndicatorCompute = {
  /**
   * 渲染完整控制面板到指定容器
   * @param {string} containerId - 目标容器 DOM id
   */
  render: function(containerId) {
    var el = document.getElementById(containerId);
    if (!el) return;
    el.innerHTML =
      '<div style="font-size:11px;color:var(--text-dim);margin-bottom:6px;"><i class="fas fa-calculator"></i> 指标计算</div>' +
      // Mode radios
      '<div style="display:flex;gap:4px;margin-bottom:6px;">' +
        '<label style="font-size:10px;color:var(--text-micro);display:flex;align-items:center;gap:3px;"><input type="radio" name="ic-mode" value="historical" checked> 全量</label>' +
        '<label style="font-size:10px;color:var(--text-micro);display:flex;align-items:center;gap:3px;"><input type="radio" name="ic-mode" value="incremental"> 增量</label>' +
        '<label style="font-size:10px;color:var(--text-micro);display:flex;align-items:center;gap:3px;"><input type="radio" name="ic-mode" value="snapshot"> 快照</label>' +
      '</div>' +
      // Stock scope
      '<div style="margin-bottom:6px;">' +
        '<label style="font-size:10px;color:var(--text-micro);display:flex;align-items:center;gap:3px;margin-bottom:3px;"><input type="radio" name="ic-scope" value="all" checked onchange="IndicatorCompute._toggleCode()"> 全部持仓+自选股</label>' +
        '<label style="font-size:10px;color:var(--text-micro);display:flex;align-items:center;gap:3px;"><input type="radio" name="ic-scope" value="custom" onchange="IndicatorCompute._toggleCode()"> 指定代码</label>' +
        '<input type="text" id="ic-codes" placeholder="如: 688012,002409" disabled style="width:100%;background:#000;border:1px solid var(--border-color);color:#fff;padding:4px 8px;border-radius:4px;font-size:10px;">' +
      '</div>' +
      // Indicator filter
      '<div style="margin-bottom:8px;">' +
        '<label style="font-size:10px;color:var(--text-micro);display:flex;align-items:center;gap:3px;"><input type="checkbox" id="ic-filter-ind" onchange="IndicatorCompute._toggleInd()"> 指定指标</label>' +
        '<div id="ic-ind-checkboxes" style="display:none;max-height:200px;overflow-y:auto;background:#000;border:1px solid var(--border-color);border-radius:4px;padding:6px 8px;margin-top:4px;">加载中...</div>' +
        '<input type="text" id="ic-ind-names" placeholder="如: macd,rsi (旧版输入框)" disabled style="width:100%;background:#000;border:1px solid var(--border-color);color:#fff;padding:4px 8px;border-radius:4px;font-size:10px;display:none;">' +
      '</div>' +
      // Submit button
      '<button id="ic-btn-submit" onclick="IndicatorCompute._onSubmit()" style="font-size:11px;width:100%;background:transparent;border:1px solid var(--accent-blue);color:var(--accent-blue);cursor:pointer;padding:6px 10px;border-radius:4px;justify-content:center;display:flex;align-items:center;gap:4px;"><i class="fas fa-paper-plane"></i> 提交计算任务</button>' +
      '<div id="ic-status" style="font-size:10px;color:var(--text-micro);margin-top:6px;text-align:center;"></div>';
  },

  /**
   * 直接提交 (无 UI), 适合快捷按钮
   * @param {object} params - { mode, target_codes?, indicator_names? }
   * @param {function} feedback - function(msg, type) 用于反馈
   */
  submit: function(params, feedback) {
    var fn = feedback || function(msg, type) { console.log('[IndicatorCompute]', msg); };
    fn('提交异步指标计算任务...', 'info');
    fetch(API_BASE + '/system/tasks/executions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_code: 'calc_indicators', params: params || {} })
    }).then(function(r) { return r.json(); }).then(function(d) {
      fn('任务入队: ' + (d.id || 'ok') + ', 请查看任务监视器', 'success');
    }).catch(function(e) { fn('入队失败: ' + e.message, 'error'); });
  },

  // ═══ 内部: 面板控件逻辑 ═══

  _toggleCode: function() {
    var custom = document.querySelector('input[name="ic-scope"]:checked');
    var el = document.getElementById('ic-codes');
    if (el && custom) el.disabled = custom.value !== 'custom';
  },

  _toggleInd: function() {
    var cb = document.getElementById('ic-filter-ind');
    var boxDiv = document.getElementById('ic-ind-checkboxes');
    if (!cb || !boxDiv) return;
    if (cb.checked) {
      boxDiv.style.display = '';
      // 懒加载: 从 API 拉取指标列表
      if (boxDiv.innerHTML === '加载中...') {
        var self = this;
        fetch(API_BASE + '/quant/indicators/registry').then(function(r) { return r.json(); }).then(function(d) {
          var list = d.data || [];
          var html = '';
          list.forEach(function(ind) {
            html += '<label style=\"display:flex;align-items:center;gap:4px;padding:2px 0;font-size:10px;color:var(--text-dim);cursor:pointer;\">' +
              '<input type=\"checkbox\" class=\"ic-ind-cb\" value=\"' + ind.name + '\" checked>' +
              '<span style=\"color:#fff;\">' + ind.name + '</span>' +
              '<span style=\"color:var(--text-micro);\">' + (ind.label || '') + '</span>' +
              '<span style=\"color:var(--text-micro);font-size:9px;\">[' + ind.category + ']</span>' +
              '</label>';
          });
          boxDiv.innerHTML = html;
        }).catch(function() { boxDiv.innerHTML = '加载失败'; });
      }
    } else {
      boxDiv.style.display = 'none';
    }
  },

  _onSubmit: function() {
    var btn = document.getElementById('ic-btn-submit');
    var status = document.getElementById('ic-status');
    var params = this._readParams();
    if (!params) return;  // validation failed, _readParams sets status text

    var origHTML = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 入队中...';
    btn.disabled = true;
    if (status) status.textContent = '提交中...';

    var self = this;
    fetch(API_BASE + '/system/tasks/executions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_code: 'calc_indicators', params: params })
    }).then(function(r) { return r.json(); }).then(function(d) {
      if (status) status.textContent = '任务入队: ' + (d.id || 'ok') + ' | 请查看任务监视器';
    }).catch(function(e) {
      if (status) status.textContent = '入队失败: ' + e.message;
    }).finally(function() {
      btn.innerHTML = origHTML;
      btn.disabled = false;
    });
  },

  _readParams: function() {
    var status = document.getElementById('ic-status');
    var modeEl = document.querySelector('input[name="ic-mode"]:checked');
    var scopeEl = document.querySelector('input[name="ic-scope"]:checked');
    var mode = modeEl ? modeEl.value : 'historical';
    var scope = scopeEl ? scopeEl.value : 'all';
    var params = { mode: mode };

    if (scope === 'custom') {
      var raw = document.getElementById('ic-codes');
      if (!raw || !raw.value.trim()) {
        if (status) status.textContent = '请输入股票代码';
        return null;
      }
      params.target_codes = raw.value.split(',').map(function(s) { return s.trim(); }).filter(Boolean);
    }
    var filterInd = document.getElementById('ic-filter-ind');
    if (filterInd && filterInd.checked) {
      var cbs = document.querySelectorAll('.ic-ind-cb:checked');
      var names = [];
      cbs.forEach(function(cb) { names.push(cb.value); });
      if (names.length > 0 && names.length < cbs.length + 10) {
        // 只有部分选中时才传 indicator_names (全选 = 不传)
        params.indicator_names = names;
      }
    }
    return params;
  },

  /**
   * 弹出 Modal 对话框, 内含完整控制面板
   * @param {object} defaultParams - 预填默认值 { mode, target_codes, indicator_names }
   */
  openModal: function(defaultParams) {
    var id = 'ic-modal-' + Date.now();
    var modalId = id + '-overlay';
    var html =
      '<div id="' + modalId + '" style="position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.7);z-index:2000;display:flex;justify-content:center;align-items:center;backdrop-filter:blur(4px);" onclick="this.remove()">' +
      '<div style="background:var(--bg-card);width:420px;max-width:95vw;border-radius:8px;border:1px solid var(--border-color);overflow:hidden;" onclick="event.stopPropagation()">' +
      '<div style="padding:10px 14px;border-bottom:1px solid var(--border-color);display:flex;justify-content:space-between;">' +
      '<span style="font-weight:700;">指标计算</span>' +
      '<button onclick="this.closest(\'div[style*=fixed]\').remove()" style="background:none;border:none;color:var(--text-dim);cursor:pointer;font-size:16px;">&times;</button>' +
      '</div>' +
      '<div style="padding:12px 14px;" id="' + id + '"></div>' +
      '</div></div>';
    document.body.insertAdjacentHTML('beforeend', html);

    var self = this;
    setTimeout(function() {
      var container = document.getElementById(id);
      if (!container) return;
      self.render(id);
      // 预填默认值
      var dp = defaultParams || {};
      if (dp.mode) {
        var r = container.querySelector('input[name="ic-mode"][value="' + dp.mode + '"]');
        if (r) r.checked = true;
      }
      if (dp.target_codes && dp.target_codes.length) {
        var scopeR = container.querySelector('input[name="ic-scope"][value="custom"]');
        if (scopeR) scopeR.checked = true;
        var codeEl = document.getElementById('ic-codes');
        if (codeEl) { codeEl.disabled = false; codeEl.value = dp.target_codes.join(','); }
      }
      if (dp.indicator_names && dp.indicator_names.length) {
        var cb = document.getElementById('ic-filter-ind');
        if (cb) cb.checked = true;
        var indEl = document.getElementById('ic-ind-names');
        if (indEl) { indEl.disabled = false; indEl.value = dp.indicator_names.join(','); }
      }
      // 覆写提交按钮: 提交后关闭 Modal
      var btn = document.getElementById('ic-btn-submit');
      if (btn) {
        btn.onclick = function() {
          var params = self._readParams();
          if (!params) return;
          self.submit(params);
          var overlay = document.getElementById(modalId);
          if (overlay) overlay.remove();
        };
      }
    }, 100);
  }
};
