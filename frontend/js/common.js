/**
 * AIStock Pro V5.2 — 全局胶水层 (framework 组件已在独立文件中)
 * 加载顺序: api.js → modal.js → common.js → ui.js → page-specific
 */

function escHtml(s) {
    if (!s) return '';
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}


// 账户概要 (所有页面显示)
async function updateAccountSummary() {
    try {
        const res = await fetch(`${API_BASE}/positions/account/summary`);
        if (!res.ok) return;
        const data = await res.json();
        const totalEl = document.getElementById('total-assets');
        const profitEl = document.getElementById('today-profit');
        if (totalEl) {
            totalEl.innerText = '¥' + Number(data.total_capital || 0).toLocaleString();
            totalEl.parentElement.title = '可用现金: ¥' + Number(data.available_cash || 0).toLocaleString() +
                ' | 市值: ¥' + Number(data.market_value || 0).toLocaleString();
        }
        if (profitEl) {
            const profit = Number(data.today_profit || 0);
            profitEl.innerText = (profit >= 0 ? '¥+' : '¥') + profit.toLocaleString();
            profitEl.style.color = profit >= 0 ? 'var(--accent-green)' : 'var(--accent-red)';
        }
    } catch (e) { /* ignore */ }
}

// 全局初始化
function initCommon() {
    const pageId = document.body.getAttribute('data-page-id');
    if (pageId && window.initPageComponents) {
        window.initPageComponents({
            activeId: pageId,
            title: document.title.split('|')[1]?.trim() || '控制台'
        });
    }

    // 账户概要 (页面加载时查一次)
    updateAccountSummary();

    // 任务监控 (仅面板打开时查询)
    if (typeof TaskMonitor !== 'undefined') TaskMonitor.init();

    // 页面数据钩子 (仅加载时查一次)
    if (typeof window.refreshPageData === 'function') {
        window.refreshPageData();
    }

    // 市场跑马灯 (仅加载时查一次)
    if (typeof UI_COMPONENTS !== 'undefined' && UI_COMPONENTS.updateMarketTicker) {
        UI_COMPONENTS.updateMarketTicker();
    }
}

// 全局同步 (所有页面顶栏按钮)
async function triggerSync() {
    const btn = document.getElementById('btn-sync');
    if (!btn) return;
    btn.disabled = true;
    const origHTML = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 同步中...';
    try {
        await API.post('/data/sync/daily/auto', { type: 'AUTO' });
        updateAccountSummary();
        if (typeof window.refreshPageData === 'function') window.refreshPageData();
    } catch (e) {
        Modal.alert('同步失败', e.message);
    }
    btn.disabled = false;
    btn.innerHTML = origHTML;
}

document.addEventListener('DOMContentLoaded', initCommon);
