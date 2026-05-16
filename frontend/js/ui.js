/**
 * UI 组件模块 - 负责动态注入通用 UI 元素 (侧边栏, 顶栏, 任务监控)
 */

const UI_COMPONENTS = {
    // 侧边栏组件
    sidebar: (activeItem) => {
        const menuItems = [
            { id: 'index', icon: 'fas fa-terminal', label: '指挥部概览', url: 'index.html' },
            { id: 'positions', icon: 'fas fa-search-dollar', label: '持仓管理', url: 'positions.html' },
            { id: 'suggestions', icon: 'fas fa-exchange-alt', label: '调仓建议', url: 'suggestions.html' },
            { id: 'research', icon: 'fas fa-brain', label: 'AI 投研', url: 'research.html' },
            { id: 'history', icon: 'fas fa-history', label: '交易审计', url: 'history.html' },
            { id: 'data', icon: 'fas fa-server', label: '数据中心', url: 'data.html' },
            { id: 'import', icon: 'fas fa-file-import', label: '智能导入', url: 'import.html' }
        ];

        let html = `
            <div class="brand-area">
                <div class="brand-title">AI STOCK</div>
            </div>
            <div class="nav-list">
        `;

        menuItems.forEach(item => {
            const isActive = activeItem === item.id ? 'active' : '';
            html += `
                <div class="nav-item ${isActive}" onclick="location.href='${item.url}'">
                    <i class="${item.icon}"></i><span>${item.label}</span>
                </div>
            `;
        });

        html += `
            </div>
            <div style="margin-top: auto;">
                <div class="nav-item" id="nav-settings"><i class="fas fa-cog"></i><span>系统设置</span></div>
            </div>
        `;
        return html;
    },

    // 顶栏组件
    topbar: (title = "") => {
        return `
            <div class="top-bar-left">
                <h2 class="page-title">${title}</h2>
            </div>
            <div class="status-group">
                <div id="page-stats" style="display: flex; gap: 20px;"></div>
                <div class="status-item">
                    <span class="status-label">账户总资产:</span>
                    <span class="status-value" id="total-assets">¥0.00</span>
                </div>
                <div class="status-item">
                    <span class="status-label">当日盈亏:</span>
                    <span class="status-value" id="today-profit">¥0.00</span>
                </div>
                <div class="status-item">
                    <span class="status-label">AI 状态:</span>
                    <span class="status-value" id="ai-status" style="color: var(--accent-green);">在线</span>
                </div>
            </div>
            <div class="top-bar-actions">
                <button class="btn-action" onclick="triggerSync()" id="btn-sync"><i class="fas fa-sync"></i> 同步</button>
                <button class="btn-action btn-primary" onclick="triggerSuggest()" id="btn-suggest"><i class="fas fa-magic"></i> 建议</button>
            </div>
        `;
    },

    // 任务监控组件
    taskMonitor: () => {
        return `
            <div class="task-panel" id="task-panel" style="display: none;">
                <div class="task-panel-header">
                    <span style="font-weight: 600;">运行中任务</span>
                    <i class="fas fa-times" style="cursor: pointer;" onclick="toggleTaskPanel()"></i>
                </div>
                <div class="task-list" id="task-list">
                    <div style="padding: 20px; text-align: center; color: var(--text-micro);">暂无运行中任务</div>
                </div>
            </div>
            <div class="task-button" id="task-btn" onclick="toggleTaskPanel()">
                <i class="fas fa-tasks"></i>
                <span class="task-badge" id="task-badge" style="display: none;"></span>
            </div>
        `;
    }
};

/**
 * 初始化页面组件
 * @param {Object} options { activeId, title }
 */
function initPageComponents(options = {}) {
    const { activeId, title } = options;
    
    // 注入侧边栏
    const sidebarEl = document.querySelector('.sidebar');
    if (sidebarEl) {
        sidebarEl.innerHTML = UI_COMPONENTS.sidebar(activeId);
    }

    // 注入顶栏
    const topbarEl = document.querySelector('.top-bar');
    if (topbarEl) {
        topbarEl.innerHTML = UI_COMPONENTS.topbar(title);
    }

    // 注入任务监控
    let monitorEl = document.querySelector('.task-monitor');
    if (!monitorEl) {
        monitorEl = document.createElement('div');
        monitorEl.className = 'task-monitor';
        document.body.appendChild(monitorEl);
    }
    monitorEl.innerHTML = UI_COMPONENTS.taskMonitor();
}

// 导出到全局
window.initPageComponents = initPageComponents;
