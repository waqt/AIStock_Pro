// 使用 common.js 中定义的 API_BASE

// 格式化金额
function formatMoney(val) {
    return '¥' + Number(val).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// 刷新概览数据
async function refreshDashboard() {
    try {
        // 1. 获取账户摘要
        const accRes = await fetch(`${API_BASE}/positions/account/summary`);
        const acc = await accRes.json();
        document.getElementById('total-assets').textContent = formatMoney(acc.total_capital);
        const pColor = acc.today_profit >= 0 ? 'var(--accent-green)' : 'var(--accent-red)';
        document.getElementById('today-profit').textContent = formatMoney(acc.today_profit);
        document.getElementById('today-profit').style.color = pColor;
    } catch (e) {
        console.error('仪表盘刷新失败:', e);
    }

    // 调仓建议和投研模块尚未实现, 显示占位
    renderSuggestions([]);
    renderDeepResearch([]);
}

// 渲染调仓建议
function renderSuggestions(items) {
    const container = document.getElementById('suggestion-list');
    if (!container) return;
    if (!items.length) {
        container.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--text-micro); padding: 40px;">暂无待执行信号<br><small style="color: var(--text-micro);">调仓建议引擎将在后续版本上线</small></td></tr>';
        return;
    }

    container.innerHTML = items.map(s => {
        const actionColor = s.action.includes('BUY') ? 'var(--accent-green)' : 'var(--accent-red)';
        const actionText = s.action === 'BUY' ? '买入' : (s.action === 'SELL' ? '卖出' : s.action);
        return `
            <tr>
                <td class="ticker">${s.stock_name}<br><small style="color: var(--text-micro);">${s.stock_code}</small></td>
                <td><span style="color: ${actionColor}; font-weight: bold;">${actionText}</span></td>
                <td style="text-align: right; font-family: var(--font-mono);">${s.suggested_shares}</td>
                <td style="text-align: right; font-family: var(--font-mono);">¥${Number(s.current_price).toFixed(2)}</td>
                <td style="text-align: right;"><span style="color: var(--accent-gold); font-weight: bold;">${Number(s.score).toFixed(1)}</span></td>
                <td style="text-align: right;">
                    <button class="btn-action" onclick="executeSuggestion(${s.id})">执行</button>
                </td>
            </tr>
        `;
    }).join('');
}

// 渲染深度投研
function renderDeepResearch(items) {
    const container = document.getElementById('research-container');
    if (!container) return;
    if (!items.length) {
        container.innerHTML = '<div style="text-align: center; color: var(--text-micro); padding: 40px;">等待 AI 投研报告生成...<br><small style="color: var(--text-micro);">AI 投研分析模块将在后续版本上线</small></div>';
        return;
    }

    container.innerHTML = items.map(r => {
        return `
            <div style="margin-bottom: 20px; border-bottom: 1px solid var(--border-thin); padding-bottom: 15px;">
                <div style="color: var(--accent-blue); font-weight: 600; margin-bottom: 8px; font-size: 14px;">${r.company_name}</div>
                <div style="font-size: 12px; color: var(--text-dim); line-height: 1.6; margin-bottom: 10px;">
                    ${r.event ? r.event.split(' | ')[0] : ''}
                </div>
                <div style="background: rgba(255,255,255,0.03); padding: 8px; border-radius: 4px; font-size: 11px;">
                    <div style="color: var(--accent-gold); margin-bottom: 4px;">[价值缺口与潜力]</div>
                    ${r.impact || ''}
                </div>
            </div>
        `;
    }).join('');
}

// 快速同步
async function triggerSync() {
    const btn = document.getElementById('btn-sync');
    if (!btn) return;
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 同步中...';
    try {
        const res = await fetch(`${API_BASE}/data/sync/daily/auto`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ type: 'AUTO' })
        });
        if (res.ok) refreshDashboard();
        else Modal.alert('同步失败', '请稍后重试');
    } catch (e) {
        Modal.alert('同步失败', e.message);
    }
    btn.disabled = false;
    btn.innerHTML = '<i class="fas fa-sync"></i> 数据同步';
}

// 生成建议 (占位 — 功能将在后续版本实现)
async function triggerSuggest() {
    const btn = document.getElementById('btn-suggest');
    if (!btn) return;
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 生成中...';
    try {
        Modal.alert('提示', '调仓建议引擎将在后续版本上线。\n\n当前您可以:\n1. 在数据中心同步行情\n2. 在持仓管理查看K线\n3. 在任务定义页手动计算指标');
    } catch (e) { /* ignore */ }
    btn.disabled = false;
    btn.innerHTML = '<i class="fas fa-magic"></i> 生成调仓建议';
}

async function executeSuggestion(id) {
    const ok = await Modal.confirm('执行交易', '确认执行该笔交易？');
    if (!ok) return;
    try {
        await fetch(`${API_BASE}/suggestions/${id}/execute`, { method: 'PUT' });
        refreshDashboard();
    } catch (e) { Modal.alert('执行失败', e.message); }
}

// 暴露给 common.js 调用
window.refreshPageData = refreshDashboard;
