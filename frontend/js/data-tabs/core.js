/**
 * 数据中心 — Core 共享层
 * 依赖: api.js (API_BASE), common.js (escHtml), 及所有 DataTabs.* 模块
 *
 * 每个 Tab 模块在 DataTabs 命名空间下暴露方法:
 *   Macro:    .sync() .load() .showHistory()
 *   Watchlist:.load() .add() .importPositions() .sync() .syncOne() .refreshHeld() .remove() .editGroup() .showChart() .finDetail()
 *   Health:   .update() .quickSync() .quickCompute() .quickSyncCode() .viewDetail()
 *   Financial:.load() .initDropdown() .selectStock() .syncSelected() .batchSync()
 *   Fundamental: .load()
 *   Alt:      .load()
 */
window.DataTabs = window.DataTabs || {};

(function() {
  var terminalEl, taskIdEl;

  DataTabs.Core = {
    init: function() {
      terminalEl = document.getElementById('data-terminal');
      taskIdEl = document.getElementById('task-id-display');
    },

    addLog: function(msg, type) {
      if (!terminalEl) { terminalEl = document.getElementById('data-terminal'); }
      var time = new Date().toLocaleTimeString('zh-CN', { hour12: false });
      var colors = { info: '#666', success: 'var(--accent-green)', warn: 'var(--accent-gold)', error: 'var(--accent-red)' };
      var line = document.createElement('div');
      line.innerHTML = '<span style="color:#333;">[' + time + ']</span> <span style="color:' + (colors[type] || '#666') + ';">' + msg + '</span>';
      terminalEl.appendChild(line);
      terminalEl.scrollTop = terminalEl.scrollHeight;
      if (terminalEl.children.length > 100) terminalEl.removeChild(terminalEl.firstChild);
    }
  };

  // ═══ Tab 路由 ═══
  DataTabs.switchTab = function(tab) {
    document.querySelectorAll('.data-tab-btn').forEach(function(b) { b.classList.remove('active'); });
    document.querySelectorAll('.data-tab-panel').forEach(function(p) { p.style.display = 'none'; p.classList.remove('active'); });
    var btn = document.querySelector('[data-tab="' + tab + '"]');
    if (btn) btn.classList.add('active');
    var panel = document.getElementById('tab-' + tab);
    if (panel) { panel.style.display = ''; panel.classList.add('active'); }

    var loaders = {
      macro:       function() { DataTabs.Macro.load(); },
      watchlist:   function() { DataTabs.Watchlist.load(); },
      health:      function() { DataTabs.Health.update(); },
      financial:   function() { DataTabs.Financial.initDropdown(); },
      fundamental: function() { DataTabs.Fundamental.load(); },
      alt:         function() { DataTabs.Alt.load(); }
    };
    if (loaders[tab]) loaders[tab]();
  };

  // ═══ 页面数据刷新钩子 (被 common.js initCommon 调用) ═══
  window.refreshPageData = function() {
    if (DataTabs.Macro && DataTabs.Macro.load) DataTabs.Macro.load();
    if (DataTabs.Health && DataTabs.Health.update) DataTabs.Health.update();
  };

  // ═══ 启动 ═══
  document.addEventListener('DOMContentLoaded', function() {
    DataTabs.Core.init();
    DataTabs.Macro.load();
    setTimeout(function() { DataTabs.Health.update(); }, 1000);
  });
})();
