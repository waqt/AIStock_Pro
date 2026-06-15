/**
 * 健康体检 — 独立页面逻辑
 * 命名空间: HealthCheck
 * 渲染函数复用 common.js 中的 renderHealthCheckHTML()
 */

window.HealthCheck = {
    _page: 0,
    _pageSize: 30,
    _total: 0,
    _records: [],
    _currentRecordId: null,

    /** ═══ Tab 切换 ═══ */
    switchTab: function(tab) {
        document.querySelectorAll('.hc-tab').forEach(function(el) {
            el.classList.toggle('active', el.dataset.tab === tab);
        });
        document.querySelectorAll('.hc-tab-content').forEach(function(el) {
            el.classList.toggle('active', el.id === 'hc-tab-' + tab);
        });
        if (tab === 'history') {
            HealthCheck._page = 0;
            HealthCheck.loadHistory();
        }
    },

    /** ═══ 运行健康体检 ═══ */
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
            var html = window.renderHealthCheckHTML ? window.renderHealthCheckHTML(result) :
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

    /** ═══ 加载历史列表 ═══ */
    loadHistory: function() {
        var filter = document.getElementById('hc-history-filter').value.trim();
        var params = '?limit=' + HealthCheck._pageSize + '&offset=' + (HealthCheck._page * HealthCheck._pageSize);
        if (filter) params += '&stock_code=' + encodeURIComponent(filter);

        var listEl = document.getElementById('hc-history-list');
        listEl.innerHTML = '<div style="text-align:center;padding:20px;color:var(--text-dim);"><i class="fas fa-spinner fa-spin"></i> 加载中...</div>';

        fetch(API_BASE + '/research/health-check/history' + params)
        .then(function(res) {
            if (!res.ok) throw new Error('加载失败');
            return res.json();
        })
        .then(function(data) {
            HealthCheck._records = data.records || [];
            HealthCheck._total = data.total || 0;
            HealthCheck._currentRecordId = null;
            HealthCheck._renderHistoryList();
        })
        .catch(function(e) {
            listEl.innerHTML = '<div style="text-align:center;padding:20px;color:var(--accent-red);font-size:11px;">❌ ' + escHtml(e.message) + '</div>';
        });
    },

    /** ═══ 渲染历史列表 ═══ */
    _renderHistoryList: function() {
        var listEl = document.getElementById('hc-history-list');
        var footerEl = document.getElementById('hc-history-footer');

        if (!HealthCheck._records.length) {
            listEl.innerHTML = '<div style="text-align:center;padding:30px;color:var(--text-micro);font-size:11px;">' +
                '<i class="fas fa-inbox" style="font-size:24px;margin-bottom:8px;display:block;opacity:0.3;"></i>' +
                '暂无体检记录</div>';
            footerEl.style.display = 'none';
            return;
        }

        var vcMap = { BUY:'var(--accent-green)', HOLD:'var(--accent-gold)', SELL:'var(--accent-red)', WATCH:'var(--accent-blue)' };
        var vcBg  = { BUY:'rgba(76,175,80,0.15)', HOLD:'rgba(255,193,7,0.15)', SELL:'rgba(244,67,54,0.15)', WATCH:'rgba(33,150,243,0.15)' };

        var html = '';
        for (var i = 0; i < HealthCheck._records.length; i++) {
            var r = HealthCheck._records[i];
            var active = (r.id === HealthCheck._currentRecordId) ? ' active' : '';
            var vColor = vcMap[r.verdict] || 'var(--text-dim)';
            var vBg = vcBg[r.verdict] || 'rgba(255,255,255,0.05)';
            var timeStr = r.created_at ? r.created_at.replace('T', ' ').substring(0, 16) : '';
            html += '<div class="hc-history-item' + active + '" data-id="' + r.id + '" onclick="HealthCheck.viewRecord(\'' + r.id + '\')">' +
                '<span class="hci-code">' + escHtml(r.stock_code) + '</span>' +
                '<span class="hci-name">' + escHtml(r.stock_name || '') + '</span>' +
                '<span class="hci-verdict" style="color:' + vColor + ';background:' + vBg + ';">' + escHtml(r.verdict || '?') + '</span>' +
                '<span class="hci-time">' + timeStr + '</span>' +
                '<span class="hci-del" onclick="event.stopPropagation();HealthCheck.deleteRecord(\'' + r.id + '\')" title="删除">✕</span>' +
                '</div>';
        }
        listEl.innerHTML = html;

        // 分页
        var totalPages = Math.ceil(HealthCheck._total / HealthCheck._pageSize) || 1;
        var curPage = HealthCheck._page + 1;
        footerEl.style.display = 'block';
        document.getElementById('hc-history-page-info').textContent = '第 ' + curPage + '/' + totalPages + ' 页 (共 ' + HealthCheck._total + ' 条)';
        document.getElementById('hc-history-prev').disabled = HealthCheck._page <= 0;
        document.getElementById('hc-history-next').disabled = curPage >= totalPages;
    },

    /** ═══ 查看单条记录详情 ═══ */
    viewRecord: function(recordId) {
        HealthCheck._currentRecordId = recordId;
        // 高亮列表项
        document.querySelectorAll('.hc-history-item').forEach(function(el) {
            el.classList.toggle('active', el.dataset.id === recordId);
        });

        var resultEl = document.getElementById('hc-result');
        resultEl.innerHTML = '<div style="text-align:center;padding:40px;color:var(--text-dim);"><i class="fas fa-spinner fa-spin" style="font-size:24px;margin-bottom:12px;"></i><div>加载详情...</div></div>';

        fetch(API_BASE + '/research/health-check/history/' + recordId)
        .then(function(res) {
            if (!res.ok) throw new Error('记录不存在');
            return res.json();
        })
        .then(function(data) {
            var record = data.data || {};
            var result = record.result || {};
            var html = window.renderHealthCheckHTML ? window.renderHealthCheckHTML(result) :
                '<pre style="font-size:10px;color:var(--text-dim);">' + JSON.stringify(result, null, 2) + '</pre>';
            // 添加返回按钮
            var headerHtml = '<div class="hc-back-link" onclick="HealthCheck.showHistoryOnly()">' +
                '<i class="fas fa-arrow-left"></i> 返回历史列表</div>';
            resultEl.innerHTML = headerHtml + html;
        })
        .catch(function(e) {
            resultEl.innerHTML = '<div style="text-align:center;padding:40px;color:var(--accent-red);">❌ ' + escHtml(e.message) + '</div>';
        });
    },

    /** ═══ 返回历史列表（不切 tab） ═══ */
    showHistoryOnly: function() {
        HealthCheck._currentRecordId = null;
        document.querySelectorAll('.hc-history-item').forEach(function(el) {
            el.classList.remove('active');
        });
        var resultEl = document.getElementById('hc-result');
        resultEl.innerHTML = '<div class="empty-state"><div class="icon">&#128138;</div><div>选择左侧历史记录查看详情</div></div>';
    },

    /** ═══ 删除记录 ═══ */
    deleteRecord: function(recordId) {
        Modal.danger('确认删除', '确定要删除这条体检记录吗？')
        .then(function(ok) {
            if (!ok) return;
            fetch(API_BASE + '/research/health-check/history/' + recordId, { method: 'DELETE' })
            .then(function(res) {
                if (!res.ok) throw new Error('删除失败');
                // 如果是当前查看的记录，清空右侧
                if (HealthCheck._currentRecordId === recordId) {
                    HealthCheck.showHistoryOnly();
                }
                // 刷新列表
                HealthCheck.loadHistory();
            })
            .catch(function(e) {
                Modal.alert('错误', '删除失败: ' + e.message);
            });
        });
    },

    /** ═══ 分页 ═══ */
    prevPage: function() {
        if (HealthCheck._page > 0) {
            HealthCheck._page--;
            HealthCheck.loadHistory();
        }
    },
    nextPage: function() {
        var totalPages = Math.ceil(HealthCheck._total / HealthCheck._pageSize) || 1;
        if (HealthCheck._page + 1 < totalPages) {
            HealthCheck._page++;
            HealthCheck.loadHistory();
        }
    },

    /** ═══ 回车触发 + 联想搜索 ═══ */
    init: function() {
        var input = document.getElementById('hc-code');
        if (input) {
            input.addEventListener('keydown', function(e) {
                if (e.key === 'Enter') HealthCheck.run();
            });
        }
        StockSearch.attach('hc-code');
    }
};

document.addEventListener('DOMContentLoaded', function() {
    if (window.HealthCheck) HealthCheck.init();
});
