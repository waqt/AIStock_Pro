/**
 * AIStock Pro 全局任务监控组件 V5.0
 * 负责：活跃任务轮询、状态显示、全局停止控制
 */

const TaskMonitor = {
    pollingInterval: 3000, // 3秒轮询一次
    timer: null,

    init() {
        console.log("[🚀] Task Monitor V5.0 Initializing...");
        this.createFloatingButton();
        this.startPolling();
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
                        <button onclick="location.href='/tasks_history.html'" title="历史审计">📜</button>
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
            #global-task-widget { position: fixed; bottom: 20px; right: 20px; z-index: 9999; font-family: sans-serif; }
            #task-fab { 
                width: 50px; height: 50px; background: #007bff; color: white; border-radius: 50%; 
                display: flex; align-items: center; justify-content: center; cursor: pointer; 
                box-shadow: 0 4px 12px rgba(0,0,0,0.15); transition: all 0.3s;
            }
            #task-fab:hover { transform: scale(1.1); background: #0056b3; }
            #active-task-count { 
                position: absolute; top: -5px; right: -5px; background: #ff4757; 
                font-size: 10px; padding: 2px 6px; border-radius: 10px; border: 2px solid white;
            }
            #task-monitor-panel { 
                position: absolute; bottom: 65px; right: 0; width: 320px; background: white; 
                border-radius: 12px; box-shadow: 0 8px 24px rgba(0,0,0,0.2); overflow: hidden;
            }
            .panel-header { background: #f8f9fa; padding: 12px 16px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #eee; }
            .panel-header h3 { margin: 0; font-size: 14px; color: #333; }
            .header-actions button { border: none; background: none; cursor: pointer; font-size: 14px; margin-left: 8px; opacity: 0.6; }
            .header-actions button:hover { opacity: 1; }
            #active-tasks-list { max-height: 400px; overflow-y: auto; padding: 8px; }
            .task-item { padding: 12px; border-bottom: 1px solid #f1f1f1; position: relative; }
            .task-item:last-child { border-bottom: none; }
            .task-info { display: flex; justify-content: space-between; margin-bottom: 6px; }
            .task-name { font-weight: bold; font-size: 13px; color: #2f3542; }
            .task-status { font-size: 11px; padding: 2px 6px; border-radius: 4px; }
            .status-running { background: #e3f2fd; color: #1976d2; }
            .status-pending { background: #fff3e0; color: #fb8c00; }
            .status-stopping { background: #ffebee; color: #d32f2f; }
            .progress-container { height: 6px; background: #f1f1f1; border-radius: 3px; overflow: hidden; margin: 8px 0; }
            .progress-bar { height: 100%; background: #2ed573; transition: width 0.5s; }
            .task-msg { font-size: 11px; color: #747d8c; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
            .stop-btn { 
                margin-top: 8px; width: 100%; padding: 4px; font-size: 11px; 
                background: #f1f2f6; border: 1px solid #dfe4ea; border-radius: 4px; cursor: pointer;
            }
            .stop-btn:hover { background: #dfe4ea; color: #ff4757; }
            .empty-state { padding: 40px; text-align: center; color: #a4b0be; font-size: 13px; }
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
        if (!confirm("确认要停止该任务吗？系统将尝试回滚未完成的数据。")) return;
        try {
            const res = await fetch(`/api/system/tasks/executions/${id}`, { method: 'DELETE' });
            if (res.ok) {
                alert("已发出停止信号，请关注状态变化。");
            } else {
                alert("停止请求失败，任务可能已结束。");
            }
        } catch (err) {
            alert("请求异常: " + err);
        }
    }
};

// 自动启动
document.addEventListener('DOMContentLoaded', () => TaskMonitor.init());
window.TaskMonitor = TaskMonitor; // 暴露给 onclick 使用
