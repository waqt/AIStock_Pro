/**
 * AIStock Pro 全局基础配置与任务监控 V5.1
 */

const API_BASE = '/api'; // 统一 API 前缀

const TaskMonitor = {
    pollingInterval: 8000,
    timer: null,

    init() {
        console.log("[🚀] Task Monitor V5.1 Initializing...");
        this.createFloatingButton();
        this.startPolling();
        
        // 自动初始化页面组件 (如果页面定义了 data-page-id)
        const pageId = document.body.getAttribute('data-page-id');
        if (pageId && window.initPageComponents) {
            window.initPageComponents({ 
                activeId: pageId, 
                title: document.title.split('|')[1]?.trim() || "控制台" 
            });
        }

        // 自动触发数据加载钩子
        if (typeof window.refreshPageData === 'function') {
            console.log(`[🔄] Auto-triggering data refresh for: ${pageId}`);
            window.refreshPageData();
            // 每分钟自动刷新一次
            setInterval(window.refreshPageData, 60000);
        }
    },

    createFloatingButton() {
        if (document.getElementById('global-task-widget')) return;

        const widget = document.createElement('div');
        widget.id = 'global-task-widget';
        widget.innerHTML = `
            <div id="task-fab" title="查看运行中任务">
                <span class="icon">⚙️</span>
                <span id="active-task-count" style="display:none;">0</span>
            </div>
            <div id="task-monitor-panel" style="display:none;">
                <div class="panel-header">
                    <h3>活跃任务监控</h3>
                    <div class="header-actions">
                        <button onclick="location.href='history.html'" title="执行历史">📜</button>
                        <button id="close-panel">✖</button>
                    </div>
                </div>
                <div id="active-tasks-list">
                    <div class="empty-state">暂无活跃任务</div>
                </div>
            </div>
        `;
        document.body.appendChild(widget);

        // 样式注入
        const style = document.createElement('style');
        style.textContent = `
            #global-task-widget { position: fixed; bottom: 20px; right: 20px; z-index: 9999; }
            #task-fab {
                width: 48px; height: 48px; background: var(--accent-blue); color: #fff; border-radius: 50%;
                display: flex; align-items: center; justify-content: center; cursor: pointer;
                box-shadow: 0 4px 16px rgba(0,0,0,0.4); transition: all 0.3s;
            }
            #task-fab:hover { transform: scale(1.1); background: var(--accent-blue); filter: brightness(1.2); }
            #active-task-count {
                position: absolute; top: -4px; right: -4px; background: var(--accent-red);
                font-size: 10px; padding: 2px 6px; border-radius: 10px; color: #fff;
            }
            #task-monitor-panel {
                position: absolute; bottom: 60px; right: 0; width: 320px; background: var(--bg-card);
                border-radius: 8px; border: 1px solid var(--border-color); box-shadow: 0 8px 24px rgba(0,0,0,0.4); overflow: hidden;
            }
            #task-monitor-panel .panel-header { background: var(--bg-deep); padding: 12px 16px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border-color); }
            #task-monitor-panel .panel-header h3 { margin: 0; font-size: 13px; color: var(--text-normal); }
            #task-monitor-panel .header-actions button { border: none; background: none; cursor: pointer; font-size: 14px; margin-left: 8px; opacity: 0.6; color: var(--text-dim); }
            #task-monitor-panel .header-actions button:hover { opacity: 1; }
            #active-tasks-list { max-height: 400px; overflow-y: auto; padding: 8px; }
            #active-tasks-list .task-item { padding: 12px; border-bottom: 1px solid var(--border-thin); }
            #active-tasks-list .task-item:last-child { border-bottom: none; }
            #active-tasks-list .task-info { display: flex; justify-content: space-between; margin-bottom: 6px; }
            #active-tasks-list .task-name { font-weight: bold; font-size: 12px; color: var(--text-normal); }
            #active-tasks-list .task-status { font-size: 10px; padding: 2px 6px; border-radius: 4px; }
            #active-tasks-list .status-running { background: rgba(96,165,250,0.15); color: var(--accent-blue); }
            #active-tasks-list .status-pending { background: rgba(251,191,36,0.15); color: var(--accent-gold); }
            #active-tasks-list .status-stopping { background: rgba(239,68,68,0.15); color: var(--accent-red); }
            #active-tasks-list .progress-container { height: 4px; background: var(--border-color); border-radius: 2px; overflow: hidden; margin: 8px 0; }
            #active-tasks-list .progress-bar { height: 100%; background: var(--accent-green); transition: width 0.5s; }
            #active-tasks-list .task-msg { font-size: 10px; color: var(--text-dim); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
            #active-tasks-list .stop-btn {
                margin-top: 8px; width: 100%; padding: 4px; font-size: 10px;
                background: transparent; border: 1px solid var(--border-color); border-radius: 4px; cursor: pointer; color: var(--text-dim);
            }
            #active-tasks-list .stop-btn:hover { border-color: var(--accent-red); color: var(--accent-red); }
            #active-tasks-list .empty-state { padding: 40px; text-align: center; color: var(--text-micro); font-size: 12px; }
        `;
        document.head.appendChild(style);

        // 事件绑定
        document.getElementById('task-fab').onclick = () => {
            const panel = document.getElementById('task-monitor-panel');
            panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
        };
        document.getElementById('close-panel').onclick = () => {
            document.getElementById('task-monitor-panel').style.display = 'none';
        };
    },

    async startPolling() {
        this.fetchActiveTasks();
        this.timer = setInterval(() => this.fetchActiveTasks(), this.pollingInterval);
    },

    async fetchActiveTasks() {
        try {
            const res = await fetch('/api/system/tasks/executions/active');
            if (!res.ok) return;
            const tasks = await res.json();
            this.updateUI(tasks);
        } catch (err) {
            console.warn("Polling error:", err);
        }
    },

    updateUI(tasks) {
        const list = document.getElementById('active-tasks-list');
        const countBadge = document.getElementById('active-task-count');

        if (tasks.length > 0) {
            countBadge.innerText = tasks.length;
            countBadge.style.display = 'block';
            
            list.innerHTML = tasks.map(t => `
                <div class="task-item">
                    <div class="task-info">
                        <span class="task-name">${t.task_code}</span>
                        <span class="task-status status-${t.status.toLowerCase()}">${t.status}</span>
                    </div>
                    <div class="progress-container">
                        <div class="progress-bar" style="width: ${t.progress}%"></div>
                    </div>
                    <div class="task-msg" title="${t.result_msg || ''}">${t.result_msg || '等待执行...'}</div>
                    ${t.status === 'RUNNING' || t.status === 'PENDING' ? 
                        `<button class="stop-btn" onclick="TaskMonitor.stopTask('${t.id}')">停止任务</button>` : ''}
                </div>
            `).join('');
        } else {
            countBadge.style.display = 'none';
            list.innerHTML = '<div class="empty-state">暂无活跃任务</div>';
        }
    },

    async stopTask(id) {
        const ok = await Modal.confirm("停止任务", "确认要停止该任务吗？系统将尝试回滚未完成的数据。");
        if (!ok) return;
        try {
            const res = await fetch(`/api/system/tasks/executions/${id}`, { method: 'DELETE' });
            if (res.ok) {
                Modal.alert("操作成功", "已发出停止信号，请关注状态变化。");
            } else {
                Modal.alert("操作失败", "停止请求失败，任务可能已结束。");
            }
        } catch (err) {
            Modal.alert("请求异常", err.toString());
        }
    }
};

