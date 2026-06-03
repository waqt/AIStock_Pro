/**
 * 股票中心 — 全部股票 6 维数据完整度 + 批量操作
 * DataTabs.StockCenter 命名空间
 */
window.DataTabs = window.DataTabs || {};

DataTabs.StockCenter = {
  PAGE_SIZE: 100,
  currentPage: 1,
  totalStocks: 0,
  stocksData: [],         // 当前页原始数据 (过滤前)
  filteredStocks: [],     // 当前页过滤后的数据
  searchTimer: null,
  selectedCodes: new Set(),

  /** 加载并渲染 */
  async load(page) {
    this.currentPage = page || 1;
    const search = document.getElementById('sc-search')?.value?.trim() || '';
    const url = `/data/stock-center/list?page=${this.currentPage}&page_size=${this.PAGE_SIZE}${search ? '&search=' + encodeURIComponent(search) : ''}`;

    document.getElementById('sc-table-body').innerHTML = '<tr><td colspan="10" style="text-align:center;color:var(--text-micro);padding:30px;">加载中...</td></tr>';

    try {
      const resp = await API.get(url);
      if (!resp.success || !resp.data) throw new Error('API error');

      this.totalStocks = resp.data.total;
      this.stocksData = resp.data.stocks || [];
      this.selectedCodes = new Set(); // 翻页清空选中

      // 提取行业列表 (仅首次)
      this._populateIndustryFilter(this.stocksData);

      this.applyFilter();
      this.updatePagination();
    } catch (e) {
      console.error('[StockCenter] Load failed:', e);
      document.getElementById('sc-table-body').innerHTML =
        `<tr><td colspan="10" style="text-align:center;color:var(--accent-red);padding:30px;">加载失败: ${e.message}</td></tr>`;
    }
  },

  /** 填充行业下拉 */
  _populateIndustryFilter(stocks) {
    const sel = document.getElementById('sc-industry-filter');
    if (!sel || sel.options.length > 1) return;
    const industries = [...new Set(stocks.map(s => s.industry).filter(Boolean))].sort();
    industries.forEach(ind => {
      const opt = document.createElement('option');
      opt.value = ind;
      opt.textContent = ind;
      sel.appendChild(opt);
    });
  },

  /** 搜索防抖 */
  debounceSearch() {
    clearTimeout(this.searchTimer);
    this.searchTimer = setTimeout(() => {
      this.currentPage = 1;
      this.load(1);
    }, 400);
  },

  /** 客户端过滤 (在当前页上) */
  applyFilter() {
    const dimFilter = document.getElementById('sc-dim-filter')?.value || '';
    const onlyMissing = document.getElementById('sc-only-missing')?.checked || false;
    const industryFilter = document.getElementById('sc-industry-filter')?.value || '';

    let list = this.stocksData;

    if (industryFilter) list = list.filter(s => s.industry === industryFilter);
    if (dimFilter) list = list.filter(s => !s.status[dimFilter]?.ok);
    if (onlyMissing) {
      list = list.filter(s => {
        const st = s.status;
        return !st.basic_finance.ok || !st.financial_indicators.ok ||
               !st.dynamic_info.ok || !st.market_data.ok ||
               !st.price_indicators.ok || !st.industry.ok;
      });
    }

    this.filteredStocks = list;
    this._render(list);
    this._updateSelectedCount();
  },

  /** 渲染表格 */
  _render(stocks) {
    const tbody = document.getElementById('sc-table-body');
    if (!stocks || stocks.length === 0) {
      tbody.innerHTML = '<tr><td colspan="10" style="text-align:center;color:var(--text-micro);padding:30px;">无匹配股票</td></tr>';
      return;
    }

    tbody.innerHTML = stocks.map(s => {
      const st = s.status;
      const checked = this.selectedCodes.has(s.code) ? 'checked' : '';
      return `<tr>
        <td style="text-align:center;"><input type="checkbox" class="sc-checkbox" data-code="${s.code}" ${checked} onchange="DataTabs.StockCenter._onCheckChange('${s.code}', this.checked)"></td>
        <td><span style="color:#fff;font-family:var(--font-mono);">${s.code}</span></td>
        <td><span style="color:#fff;">${this._esc(s.name)}</span></td>
        <td>${this._badge(st.basic_finance, 'quarters_count')}</td>
        <td>${this._badge(st.financial_indicators, 'report_count')}</td>
        <td>${this._valBadge(st.dynamic_info)}</td>
        <td>${this._badge(st.market_data, 'days')}</td>
        <td>${this._badge(st.price_indicators, 'record_count')}</td>
        <td>${this._industryBadge(st.industry)}</td>
        <td style="text-align:center;">${s.in_position ? '<span style="color:var(--accent-cyan);"><i class="fas fa-briefcase"></i></span>' : ''}${s.in_watchlist ? '<span style="color:var(--accent-gold);margin-left:4px;"><i class="fas fa-star"></i></span>' : ''}</td>
      </tr>`;
    }).join('');
  },

  /** 维度 badge (计数) */
  _badge(dim, countField) {
    if (dim.ok) {
      const count = dim[countField] || '';
      return `<span class="sc-badge sc-badge-ok"><i class="fas fa-check-circle"></i> ${count}</span>`;
    }
    return `<span class="sc-badge sc-badge-missing"><i class="fas fa-times-circle"></i></span>`;
  },

  /** 估值 badge */
  _valBadge(dim) {
    if (dim.ok) {
      const pe = dim.pe != null ? dim.pe.toFixed(1) : '?';
      return `<span class="sc-badge sc-badge-ok">PE ${pe}</span>`;
    }
    return `<span class="sc-badge sc-badge-missing"><i class="fas fa-times-circle"></i></span>`;
  },

  /** 行业 badge */
  _industryBadge(dim) {
    if (dim.ok) {
      return `<span class="sc-badge sc-badge-ok"><i class="fas fa-tag"></i> ${this._esc(dim.name)}</span>`;
    }
    return `<span class="sc-badge sc-badge-missing"><i class="fas fa-times-circle"></i></span>`;
  },

  /** 全选 */
  selectAll() {
    const checked = document.getElementById('sc-select-all').checked;
    this.filteredStocks.forEach(s => {
      if (checked) this.selectedCodes.add(s.code);
      else this.selectedCodes.delete(s.code);
    });
    document.querySelectorAll('.sc-checkbox').forEach(cb => cb.checked = checked);
    this._updateSelectedCount();
  },

  _onCheckChange(code, checked) {
    if (checked) this.selectedCodes.add(code);
    else this.selectedCodes.delete(code);
    this._updateSelectedCount();
  },

  getSelected() { return [...this.selectedCodes]; },

  _updateSelectedCount() {
    const el = document.getElementById('sc-selected-count');
    if (el) el.textContent = `已选 ${this.selectedCodes.size} 只`;
  },

  updatePagination() {
    const totalPages = Math.max(1, Math.ceil(this.totalStocks / this.PAGE_SIZE));
    document.getElementById('sc-page-info').textContent = `${this.currentPage}/${totalPages}`;
    document.getElementById('sc-pagination').textContent = `共 ${this.totalStocks} 只股票`;
  },

  prevPage() { if (this.currentPage > 1) this.load(this.currentPage - 1); },

  nextPage() {
    const totalPages = Math.max(1, Math.ceil(this.totalStocks / this.PAGE_SIZE));
    if (this.currentPage < totalPages) this.load(this.currentPage + 1);
  },

  // ═══ 批量操作 ═══════════════════════════

  /** 批量同步行情 (走批量接口) */
  async batchSyncMarket() {
    const codes = this.getSelected();
    if (codes.length === 0) { await Modal.alert('提示', '请先勾选需要同步的股票'); return; }
    const ok = await Modal.confirm('同步行情', `确认对 ${codes.length} 只股票执行行情+估值同步?`);
    if (!ok) return;

    DataTabs.addLog(`[StockCenter] 开始批量同步: ${codes.length} 只...`);
    try {
      await API.post('/data/stock-center/batch-sync', { codes, mode: 'daily' });
      DataTabs.addLog('[StockCenter] 批量同步完成');
      await Modal.alert('同步完成', `${codes.length} 只股票已提交同步`);
    } catch (e) {
      console.error('[StockCenter] Batch sync fail:', e);
      await Modal.alert('同步失败', e.message);
    }
    this.load(this.currentPage);
  },

  /** 批量同步估值 (已有接口, 不耗时长) */
  async batchSyncValuation() {
    const codes = this.getSelected();
    if (codes.length === 0) { await Modal.alert('提示', '请先勾选需要同步的股票'); return; }
    const ok = await Modal.confirm('同步估值', `确认对 ${codes.length} 只同步估值?`);
    if (!ok) return;

    DataTabs.addLog(`[StockCenter] 开始同步估值: ${codes.length} 只...`);
    let done = 0;
    for (const code of codes) {
      try {
        await API.post(`/data/valuation/sync`, { target_codes: [code] });
        done++;
      } catch (e) {
        console.error(`[StockCenter] ${code} val sync fail:`, e);
      }
    }
    DataTabs.addLog(`[StockCenter] 估值同步: ${done}只`);
    await Modal.alert('同步完成', `${done} 只已同步`);
    this.load(this.currentPage);
  },

  /** 批量同步财务 (逐个) */
  async batchSyncFinance() {
    const codes = this.getSelected();
    if (codes.length === 0) { await Modal.alert('提示', '请先勾选需要同步的股票'); return; }
    const ok = await Modal.confirm('同步财务', `确认对 ${codes.length} 只逐个同步财报?`);
    if (!ok) return;

    DataTabs.addLog(`[StockCenter] 开始同步财务: ${codes.length} 只...`);
    let done = 0;
    for (const code of codes) {
      try {
        await API.post(`/data/financial/sync/${code}`);
        done++;
      } catch (e) {
        console.error(`[StockCenter] ${code} fin sync fail:`, e);
      }
    }
    DataTabs.addLog(`[StockCenter] 财务同步: ${done}只`);
    await Modal.alert('同步完成', `${done} 只已同步`);
    this.load(this.currentPage);
  },

  /** 批量计算价量指标 (批量接口) */
  async batchComputeIndicators() {
    const codes = this.getSelected();
    if (codes.length === 0) { await Modal.alert('提示', '请先勾选需要计算的股票'); return; }
    const ok = await Modal.confirm('计算价量指标', `确认对 ${codes.length} 只计算结果指标?`);
    if (!ok) return;

    DataTabs.addLog(`[StockCenter] 计算价量指标: ${codes.length} 只...`);
    try {
      // 批量接口使用 query params: codes=xxx,xxx&mode=incremental
      const url = `/quant/indicators/compute?codes=${codes.join(',')}&mode=incremental`;
      const resp = await fetch(`${API_BASE}${url}`, { method: 'POST' });
      const result = await resp.json();
      DataTabs.addLog('[StockCenter] 价量指标计算已提交');
      await Modal.alert('计算完成', `${codes.length} 只已提交计算`);
    } catch (e) {
      console.error('[StockCenter] Indicator compute fail:', e);
      await Modal.alert('计算失败', e.message);
    }
  },

  /** 批量计算财务指标 (支持 body target_codes) */
  async batchComputeFinancial() {
    const codes = this.getSelected();
    if (codes.length === 0) { await Modal.alert('提示', '请先勾选需要计算的股票'); return; }
    const ok = await Modal.confirm('计算财务指标', `确认对 ${codes.length} 只计算财务指标?`);
    if (!ok) return;

    DataTabs.addLog(`[StockCenter] 计算财务指标: ${codes.length} 只...`);
    try {
      const resp = await API.post('/quant/financial-indicators/compute', {
        target_codes: codes,
      });
      DataTabs.addLog('[StockCenter] 财务指标计算已提交');
      await Modal.alert('计算完成', `${codes.length} 只已提交计算`);
    } catch (e) {
      console.error('[StockCenter] Financial compute fail:', e);
      await Modal.alert('计算失败', e.message);
    }
  },

  _esc(s) {
    if (!s) return '';
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  },
};

// ═══ Tab 切换自动加载 ════════════════════
(function() {
  const origSwitch = DataTabs.switchTab;
  if (origSwitch) {
    DataTabs.switchTab = function(tab) {
      origSwitch(tab);
      if (tab === 'stock-center') {
        DataTabs.StockCenter.load(1);
      }
    };
  }
})();
