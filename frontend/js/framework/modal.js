/**
 * 暗色弹窗系统 (Dark Modal System)
 * 用法: Modal.alert(title, msg) / Modal.confirm(title, msg) / Modal.danger(title, msg)
 */
const Modal = {
	_ensureDOM() {
		if (document.getElementById('dark-modal-overlay')) return;
		var overlay = document.createElement('div');
		overlay.id = 'dark-modal-overlay';
		overlay.innerHTML = `
			<div id="dark-modal-box">
				<div id="dark-modal-title"></div>
				<div id="dark-modal-body"></div>
				<div id="dark-modal-actions"></div>
			</div>`;
		document.body.appendChild(overlay);
		var style = document.createElement('style');
		style.textContent = `
			#dark-modal-overlay {
				position: fixed; inset: 0; background: rgba(0,0,0,0.7);
				display: none; justify-content: center; align-items: center;
				z-index: 9999;
			}
			#dark-modal-overlay.open { display: flex; }
			#dark-modal-box {
				background: #111; padding: 16px 20px;
				border: 1px solid var(--border-color, #333);
				border-radius: 8px; min-width: 360px; max-width: 560px;
				position: relative;
			}
			#dark-modal-title { color: #fff; font-size: 13px; margin-bottom: 12px; }
			#dark-modal-body { color: var(--text-dim, #888); }
			#dark-modal-actions { margin-top: 12px; display: flex; justify-content: flex-end; gap: 6px; }
		`;
		document.head.appendChild(style);
	},

	alert(title, msg) {
		return new Promise((resolve) => {
			this._ensureDOM();
			document.getElementById('dark-modal-title').textContent = title;
			document.getElementById('dark-modal-body').innerHTML = '<div style="min-width:300px;">' + msg + '</div>';
			var actions = document.getElementById('dark-modal-actions');
			actions.innerHTML = '<button id="dark-modal-ok" style="background:var(--accent-blue,#4e9eff);color:#fff;border:none;padding:4px 18px;border-radius:4px;cursor:pointer;font-size:11px;">确定</button>';
			document.getElementById('dark-modal-overlay').classList.add('open');
			document.getElementById('dark-modal-ok').onclick = function() {
				document.getElementById('dark-modal-overlay').classList.remove('open');
				resolve(true);
			};
		});
	},

	confirm(title, msg) {
		return new Promise((resolve) => {
			this._ensureDOM();
			document.getElementById('dark-modal-title').textContent = title;
			document.getElementById('dark-modal-body').innerHTML = '<div style="min-width:300px;">' + msg + '</div>';
			var actions = document.getElementById('dark-modal-actions');
			actions.innerHTML = `
				<button id="dark-modal-no" style="background:none;border:1px solid var(--border-thin,#555);color:var(--text-dim,#888);padding:4px 14px;border-radius:4px;cursor:pointer;font-size:11px;">取消</button>
				<button id="dark-modal-yes" style="background:var(--accent-blue,#4e9eff);color:#fff;border:none;padding:4px 14px;border-radius:4px;cursor:pointer;font-size:11px;">确认</button>`;
			document.getElementById('dark-modal-overlay').classList.add('open');
			document.getElementById('dark-modal-no').onclick = function() {
				document.getElementById('dark-modal-overlay').classList.remove('open');
				resolve(false);
			};
			document.getElementById('dark-modal-yes').onclick = function() {
				document.getElementById('dark-modal-overlay').classList.remove('open');
				resolve(true);
			};
		});
	},

	danger(title, msg) {
		return new Promise((resolve) => {
			this._ensureDOM();
			document.getElementById('dark-modal-title').textContent = title;
			document.getElementById('dark-modal-body').innerHTML = '<div style="min-width:300px;">' + msg + '</div>';
			var actions = document.getElementById('dark-modal-actions');
			actions.innerHTML = `
				<button id="dark-modal-no" style="background:none;border:1px solid var(--border-thin,#555);color:var(--text-dim,#888);padding:4px 14px;border-radius:4px;cursor:pointer;font-size:11px;">取消</button>
				<button id="dark-modal-yes" style="background:var(--accent-red,#f44);color:#fff;border:none;padding:4px 14px;border-radius:4px;cursor:pointer;font-size:11px;">确认删除</button>`;
			document.getElementById('dark-modal-overlay').classList.add('open');
			document.getElementById('dark-modal-no').onclick = function() {
				document.getElementById('dark-modal-overlay').classList.remove('open');
				resolve(false);
			};
			document.getElementById('dark-modal-yes').onclick = function() {
				document.getElementById('dark-modal-overlay').classList.remove('open');
				resolve(true);
			};
		});
	},

	custom({title, content, wide}) {
		this._ensureDOM();
		var box = document.getElementById('dark-modal-box');
		box.style.maxWidth = wide ? '900px' : '560px';
		box.style.width = wide ? '900px' : '';
		box.style.minHeight = wide ? '75vh' : '';
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
