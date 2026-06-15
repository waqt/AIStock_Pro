/**
 * StockSearch — 股票代码联想搜索组件
 * 预加载全量股票列表到本地，输入时本地过滤，0 网络延迟。
 * 基于 HTML5 datalist, 选中后记录 stockName 到 input.dataset
 *
 * 用法:
 *   StockSearch.attach('input-id');
 *   StockSearch.attach('input-id', { onSelect: function(code, name) {} });
 *   var name = document.getElementById('input-id').dataset.stockName;
 */
(function() {
    'use strict';

    var STOCK_LIST = null;       // 全量缓存 [{code, name}]
    var LOADING = false;
    var CALLBACKS = [];          // 等待加载完成的回调

    function loadStockList(cb) {
        if (STOCK_LIST) { cb(STOCK_LIST); return; }
        CALLBACKS.push(cb);
        if (LOADING) return;
        LOADING = true;
        fetch(API_BASE + '/data/stock-list/search?q=&limit=9999')
            .then(function(r) { return r.json(); })
            .then(function(items) {
                STOCK_LIST = items || [];
                var pending = CALLBACKS.slice();
                CALLBACKS = [];
                pending.forEach(function(fn) { fn(STOCK_LIST); });
            })
            .catch(function() {
                STOCK_LIST = [];
                var pending = CALLBACKS.slice();
                CALLBACKS = [];
                pending.forEach(function(fn) { fn(STOCK_LIST); });
            });
    }

    window.StockSearch = {

        /**
         * 为指定 input 绑定股票代码联想搜索
         * @param {string} inputId - input 元素 ID
         * @param {object} opts - { onSelect: function(code, name) }
         */
        attach: function(inputId, opts) {
            opts = opts || {};
            var input = document.getElementById(inputId);
            if (!input) {
                console.warn('[StockSearch] Input not found:', inputId);
                return;
            }

            // 创建 datalist
            var listId = 'ss-list-' + inputId;
            var list = document.getElementById(listId);
            if (!list) {
                list = document.createElement('datalist');
                list.id = listId;
                input.parentNode.insertBefore(list, input.nextSibling);
            }
            input.setAttribute('list', listId);

            // 统一样式
            if (!input.style.backgroundColor || input.style.backgroundColor === 'rgba(0, 0, 0, 0)') {
                input.style.background = '#000';
                input.style.border = input.style.border || '1px solid var(--border-color)';
                input.style.color = input.style.color || '#fff';
                input.style.padding = input.style.padding || '8px 10px';
                input.style.borderRadius = input.style.borderRadius || '4px';
                input.style.fontSize = input.style.fontSize || '13px';
            }

            var timer = null;

            // 输入时本地过滤
            input.addEventListener('input', function() {
                var q = this.value.trim().toLowerCase();
                if (q.length < 1) { list.innerHTML = ''; return; }
                if (timer) clearTimeout(timer);
                timer = setTimeout(function() {
                    var items;
                    if (!STOCK_LIST) {
                        // 尚未加载完成，用 API 兜底
                        fetch(API_BASE + '/data/stock-list/search?q=' + encodeURIComponent(q) + '&limit=20')
                            .then(function(r) { return r.json(); })
                            .then(function(res) { renderList(list, res); })
                            .catch(function() {});
                        return;
                    }
                    items = STOCK_LIST.filter(function(i) {
                        return i.code.indexOf(q) >= 0 || (i.name && i.name.toLowerCase().indexOf(q) >= 0);
                    }).slice(0, 20);
                    renderList(list, items);
                }, 50); // 短防抖，本地过滤很快
            });

            // 选中时记录名称到 dataset
            input.addEventListener('change', function() {
                var val = this.value.trim();
                if (!val) return;
                var optsEl = list.querySelectorAll('option');
                for (var i = 0; i < optsEl.length; i++) {
                    if (optsEl[i].value === val) {
                        this.dataset.stockName = optsEl[i].getAttribute('data-name') || '';
                        if (opts.onSelect) opts.onSelect(val, this.dataset.stockName);
                        break;
                    }
                }
            });

            // 预加载股票列表
            loadStockList(function() {});
        }
    };

    function renderList(list, items) {
        list.innerHTML = items.map(function(i) {
            return '<option value="' + i.code + '" data-name="' + (i.name || '') + '">' + i.code + ' - ' + (i.name || '?') + '</option>';
        }).join('');
    }
})();
