/**
 * 股票中心 — 全部股票 6 维数据完整度 + 批量操作
 * DataTabs.StockCenter 命名空间
 */
window.DataTabs = window.DataTabs || {};

DataTabs.StockCenter = {
  PAGE_SIZE: 100,
  currentPage: 1,
  totalStocks: 0,
  selectedCodes: new Set(),
  _dimStates: {},      // { dim: '' | 'has' | 'missing' }
  _wlFilter: '',       // '' | 'watchlist' | 'non_watchlist'

  /** 加载并渲染 (服务端排序/筛选/分页) */
  async load(page) {
    this.currentPage = page || 1;
    const params = this._buildParams();
    const url = `/data/stock-center/list?${this._toQueryString(params)}`;

    document.getElementById('sc-table-body').innerHTML =
      '<tr><td colspan="10" style="text-align:center;color:var(--text-micro);padding:30px;">加载中...</td></tr>';

    try {
      const resp = await API.get(url);
      if (!resp.success || !resp.data) throw new Error('API error');

      this.totalStocks = resp.data.total;
      this.selectedCodes = new Set();

      // 统计概览
      if (resp.data.summary) this._renderSummary(resp.data.summary);

      // 填充行业下拉 (仅首次)
      this._populateIndustryFilter(resp.data.stocks);

      this._render(resp.data.stocks);
      this.updatePagination();
    } catch (e) {
      console.error('[StockCenter] Load failed:', e);
      document.getElementById('sc-table-body').innerHTML =
        `<tr><td colspan="10" style="text-align:center;color:var(--accent-red);padding:30px;">加载失败: ${e.message}</td></tr>`;
    }
  },

  /** 构造 API 查询参数 */
  _buildParams() {
    const params = {
      page: this.currentPage,
      page_size: this.PAGE_SIZE,
    };

    // 搜索
    const search = document.getElementById('sc-search')?.value?.trim();
    if (search) params.search = search;

    // 排序
    const sortVal = document.getElementById('sc-sort')?.value || 'code_asc';
    const parts = sortVal.split('_');
    params.sort_by = parts[0] || 'code';
    params.sort_order = parts[1] || 'asc';

    // 行业
    const industry = document.getElementById('sc-industry-filter')?.value;
    if (industry) params.industry = industry;

    // 维度复选: 从 toggle chips 读取
    var hasAny = false;
    for (const [dim, state] of Object.entries(this._dimStates)) {
      if (state === 'has') { params[`has_${dim}`] = 'true'; hasAny = true; }
      else if (state === 'missing') { params[`has_${dim}`] = 'false'; hasAny = true; }
    }

    // 自选股筛选
    if (this._wlFilter) params.watchlist_filter = this._wlFilter;

    // "仅显示缺数据的" 快捷开关 → 全部缺 (仅在未设置任何维度时生效)
    const onlyMissing = document.getElementById('sc-only-missing')?.checked;
    if (onlyMissing && !hasAny) {
      const DIMS = ['basic_finance', 'financial_indicators', 'dynamic_info',
                    'market_data', 'price_indicators', 'industry'];
      DIMS.forEach(d => { params[`has_${d}`] = 'false'; });
    }

    return params;
  },

  /** 对象 → URL 查询字符串 */
  _toQueryString(params) {
    return Object.entries(params)
      .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
      .join('&');
  },

  /** 渲染统计概览卡片 */
  _renderSummary(summary) {
    const bar = document.getElementById('sc-summary-bar');
    if (!bar) return;
    bar.style.display = 'flex';

    // 维度映射: key → { label, color, icon }
    const DIM_MAP = {
      total_stocks:       { label: '总计',      icon: 'fa-database', color: '#fff' },
      market_data:        { label: '有行情',     icon: 'fa-chart-line', color: 'var(--accent-green)' },
      basic_finance:      { label: '有财务报表',  icon: 'fa-file-invoice', color: 'var(--accent-cyan)' },
      dynamic_info:       { label: '有动态信息',  icon: 'fa-tag', color: 'var(--accent-gold)' },
      industry:           { label: '有行业分类',  icon: 'fa-industry', color: 'var(--accent-blue)' },
      financial_indicators: { label: '有财务指标', icon: 'fa-calculator', color: 'var(--accent-purple)' },
      price_indicators:   { label: '有价量指标',  icon: 'fa-microchip', color: '#f59e0b' },
    };

    // 保留总计卡片, 更新或追加维度卡片
    const existingTotal = bar.querySelector('[data-key="total_stocks"]');
    if (existingTotal) {
      existingTotal.querySelector('.sc-summary-num').textContent =
        summary.total_stocks.toLocaleString();
    }

    for (const [key, dim] of Object.entries(DIM_MAP)) {
      if (key === 'total_stocks') continue;
      const cov = summary.dim_coverage?.[key];
      if (!cov) continue;
      const ok = cov.ok || 0;
      const total = cov.total || summary.total_stocks;
      const pct = total > 0 ? (ok / total * 100).toFixed(1) : '0.0';
      const color = ok === total ? 'var(--accent-green)' : ok > total * 0.5 ? 'var(--accent-gold)' : 'var(--accent-red)';

      let card = bar.querySelector(`[data-key="${key}"]`);
      if (!card) {
        card = document.createElement('div');
        card.className = 'sc-summary-card';
        card.dataset.key = key;
        card.style.cssText = 'padding:4px 12px;min-width:70px;text-align:center;';
        card.innerHTML = `
          <div class="sc-summary-num" style="font-size:16px;font-weight:600;font-family:var(--font-mono);"></div>
          <div class="sc-summary-label" style="font-size:8px;color:var(--text-micro);margin-top:1px;display:flex;align-items:center;justify-content:center;gap:3px;">
            <i class="fas ${dim.icon}" style="font-size:8px;"></i> ${dim.label}
          </div>
          <div class="sc-summary-sub" style="font-size:8px;margin-top:1px;"></div>
        `;
        bar.appendChild(card);
      }

      const numEl = card.querySelector('.sc-summary-num');
      const subEl = card.querySelector('.sc-summary-sub');
      numEl.textContent = ok.toLocaleString();
      numEl.style.color = color;
      subEl.textContent = `${pct}% · ${total.toLocaleString()} 只`;
      subEl.style.color = 'var(--text-micro)';
    }
  },

  /** 填充行业下拉 (增量添加, 不覆盖已有) */
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
    this.searchTimer = setTimeout(() => { this.load(1); }, 400);
  },

  /** 任意筛选/排序变化 → 重载第1页 */
  applyFilter() {
    this.load(1);
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
        <td><span style="color:#fff;font-family:var(--font-mono);">${this._esc(s.code)}</span></td>
        <td><span style="color:#fff;">${this._esc(s.name)}</span></td>
        <td>${this._badge(st.basic_finance, 'quarters_count')}</td>
        <td>${this._badge(st.financial_indicators, 'report_count')}</td>
        <td>${this._valBadge(st.dynamic_info)}</td>
        <td>${this._badge(st.market_data, 'days')}</td>
        <td>${this._badge(st.price_indicators, 'record_count')}</td>
        <td>${this._industryBadge(st.industry)}</td>
        <td style="text-align:center;">${s.in_position ? '<span style="color:var(--accent-cyan);"><i class="fas fa-briefcase"></i></span>' : ''}${s.in_watchlist ? '<span style="color:var(--accent-gold);margin-left:4px;"><i class="fas fa-star"></i></span>' : ''}
          ${s.completeness != null ? `<span style="font-size:8px;color:var(--text-micro);display:block;">${s.completeness}/6</span>` : ''}</td>
      </tr>`;
    }).join('');
  },

  /** 维度 badge */
  _badge(dim, countField) {
    if (dim.ok) {
      const count = dim[countField] || '';
      return `<span class="sc-badge sc-badge-ok"><i class="fas fa-check-circle"></i> ${count}</span>`;
    }
    return `<span class="sc-badge sc-badge-missing"><i class="fas fa-times-circle"></i></span>`;
  },

  _valBadge(dim) {
    if (dim.ok) {
      const pe = dim.pe != null ? dim.pe.toFixed(1) : '?';
      return `<span class="sc-badge sc-badge-ok">PE ${pe}</span>`;
    }
    return `<span class="sc-badge sc-badge-missing"><i class="fas fa-times-circle"></i></span>`;
  },

  _industryBadge(dim) {
    if (dim.ok) {
      return `<span class="sc-badge sc-badge-ok"><i class="fas fa-tag"></i> ${this._esc(dim.name)}</span>`;
    }
    return `<span class="sc-badge sc-badge-missing"><i class="fas fa-times-circle"></i></span>`;
  },

  /** 全选 */
  selectAll() {
    const checked = document.getElementById('sc-select-all').checked;
    document.querySelectorAll('.sc-checkbox').forEach(cb => {
      cb.checked = checked;
      if (checked) this.selectedCodes.add(cb.dataset.code);
      else this.selectedCodes.delete(cb.dataset.code);
    });
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

  async batchSyncMarket() {
    const codes = this.getSelected();
    if (codes.length === 0) { await Modal.alert('提示', '请先勾选需要同步的股票'); return; }
    const ok = await Modal.confirm('同步行情', `确认对 ${codes.length} 只股票执行行情同步?`);
    if (!ok) return;
    DataTabs.Core.addLog(`[StockCenter] 开始同步行情: ${codes.length} 只...`);
    try {
      const r = await SyncAPI.market(codes, 'smart');
      DataTabs.Core.addLog(`[StockCenter] 同步行情完成: ${r.synced || 0} 条新记录`);
      await Modal.alert('同步完成', `${codes.length} 只, ${r.synced || 0} 条新K线`);
    } catch (e) {
      console.error('[StockCenter] Market sync fail:', e);
      await Modal.alert('同步失败', e.message);
    }
    this.load(this.currentPage);
  },

  async batchSyncMarketFull() {
    const codes = this.getSelected();
    if (codes.length === 0) { await Modal.alert('提示', '请先勾选需要同步的股票'); return; }
    const ok = await Modal.confirm('覆盖同步', `确认对 ${codes.length} 只执行全量覆盖? 将删除历史数据重新插入。`);
    if (!ok) return;
    DataTabs.Core.addLog(`[StockCenter] 覆盖同步行情: ${codes.length} 只...`);
    try {
      const r = await SyncAPI.market(codes, 'full');
      DataTabs.Core.addLog(`[StockCenter] 覆盖同步完成: ${r.synced || 0} 条记录`);
      await Modal.alert('覆盖完成', `${codes.length} 只, ${r.synced || 0} 条K线`);
    } catch (e) {
      console.error('[StockCenter] Market full sync fail:', e);
      await Modal.alert('同步失败', e.message);
    }
    this.load(this.currentPage);
  },

  async batchSyncValuation() {
    const codes = this.getSelected();
    if (codes.length === 0) { await Modal.alert('提示', '请先勾选需要同步的股票'); return; }
    const ok = await Modal.confirm('同步估值', `确认对 ${codes.length} 只同步估值?`);
    if (!ok) return;
    DataTabs.Core.addLog(`[StockCenter] 开始同步估值: ${codes.length} 只...`);
    try {
      const r = await SyncAPI.valuation(codes);
      DataTabs.Core.addLog(`[StockCenter] 估值同步: ${r.synced || 0}只`);
      await Modal.alert('同步完成', `${r.synced || 0} 只已同步`);
    } catch (e) {
      console.error('[StockCenter] Valuation sync fail:', e);
      await Modal.alert('同步失败', e.message);
    }
    this.load(this.currentPage);
  },

  async batchSyncFinance() {
    const codes = this.getSelected();
    if (codes.length === 0) { await Modal.alert('提示', '请先勾选需要同步的股票'); return; }
    const ok = await Modal.confirm('同步财务', `确认对 ${codes.length} 只同步财报?`);
    if (!ok) return;
    DataTabs.Core.addLog(`[StockCenter] 开始同步财务: ${codes.length} 只...`);
    try {
      const r = await SyncAPI.financial(codes, 'smart');
      const stored = r.stored || 0;
      DataTabs.Core.addLog(`[StockCenter] 财务同步: ${stored} 季度`);
      await Modal.alert('同步完成', `${codes.length} 只, ${stored} 季度`);
    } catch (e) {
      console.error('[StockCenter] Financial sync fail:', e);
      await Modal.alert('同步失败', e.message);
    }
    this.load(this.currentPage);
  },

  async batchComputeIndicators() {
    const codes = this.getSelected();
    if (codes.length === 0) { await Modal.alert('提示', '请先勾选需要计算的股票'); return; }
    const ok = await Modal.confirm('计算价量指标', `确认对 ${codes.length} 只计算结果指标?`);
    if (!ok) return;
    DataTabs.Core.addLog(`[StockCenter] 计算价量指标: ${codes.length} 只...`);
    try {
      const resp = await API.post(`/quant/indicators/compute?codes=${codes.join(',')}&mode=incremental`, {});
      const d = resp.data || {};
      const msg = d.message || `已提交 ${codes.length} 只`;
      DataTabs.Core.addLog(`[StockCenter] 价量指标: ${msg}`);
      await Modal.alert('计算完成', `${codes.length} 只已提交`);
    } catch (e) {
      console.error('[StockCenter] Indicator compute fail:', e);
      DataTabs.Core.addLog(`[StockCenter] 价量指标计算失败: ${e.message}`, 'error');
      await Modal.alert('计算失败', e.message);
    }
  },

  async batchComputeFinancial() {
    const codes = this.getSelected();
    if (codes.length === 0) { await Modal.alert('提示', '请先勾选需要计算的股票'); return; }
    const ok = await Modal.confirm('计算财务指标', `确认对 ${codes.length} 只计算财务指标?`);
    if (!ok) return;
    DataTabs.Core.addLog(`[StockCenter] 计算财务指标: ${codes.length} 只...`);
    try {
      const resp = await API.post('/quant/financial-indicators/compute', { target_codes: codes });
      const d = resp.data || {};
      const okCount = d.computed || 0;
      const total = d.total || 0;
      DataTabs.Core.addLog(`[StockCenter] 财务指标: ${okCount}/${total} 完成`);
      // 显示每只结果摘要
      const results = d.results || [];
      results.forEach(function(r) {
        if (r.status === 'ok') {
          DataTabs.Core.addLog(`  ${r.code}: ${r.periods}期 OK  ROIC=${r.roic_pct != null ? r.roic_pct + '%' : '?'}`);
        } else if (r.status === 'skipped') {
          DataTabs.Core.addLog(`  ${r.code}: 跳过 (${r.reason})`);
        } else if (r.status === 'error') {
          DataTabs.Core.addLog(`  ${r.code}: 失败 (${r.reason})`, 'error');
        }
      });
      const summary = okCount > 0 ? `${okCount} 只完成` : '无有效数据';
      await Modal.alert('计算完成', `${codes.length} 只提交, ${summary}`);
    } catch (e) {
      console.error('[StockCenter] Financial compute fail:', e);
      DataTabs.Core.addLog(`[StockCenter] 财务指标计算失败: ${e.message}`, 'error');
      await Modal.alert('计算失败', e.message);
    }
  },

  /** ═══ 维度 toggle: 不限 → 有 → 缺 → 不限 ═══ */
  toggleDim(dim) {
    console.log('[StockCenter] toggleDim called:', dim);
    const cur = this._dimStates[dim] || '';
    const next = cur === '' ? 'has' : cur === 'has' ? 'missing' : '';
    this._dimStates[dim] = next;
    console.log('[StockCenter] _dimStates:', JSON.stringify(this._dimStates));

    // 更新 chip 样式
    const chip = document.querySelector(`.sc-dim-chip[data-dim="${dim}"]`);
    if (chip) {
      chip.classList.toggle('has', next === 'has');
      chip.classList.toggle('missing', next === 'missing');
    } else {
      console.warn('[StockCenter] chip not found for dim:', dim);
    }
    this.applyFilter();
  },

  /** ═══ 自选股筛选 ═══ */
  setWatchlistFilter(val) {
    console.log('[StockCenter] setWatchlistFilter called:', val);
    this._wlFilter = val;
    document.querySelectorAll('#sc-wl-filter span').forEach(function(el) {
      el.classList.toggle('active', el.dataset.v === val);
    });
    this.applyFilter();
  },

  /** ═══ 重置所有筛选 (供外部调用) ═══ */
  resetFilters() {
    this._dimStates = {};
    this._wlFilter = '';
    document.querySelectorAll('.sc-dim-chip').forEach(function(el) {
      el.classList.remove('has', 'missing');
    });
    document.querySelectorAll('#sc-wl-filter span').forEach(function(el) {
      el.classList.toggle('active', el.dataset.v === '');
    });
    document.getElementById('sc-industry-filter').value = '';
    document.getElementById('sc-only-missing').checked = false;
    document.getElementById('sc-search').value = '';
  },

  /** ═══ 批量同步行业 ═══ */
  async batchSyncIndustry() {
    const codes = this.getSelected();
    if (codes.length === 0) { await Modal.alert('提示', '请先勾选需要同步的股票'); return; }
    const ok = await Modal.confirm('同步行业', `确认对 ${codes.length} 只同步行业分类?`);
    if (!ok) return;
    DataTabs.Core.addLog(`[StockCenter] 开始同步行业: ${codes.length} 只...`);
    try {
      const r = await SyncAPI.industry(codes);
      DataTabs.Core.addLog(`[StockCenter] 行业同步: ${r.synced || 0}/${codes.length} 完成`);
      await Modal.alert('同步完成', `${r.synced || 0}/${codes.length} 只行业已同步`);
    } catch (e) {
      console.error('[StockCenter] Industry sync fail:', e);
      DataTabs.Core.addLog(`[StockCenter] 行业同步失败: ${e.message}`, 'error');
    }
    this.load(this.currentPage);
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
      // 股票中心 → 去掉外层 padding-top; 其他 tab → 恢复
      const wrapper = document.getElementById('tab-content-wrapper');
      if (wrapper) {
        wrapper.style.paddingTop = tab === 'stock-center' ? '0' : '14px';
      }
      if (tab === 'stock-center') DataTabs.StockCenter.load(1);
    };
  }
})();
