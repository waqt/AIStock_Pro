/**
 * 健康体检 — 独立页面逻辑
 * 命名空间: HealthCheck
 * 渲染函数复用 common.js 中的 renderHealthCheckHTML()
 */

window.HealthCheck = {
    /** 运行健康体检 */
    run: function() {
        var code = document.getElementById('hc-code').value.trim();
        if (!code) { Modal.alert('提示', '请输入股票代码'); return; }

        var dims = [];
        if (document.getElementById('hc-dim-financial').checked) dims.push('financial');
        if (document.getElementById('hc-dim-technical').checked) dims.push('technical');
        if (document.getElementById('hc-dim-talent').checked) dims.push('talent');
        if (document.getElementById('hc-dim-valuation').checked) dims.push('valuation');

        var statusEl = document.getElementById('hc-status');
        var resultEl = document.getElementById('hc-result');
        var btn = document.getElementById('btn-hc');

        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 体检中...';
        statusEl.innerHTML = '<i class="fas fa-spinner fa-spin"></i> LLM 分析中 (约30-60s)...';
        resultEl.innerHTML = '<div style="text-align:center;padding:40px;color:var(--text-dim);"><i class="fas fa-spinner fa-spin" style="font-size:24px;margin-bottom:12px;"></i><div>分析中，请稍候...</div></div>';

        var body = { stock_code: code };
        if (dims.length < 4) body.dimensions = dims;

        fetch(API_BASE + '/research/health-check', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        })
        .then(function(res) {
            if (!res.ok) { return res.json().then(function(d) { throw new Error(d.detail || '请求失败'); }); }
            return res.json();
        })
        .then(function(data) {
            var result = data.data || data;
            var html = renderHealthCheckHTML ? renderHealthCheckHTML(result) :
                '<pre style="font-size:10px;color:var(--text-dim);">' + JSON.stringify(result, null, 2) + '</pre>';
            resultEl.innerHTML = html;
            statusEl.innerHTML = '✅ 体检完成';
        })
        .catch(function(e) {
            resultEl.innerHTML = '<div style="text-align:center;padding:40px;color:var(--accent-red);"><i class="fas fa-exclamation-triangle" style="font-size:24px;margin-bottom:12px;"></i><div>' + escHtml(e.message) + '</div></div>';
            statusEl.innerHTML = '❌ ' + escHtml(e.message);
        })
        .finally(function() {
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-stethoscope"></i> 开始体检';
        });
    },

    /** 回车触发 */
    init: function() {
        var input = document.getElementById('hc-code');
        if (input) {
            input.addEventListener('keydown', function(e) {
                if (e.key === 'Enter') HealthCheck.run();
            });
        }
    }
};

document.addEventListener('DOMContentLoaded', function() {
    if (window.HealthCheck) HealthCheck.init();
});
