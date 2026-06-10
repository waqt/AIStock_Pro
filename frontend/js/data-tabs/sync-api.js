/**
 * 统一同步 API 组件 (V5.17)
 *
 * 所有页面通过此模块触发同步, 区别只在于 codes 的取值方式:
 *   选中股票 → this.getSelected()
 *   全部自选 → (await API.get('/data/watchlist')).data.map(i => i.stock_code)
 *   单只     → [code]
 *   全部     → null (服务端自动取 Position ∪ WatchlistItem)
 *
 * 依赖: api.js (API_BASE)
 */
window.SyncAPI = {

  /** 行情日K线同步 — mode: "smart" | "full" */
  async market(codes, mode = 'smart') {
    const r = await API.post('/data/sync/market', { codes, mode });
    return r;
  },

  /** 财务报表同步 — mode: "smart" | "full" */
  async financial(codes, mode = 'smart') {
    const r = await API.post('/data/sync/financial', { codes, mode });
    return r;
  },

  /** 估值 (PE/PB/市值) 同步 */
  async valuation(codes) {
    const r = await API.post('/data/sync/valuation', { codes });
    return r;
  },

  /** 行业分类同步 */
  async industry(codes) {
    const r = await API.post('/data/sync/industry', { codes });
    return r;
  },

  /** 股票基本信息同步 (名称/总股本/流通股本/上市日期) — mode: "smart" | "full" */
  async stockInfo(codes, mode = 'smart') {
    const r = await API.post('/data/sync/stock-info', { codes, mode });
    return r;
  },

  /** 宏观数据同步 — mode: "smart" | "full" */
  async macro(codes, mode = 'smart') {
    const r = await API.post('/data/sync/macro', { codes, mode });
    return r;
  },

  // ── 便捷: 获取全部股票代码 (Position ∪ WatchlistItem) ──
  async _getAllCodes() {
    try {
      const pos = await API.get('/positions');
      const wl = await API.get('/data/watchlist');
      const codes = new Set();
      (pos.data || []).forEach(p => codes.add(p.stock_code));
      (wl.data || []).forEach(w => codes.add(w.stock_code));
      return [...codes];
    } catch { return null; }
  },
};
