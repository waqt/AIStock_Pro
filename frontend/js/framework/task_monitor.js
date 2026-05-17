/**
 * 任务监控浮窗 — 右下角按钮 + 面板
 */
const TaskMonitor = {

    init() {
        this.createFloatingButton();
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

        const style = document.createElement('style');
        style.textContent = `
            #global-task-widget { position: fixed; bottom: 20px; right: 20px; z-index: 9999; }
            #task-fab { width: 48px; height: 48px; background: var(--accent-blue); color: #fff; border-radius: 50%; display: flex; align-items: center; justify-content: center; cursor: pointer; box-shadow: 0 4px 16px rgba(0,0,0,0.4); transition: all 0.3s; }
            #task-fab:hover { transform: scale(1.1); }
            #active-task-count { position: absolute; top: -4px; right: -4px; background: var(--accent-red); font-size: 10px; padding: 2px 6px; border-radius: 10px; color: #fff; }
            #task-monitor-panel { position: absolute; bottom: 60px; right: 0; width: 320px; background: var(--bg-card); border-radius: 8px; border: 1px solid var(--border-color); box-shadow: 0 8px 24px rgba(0,0,0,0.4); overflow: hidden; }
            #task-monitor-panel .panel-header { background: var(--bg-deep); padding: 12px 16px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border-color); }
            #task-monitor-panel .panel-header h3 { margin: 0; font-size: 13px; color: var(--text-normal); }
            #active-tasks-list { max-height: 400px; overflow-y: auto; padding: 8px; }
            .task-item { padding: 12px; border-bottom: 1px solid var(--border-thin); }
            .task-info { display: flex; justify-content: space-between; margin-bottom: 6px; }
            .task-name { font-weight: bold; font-size: 12px; color: var(--text-normal); }
            .task-status { font-size: 10px; padding: 2px 6px; border-radius: 4px; }
            .status-running { background: rgba(96,165,250,0.15); color: var(--accent-blue); }
            .status-pending { background: rgba(251,191,36,0.15); color: var(--accent-gold); }
            .status-stopping { background: rgba(239,68,68,0.15); color: var(--accent-red); }
            .progress-container { height: 4px; background: var(--border-color); border-radius: 2px; overflow: hidden; margin: 8px 0; }
            .progress-bar { height: 100%; background: var(--accent-green); transition: width 0.5s; }
            .task-msg { font-size: 10px; color: var(--text-dim); }
            .stop-btn { margin-top: 8px; width: 100%; padding: 4px; font-size: 10px; background: transparent; border: 1px solid var(--border-color); border-radius: 4px; cursor: pointer; color: var(--text-dim); }
            .stop-btn:hover { border-color: var(--accent-red); color: var(--accent-red); }
            .empty-state { padding: 40px; text-align: center; color: var(--text-micro); font-size: 12px; }
        `;
        document.head.appendChild(style);

        document.getElementById('task-fab').onclick = () => {
            const panel = document.getElementById('task-monitor-panel');
            const isOpen = panel.style.display === 'block';
            panel.style.display = isOpen ? 'none' : 'block';
            if (!isOpen) this.fetchActiveTasks();  // 打开时查询一次
        };
        document.getElementById('close-panel').onclick = () => {
            document.getElementById('task-monitor-panel').style.display = 'none';
        };
    },

    async fetchActiveTasks() {
        try {
            const res = await fetch('/api/system/tasks/executions/active');
            if (!res.ok) return;
            this.updateUI(await res.json());
        } catch (err) { /* ignore */ }
    },

    updateUI(tasks) {
        const list = document.getElementById('active-tasks-list');
        const badge = document.getElementById('active-task-count');
        if (!list || !badge) return;

        if (tasks.length > 0) {
            badge.innerText = tasks.length;
            badge.style.display = 'block';
            list.innerHTML = tasks.map(t => `
                <div class="task-item">
                    <div class="task-info">
                        <span class="task-name">${t.task_code}</span>
                        <span class="task-status status-${t.status.toLowerCase()}">${t.status}</span>
                    </div>
                    <div class="progress-container"><div class="progress-bar" style="width: ${t.progress}%"></div></div>
                    <div class="task-msg" title="${t.result_msg || ''}">${t.result_msg || '等待执行...'}</div>
                    ${t.status === 'RUNNING' || t.status === 'PENDING' ? `<button class="stop-btn" onclick="TaskMonitor.stopTask('${t.id}')">停止任务</button>` : ''}
                </div>`).join('');
        } else {
            badge.style.display = 'none';
            list.innerHTML = '<div class="empty-state">暂无活跃任务</div>';
        }
    },

    async stopTask(id) {
        const ok = await Modal.confirm('停止任务', '确认要停止该任务吗？');
        if (!ok) return;
        try {
            const res = await fetch(`/api/system/tasks/executions/${id}`, { method: 'DELETE' });
            if (res.ok) {
                Modal.alert('操作成功', '已发出停止信号');
            } else {
                Modal.alert('操作失败', '停止请求失败');
            }
        } catch (err) {
            Modal.alert('请求异常', err.toString());
        }
    }
};
