/**
 * AIStock Pro V5.2 — 全局胶水层 (framework 组件已在独立文件中)
 * 加载顺序: api.js → modal.js → common.js → ui.js → page-specific
 */

// 全局初始化
function initCommon() {
    const pageId = document.body.getAttribute('data-page-id');
    if (pageId && window.initPageComponents) {
        window.initPageComponents({
            activeId: pageId,
            title: document.title.split('|')[1]?.trim() || '控制台'
        });
    }

    // 任务监控启动 (TaskMonitor 定义在 framework/task_monitor.js)
    if (typeof TaskMonitor !== 'undefined') TaskMonitor.init();

    // 页面数据自动刷新钩子
    if (typeof window.refreshPageData === 'function') {
        window.refreshPageData();
        setInterval(window.refreshPageData, 60000);
    }

    // 市场跑马灯 (UI_COMPONENTS 定义在 ui.js)
    if (typeof UI_COMPONENTS !== 'undefined' && UI_COMPONENTS.updateMarketTicker) {
        UI_COMPONENTS.updateMarketTicker();
        setInterval(() => UI_COMPONENTS.updateMarketTicker(), 30000);
    }
}

document.addEventListener('DOMContentLoaded', initCommon);
