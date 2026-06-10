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
        if (typeof SyncAPI !== 'undefined') {
            await SyncAPI.market(null, 'smart');
        } else {
            await API.post('/data/sync/daily/auto', { type: 'AUTO' });
        }
        updateAccountSummary();
        if (typeof window.refreshPageData === 'function') window.refreshPageData();
    } catch (e) {
        Modal.alert('同步失败', e.message);
    }
    btn.disabled = false;
    btn.innerHTML = origHTML;
}

document.addEventListener('DOMContentLoaded', initCommon);


// ═══ 健康体检结果渲染器 (全局, 供 quant.html / watchlist 共用) ═══

window.renderHealthCheckHTML = function(result) {
    if (!result) return '<div style="color:var(--text-dim);padding:20px;">无数据</div>';

    const overall = result.overall || {};
    const verdict = overall.verdict || 'UNKNOWN';
    const confidence = overall.confidence || 'low';
    const summary = overall.summary || '';
    const stockCode = result.stock_code || '';
    const stockName = result.stock_name || '';
    const dims = result.dimensions || [];
    const risks = result.key_risks || [];
    const catalysts = result.key_catalysts || [];
    const overallAnalysis = result.overall_analysis || '';

    const vcMap = { BUY:'var(--accent-green)', HOLD:'var(--accent-gold)', SELL:'var(--accent-red)', WATCH:'var(--accent-blue)' };
    const vcBg  = { BUY:'rgba(76,175,80,0.15)', HOLD:'rgba(255,193,7,0.15)', SELL:'rgba(244,67,54,0.15)', WATCH:'rgba(33,150,243,0.15)' };
    const vColor = vcMap[verdict] || 'var(--text-dim)';
    const vBg = vcBg[verdict] || 'rgba(255,255,255,0.05)';
    const confMap = { high:'高', medium:'中', low:'低' };

    const dimVerdictStyles = {
        'PASS':{color:'var(--accent-green)',bg:'rgba(76,175,80,0.12)'},
        'CAUTION':{color:'var(--accent-gold)',bg:'rgba(255,193,7,0.12)'},
        'FAIL':{color:'var(--accent-red)',bg:'rgba(244,67,54,0.12)'},
        'INSUFFICIENT_DATA':{color:'var(--text-dim)',bg:'rgba(255,255,255,0.05)'},
        'BULLISH':{color:'var(--accent-green)',bg:'rgba(76,175,80,0.12)'},
        'NEUTRAL':{color:'var(--accent-gold)',bg:'rgba(255,193,7,0.12)'},
        'BEARISH':{color:'var(--accent-red)',bg:'rgba(244,67,54,0.12)'},
        'STRONG':{color:'var(--accent-green)',bg:'rgba(76,175,80,0.12)'},
        'ADEQUATE':{color:'var(--accent-blue)',bg:'rgba(33,150,243,0.12)'},
        'WEAK':{color:'var(--accent-red)',bg:'rgba(244,67,54,0.12)'},
        'UNKNOWN':{color:'var(--text-dim)',bg:'rgba(255,255,255,0.05)'},
        'OVERPRICED':{color:'var(--accent-red)',bg:'rgba(244,67,54,0.12)'},
        'FAIR':{color:'var(--accent-gold)',bg:'rgba(255,193,7,0.12)'},
        'UNDERVALUED':{color:'var(--accent-green)',bg:'rgba(76,175,80,0.12)'},
    };

    var dimCards = '';
    var dimOrder = ['财务健康','技术面','人才与专利','估值合理性'];
    for (var di = 0; di < dimOrder.length; di++) {
        var dName = dimOrder[di];
        var dim = null;
        for (var j = 0; j < dims.length; j++) {
            var dn = dims[j].name || '';
            if (dn === dName) { dim = dims[j]; break; }
        }
        if (!dim) {
            dimCards += '<div style="background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.06);border-radius:6px;padding:10px;opacity:0.4;">' +
                '<div style="font-size:11px;color:var(--text-dim);">' + dName + '</div>' +
                '<div style="font-size:10px;color:var(--text-micro);margin-top:8px;">未分析</div></div>';
            continue;
        }
        var dv = dim.verdict || '?';
        var ds = dimVerdictStyles[dv] || {color:'var(--text-dim)', bg:'rgba(255,255,255,0.05)'};
        var dc = dim.confidence || 'medium';
        var evidence = dim.evidence || [];
        var analysis = dim.analysis || '';
        dimCards += '<div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);border-radius:6px;padding:10px;">' +
            '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">' +
                '<span style="font-size:11px;color:#ddd;">' + dName + '</span>' +
                '<span style="font-size:11px;font-weight:600;color:' + ds.color + ';background:' + ds.bg + ';padding:2px 8px;border-radius:3px;">' + dv + '</span>' +
            '</div>' +
            '<div style="font-size:9px;color:var(--text-micro);margin-bottom:4px;">置信度: ' + (confMap[dc]||dc) + '</div>' +
            (evidence.length > 0 ? '<div style="font-size:10px;color:var(--text-dim);"><ul style="margin:0;padding-left:14px;">' +
                evidence.map(function(e){return '<li>' + escHtml(e) + '</li>';}).join('') + '</ul></div>' : '') +
            (analysis ? '<div style="font-size:9px;color:var(--text-micro);border-top:1px solid rgba(255,255,255,0.05);padding-top:4px;margin-top:4px;">' + escHtml(analysis.substring(0,120)) + '</div>' : '') +
        '</div>';
    }

    return '<div style="font-size:12px;">' +
        // Header
        '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">' +
            '<div><span style="color:var(--accent-blue);font-weight:600;">' + escHtml(stockCode) + '</span>' +
            (stockName ? '<span style="color:var(--text-dim);margin-left:6px;">' + escHtml(stockName) + '</span>' : '') + '</div>' +
            '<div style="display:flex;gap:6px;align-items:center;">' +
                '<span style="font-size:14px;font-weight:700;color:' + vColor + ';background:' + vBg + ';padding:3px 12px;border-radius:4px;">' + verdict + '</span>' +
                '<span style="font-size:10px;color:var(--text-dim);">(' + (confMap[confidence]||confidence) + ')</span>' +
            '</div>' +
        '</div>' +
        (summary ? '<div style="margin-bottom:10px;padding:8px;border-left:3px solid ' + vColor + ';background:rgba(0,0,0,0.2);border-radius:2px;font-size:12px;color:#ddd;">' + escHtml(summary) + '</div>' : '') +
        // Dimension cards
        '<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:10px;">' + dimCards + '</div>' +
        // Risks & Catalysts
        (risks.length > 0 || catalysts.length > 0 ? '<div style="display:flex;gap:12px;margin-bottom:8px;">' +
            (risks.length > 0 ? '<div style="flex:1;"><div style="font-size:10px;color:var(--accent-red);margin-bottom:4px;">⚠ 关键风险</div><ul style="margin:0;padding-left:14px;font-size:10px;color:var(--text-dim);">' +
                risks.map(function(r){return '<li>' + escHtml(r) + '</li>';}).join('') + '</ul></div>' : '') +
            (catalysts.length > 0 ? '<div style="flex:1;"><div style="font-size:10px;color:var(--accent-green);margin-bottom:4px;">⚡ 关键催化剂</div><ul style="margin:0;padding-left:14px;font-size:10px;color:var(--text-dim);">' +
                catalysts.map(function(c){return '<li>' + escHtml(c) + '</li>';}).join('') + '</ul></div>' : '') +
        '</div>' : '') +
        (overallAnalysis ? '<div style="font-size:10px;color:var(--text-dim);border-top:1px solid rgba(255,255,255,0.06);padding-top:8px;line-height:1.6;">' + escHtml(overallAnalysis) + '</div>' : '') +
    '</div>';
};
