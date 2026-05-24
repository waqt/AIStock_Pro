/**
 * 暗色弹窗系统 (Dark Modal System)
 * 用法: Modal.alert(title, msg) / Modal.confirm(title, msg) / Modal.danger(title, msg)
 */
const Modal = {
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
    },

    _open(title, bodyHTML, buttons) {
        this._ensureDOM();
        document.getElementById('dark-modal-title').textContent = title;
        document.getElementById('dark-modal-body').innerHTML = bodyHTML;
        const actions = document.getElementById('dark-modal-actions');
        actions.innerHTML = '';
        const overlay = document.getElementById('dark-modal-overlay');
        buttons.forEach(([label, cls, handler]) => {
            const btn = document.createElement('button');
            btn.textContent = label;
            if (cls) btn.className = cls;
            btn.onclick = () => { overlay.classList.remove('open'); handler(); };
            actions.appendChild(btn);
        });
        overlay.classList.add('open');
    },

    alert(title, msg) {
        return new Promise(resolve => {
            this._open(title, msg, [['确定', 'btn-modal-primary', resolve]]);
        });
    },

    confirm(title, msg) {
        return new Promise(resolve => {
            this._open(title, msg, [
                ['取消', '', () => resolve(false)],
                ['确认', 'btn-modal-primary', () => resolve(true)]
            ]);
        });
    },

    danger(title, msg) {
        return new Promise(resolve => {
            this._open(title, msg, [
                ['取消', '', () => resolve(false)],
                ['确认删除', 'btn-modal-danger', () => resolve(true)]
            ]);
        });
    },

    custom({title, content}) {
        this._ensureDOM();
        document.getElementById('dark-modal-title').textContent = title;
        document.getElementById('dark-modal-body').innerHTML = content;
        document.getElementById('dark-modal-actions').innerHTML = '';
        document.getElementById('dark-modal-overlay').classList.add('open');
    },

    close() {
        var overlay = document.getElementById('dark-modal-overlay');
        if (overlay) overlay.classList.remove('open');
    }
};