// ═══════════════════════════════════════════
// 暗色弹窗系统 (Dark Modal System)
// ═══════════════════════════════════════════

const Modal = {
    _overlay: null,
    _box: null,

    _ensureDOM() {
        if (document.getElementById('dark-modal-overlay')) return;
        const overlay = document.createElement('div');
        overlay.id = 'dark-modal-overlay';
        overlay.innerHTML = `
            <div id="dark-modal-box">
                <div id="dark-modal-title"></div>
                <div id="dark-modal-body"></div>
                <div id="dark-modal-actions"></div>
            </div>`;
        document.body.appendChild(overlay);

        const style = document.createElement('style');
        style.textContent = `
            #dark-modal-overlay {
                position: fixed; inset: 0; z-index: 10000;
                background: rgba(0,0,0,0.75); backdrop-filter: blur(4px);
                display: none; justify-content: center; align-items: center;
            }
            #dark-modal-overlay.open { display: flex; }
            #dark-modal-box {
                background: var(--bg-card, #0d0d0d);
                border: 1px solid var(--border-color, #222);
                border-radius: 8px; min-width: 360px; max-width: 560px;
                box-shadow: 0 16px 48px rgba(0,0,0,0.6);
                overflow: hidden;
            }
            #dark-modal-title {
                padding: 16px 20px; font-weight: 700; font-size: 14px;
                color: var(--text-normal, #fff); border-bottom: 1px solid var(--border-color, #222);
                background: rgba(255,255,255,0.02);
            }
            #dark-modal-body {
                padding: 20px; font-size: 13px; color: var(--text-dim, #a4b0be);
                line-height: 1.7; max-height: 50vh; overflow-y: auto;
                white-space: pre-wrap; font-family: var(--font-mono, monospace);
            }
            #dark-modal-actions {
                padding: 12px 20px; display: flex; justify-content: flex-end; gap: 10px;
                border-top: 1px solid var(--border-color, #222);
                background: rgba(255,255,255,0.01);
            }
            #dark-modal-actions button {
                padding: 8px 20px; border-radius: 4px; font-size: 12px; cursor: pointer;
                border: 1px solid var(--border-color, #333); font-weight: 600;
                background: transparent; color: var(--text-dim, #888);
            }
            #dark-modal-actions button.btn-modal-primary {
                background: var(--accent-blue, #70a1ff); border-color: var(--accent-blue);
                color: #000; font-weight: 700;
            }
            #dark-modal-actions button.btn-modal-danger {
                background: transparent; border-color: var(--accent-red, #ff4757);
                color: var(--accent-red);
            }
            #dark-modal-actions button:hover { filter: brightness(1.2); }
        `;
        document.head.appendChild(style);
        this._overlay = overlay;
        this._box = overlay.querySelector('#dark-modal-box');
    },

    _open(title, bodyHTML, buttons) {
        this._ensureDOM();
        document.getElementById('dark-modal-title').textContent = title;
        document.getElementById('dark-modal-body').innerHTML = bodyHTML;
        const actions = document.getElementById('dark-modal-actions');
        actions.innerHTML = '';
        buttons.forEach(([label, cls, handler]) => {
            const btn = document.createElement('button');
            btn.textContent = label;
            if (cls) btn.className = cls;
            btn.onclick = () => { this._overlay.classList.remove('open'); handler(); };
            actions.appendChild(btn);
        });
        this._overlay.classList.add('open');
    },

    alert(title, msg) {
        return new Promise(resolve => {
            this._open(title, msg, [['确定', 'btn-modal-primary', resolve]]);
        });
    },

    /** 返回 true 如果用户点确认 */
    confirm(title, msg) {
        return new Promise(resolve => {
            this._open(title, msg, [
                ['取消', '', () => resolve(false)],
                ['确认', 'btn-modal-primary', () => resolve(true)]
            ]);
        });
    },

    /** 危险操作确认 — 确认按钮红色 */
    danger(title, msg) {
        return new Promise(resolve => {
            this._open(title, msg, [
                ['取消', '', () => resolve(false)],
                ['确认删除', 'btn-modal-danger', () => resolve(true)]
            ]);
        });
    }
};

// 挂载到全局
window.Modal = Modal;

// 自动启动
document.addEventListener('DOMContentLoaded', () => TaskMonitor.init());
window.TaskMonitor = TaskMonitor; // 暴露给 onclick 使用
