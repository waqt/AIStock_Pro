"""持仓估值同步 — 从腾讯行情获取 PE/PB/市值 + 从东财获取行业等基本信息

表拆分（V5.17）:
  - sync_basic_info  → StockMaster（静态：名称/总股本/流通股本/上市日期）
  - sync_industry    → StockMaster.industry（行业分类，独立缓存+多源链）
  - sync_valuation   → StockValuation（动态：PE/PB/市值/换手率）
  - sync_financial_factors → StockValuation（动态：ROE/股息率/盈利增速）
"""
from datetime import datetime as dt, date
from app.framework.database.session import async_session
from app.models.models import StockMaster, StockValuation, Position
from app.domain.market_data.sources.tencent import get_tencent_quotes
from app.framework.logger import logger
from sqlalchemy import select
import os, json
import httpx
import asyncio

# ── 行业映射缓存 ──
_INDUSTRY_CACHE = {}
_INDUSTRY_CACHE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "data", "industry_mapping.json")
_INDUSTRY_CACHE_RETRY_TIME = 0  # 下次尝试 Tushare batch 的时间戳


def _load_industry_cache() -> dict:
    """从 JSON 文件加载行业映射缓存"""
    if _INDUSTRY_CACHE:
        return _INDUSTRY_CACHE
    if os.path.exists(_INDUSTRY_CACHE_PATH):
        try:
            with open(_INDUSTRY_CACHE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                _INDUSTRY_CACHE.update(data.get("mapping", {}))
            logger.info(f"[IndustryCache] Loaded {len(_INDUSTRY_CACHE)} mappings from {_INDUSTRY_CACHE_PATH}")
        except Exception as e:
            logger.warning(f"[IndustryCache] Load failed: {e}")
    return _INDUSTRY_CACHE


def _save_industry_cache():
    """持久化行业映射"""
    try:
        os.makedirs(os.path.dirname(_INDUSTRY_CACHE_PATH), exist_ok=True)
        with open(_INDUSTRY_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump({"mapping": _INDUSTRY_CACHE, "timestamp": dt.now().isoformat()},
                      f, ensure_ascii=False, indent=2)
        logger.info(f"[IndustryCache] Saved {len(_INDUSTRY_CACHE)} mappings")
    except Exception as e:
        logger.warning(f"[IndustryCache] Save failed: {e}")


async def _ensure_industry_cache():
    """确保缓存有数据; 没有则通过 Tushare 批量获取 (含重试控制)"""
    global _INDUSTRY_CACHE_RETRY_TIME
    cache = _load_industry_cache()
    if len(cache) > 100:
        return cache

    # 首次加载时从 DB StockMaster 补充缓存 (已有的行业数据快速加载)
    if len(cache) < 50 and not _INDUSTRY_CACHE_RETRY_TIME:
        try:
            async with async_session() as db:
                from sqlalchemy import select
                sm_rows = await db.execute(
                    select(StockMaster.stock_code, StockMaster.industry)
                    .where(StockMaster.industry.isnot(None))
                )
                for row in sm_rows.all():
                    code, ind = row
                    if ind and code not in _INDUSTRY_CACHE:
                        _INDUSTRY_CACHE[code] = ind
            if _INDUSTRY_CACHE:
                _save_industry_cache()
                logger.info(f"[IndustryCache] Supplemented from DB: {len(_INDUSTRY_CACHE)} industries")
        except Exception as e:
            logger.warning(f"[IndustryCache] DB supplement failed: {e}")

    now = dt.now().timestamp()
    # 避免在频率限制期内反复重试 (每 10 分钟最多尝试一次)
    if now < _INDUSTRY_CACHE_RETRY_TIME:
        return _INDUSTRY_CACHE

    # 尝试 Tushare 批量获取
    try:
        from app.domain.market_data.sources.tushare_provider import TushareProvider
        loop = asyncio.get_event_loop()
        all_info = await loop.run_in_executor(None, TushareProvider.fetch_all_stock_basic)
        if all_info:
            for code, info in all_info.items():
                if info.get("industry"):
                    _INDUSTRY_CACHE[code] = info["industry"]
            _save_industry_cache()
            logger.info(f"[IndustryCache] Built via Tushare batch: {len(_INDUSTRY_CACHE)} industries")
            return _INDUSTRY_CACHE
    except Exception as e:
        msg = str(e)
        if "频率超限" in msg:
            # Tushare 频率限制, 10 分钟后再试
            _INDUSTRY_CACHE_RETRY_TIME = now + 600
            logger.warning(f"[IndustryCache] Tushare rate limited, retry after 600s")
        else:
            logger.warning(f"[IndustryCache] Tushare batch failed: {e}")

    return _INDUSTRY_CACHE


async def _save_stock_master(code: str, info: dict) -> bool:
    """将股票基本信息写入 / 更新 StockMaster"""
    try:
        async with async_session() as db:
            existing = await db.get(StockMaster, code)
            if existing:
                if 'industry' in info and info['industry']:
                    existing.industry = info['industry']
                if 'list_date' in info:
                    existing.list_date = info['list_date']
                if 'name' in info and (not existing.stock_name or existing.stock_name == code):
                    existing.stock_name = info['name']
                if 'total_shares' in info:
                    existing.total_shares = info['total_shares']
                if 'float_shares' in info:
                    existing.float_shares = info['float_shares']
            else:
                db.add(StockMaster(
                    stock_code=code,
                    stock_name=info.get('name', code),
                    exchange=_infer_exchange(code),
                    industry=info.get('industry'),
                    list_date=info.get('list_date'),
                    total_shares=info.get('total_shares'),
                    float_shares=info.get('float_shares'),
                ))
            await db.commit()
        logger.info(f"[StockMaster] Synced {code}: name={info.get('name','?')} industry={info.get('industry','?')}")
        return True
    except Exception as e:
        logger.warning(f"[StockMaster] {code}: DB save failed: {e}")
        return False


def _find_column(df_columns, keywords: list) -> object:
    """在 DataFrame 列名中模糊查找, 返回第一个匹配的列名"""
    for col in df_columns:
        col_str = str(col)
        if all(kw in col_str for kw in keywords):
            return col
    for col in df_columns:
        col_str = str(col)
        if any(kw in col_str for kw in keywords):
            return col
    return None


def _infer_exchange(code: str) -> str:
    """根据股票代码推断交易所"""
    if len(code) == 5:
        return "HK"
    return "SH" if code.startswith(("6", "9")) else "SZ"


async def sync_basic_info(code: str) -> bool:
    """同步单只股票的基本信息 (名称/总股本/流通股本/上市日期) → StockMaster

    专注静态信息，不含行业分类（行业由 sync_industry 独立负责）。
    数据源链: 腾讯(名称) → EM push2(总股本/流通股本/上市日期) → Tushare(上市日期回退)
    """
    loop = asyncio.get_event_loop()
    info = {}

    # ── 数据源 1: 腾讯行情 (名称) ──
    try:
        quotes = await get_tencent_quotes([code])
        if quotes and code in quotes:
            q = quotes[code]
            if q.get("name"):
                info['name'] = q["name"]
    except Exception as e:
        logger.warning(f"[StockMaster] {code}: Tencent failed ({e})")

    # ── 数据源 2: httpx → 东方财富 push2 API (总股本/流通股本/上市日期, 带重试) ──
    for attempt in range(3):
        if info.get('total_shares') and info.get('list_date'):
            break
        for proxy, protocol in [(None, "http"), ("http://127.0.0.1:7890", "https")]:
            try:
                market_code = 1 if code.startswith("6") else 0
                async with httpx.AsyncClient(proxy=proxy, timeout=8,
                                              headers={"User-Agent": "Mozilla/5.0"}) as client:
                    resp = await client.get(
                        f"{protocol}://push2.eastmoney.com/api/qt/stock/get",
                        params={"fltt": "2", "invt": "2",
                                "fields": "f57,f58,f84,f85,f189",
                                "secid": f"{market_code}.{code}"}
                    )
                    data = resp.json()
                    if data.get("data"):
                        d = data["data"]
                        if not info.get('name') and d.get("f58"):
                            info['name'] = str(d["f58"])
                        if d.get("f84"):
                            try: info['total_shares'] = float(d["f84"])
                            except: pass
                        if d.get("f85"):
                            try: info['float_shares'] = float(d["f85"])
                            except: pass
                        if d.get("f189"):
                            try:
                                val_str = str(int(d["f189"]))
                                info['list_date'] = date(int(val_str[:4]), int(val_str[4:6]), int(val_str[6:8]))
                            except: pass
                        if info.get('total_shares') and info.get('list_date'): break
            except Exception as e:
                logger.warning(f"[StockMaster] {code}: EM push2 {proxy} attempt {attempt+1} failed ({e})")
        if not info.get('total_shares'):
            await asyncio.sleep(0.5)

    # ── 数据源 3: Tushare (列表日期回退) ──
    if not info.get('list_date'):
        try:
            from app.domain.market_data.sources.tushare_provider import TushareProvider
            if TushareProvider.available():
                ts_info = await loop.run_in_executor(None, TushareProvider._fetch_stock_info, code)
                if ts_info.get('list_date'):
                    try:
                        info['list_date'] = date.fromisoformat(str(ts_info['list_date']))
                    except: pass
        except Exception as e:
            logger.warning(f"[StockMaster] {code}: Tushare list_date fallback failed ({e})")

    if not info:
        logger.warning(f"[StockMaster] {code}: all data sources failed, skipping")
        return False

    return await _save_stock_master(code, info)


async def sync_stock_info(code: str) -> bool:
    """[向后兼容] 同步单只股票基本信息+行业 → StockMaster

    内部调用 sync_basic_info() + sync_industry()。
    V5.17+ 新增: 推荐直接调用 sync_basic_info / sync_industry。
    """
    ok = await sync_basic_info(code)
    # 单独同步行业（sync_industry 有独立缓存和多源链）
    try:
        await sync_industry(code)
    except Exception as e:
        logger.warning(f"[StockMaster] {code}: industry sync failed ({e})")
    return ok


async def sync_industry(code: str) -> str:
    """同步单只股票的行业分类 → StockMaster.industry

    数据源链: 本地缓存 → EM push2
    返回 industry 字符串或空字符串
    """
    # ── 数据源 0: 本地行业映射缓存 ──
    cache = await _ensure_industry_cache()
    industry = cache.get(code)
    if industry:
        logger.info(f"[Industry] {code}: cache hit → {industry}")
        return industry

    # ── 数据源 1: httpx → 东方财富 push2 API (带重试) ──
    for attempt in range(3):
        if industry:
            break
        for proxy, protocol in [(None, "http"), ("http://127.0.0.1:7890", "https")]:
            try:
                market_code = 1 if code.startswith("6") else 0
                async with httpx.AsyncClient(proxy=proxy, timeout=8,
                                              headers={"User-Agent": "Mozilla/5.0"}) as client:
                    resp = await client.get(
                        f"{protocol}://push2.eastmoney.com/api/qt/stock/get",
                        params={"fltt": "2", "invt": "2",
                                "fields": "f57,f127",
                                "secid": f"{market_code}.{code}"}
                    )
                    data = resp.json()
                    if data.get("data") and data["data"].get("f127"):
                        industry = str(data["data"]["f127"])
                        _INDUSTRY_CACHE[code] = industry
                        _save_industry_cache()
                        break
            except Exception as e:
                logger.warning(f"[Industry] {code}: EM push2 attempt {attempt+1} failed ({e})")
        if not industry:
            await asyncio.sleep(0.5)

    # 写入 StockMaster
    if industry:
        async with async_session() as db:
            master = await db.get(StockMaster, code)
            if master:
                master.industry = industry
                await db.commit()
        logger.info(f"[Industry] {code}: synced → {industry}")
    else:
        logger.warning(f"[Industry] {code}: all sources failed")

    return industry


async def sync_valuation(target_codes: list = None):
    """同步 PE/PB/市值到 StockValuation 表。target_codes 为 None 时同步全部持仓

    若股票尚未在 StockMaster 中，自动用腾讯接口的名称创建一条初始记录。
    """
    async with async_session() as db:
        if target_codes:
            codes = list(target_codes)
        else:
            res = await db.execute(select(Position.stock_code))
            codes = list(set(r[0] for r in res.all() if r[0]))

    if not codes:
        return 0

    quotes = await get_tencent_quotes(codes)
    updated = 0

    async with async_session() as db:
        for code, q in quotes.items():
            name = q.get("name")
            if not name:
                continue

            # 确保 StockMaster 有该股票的记录（用腾讯名称兜底创建）
            master = await db.get(StockMaster, code)
            if not master:
                db.add(StockMaster(
                    stock_code=code, stock_name=name,
                    exchange=_infer_exchange(code),
                ))

            # 写入/更新 StockValuation (★ 质量保护: 返回值无效时不覆盖)
            val = await db.get(StockValuation, code)
            pe = q.get("pe_ttm")
            pb = q.get("pb")
            mcap = q.get("mcap_yi")
            fmcap = q.get("float_mcap_yi")
            turnover = q.get("turnover_pct")
            if val:
                if pe is not None and pe > 0: val.pe_ttm = pe
                if pb is not None and pb > 0: val.pb = pb
                if mcap is not None and mcap > 0: val.mcap_yi = mcap
                if fmcap is not None and fmcap > 0: val.float_mcap_yi = fmcap
                if turnover is not None: val.turnover_pct = turnover
                val.updated_at = dt.now()
            else:
                db.add(StockValuation(
                    stock_code=code,
                    pe_ttm=pe if pe and pe > 0 else None,
                    pb=pb if pb and pb > 0 else None,
                    mcap_yi=mcap if mcap and mcap > 0 else None,
                    float_mcap_yi=fmcap if fmcap and fmcap > 0 else None,
                    turnover_pct=turnover,
                ))
            updated += 1
        await db.commit()

    logger.info(f"[StockValuation] Synced: {updated} stocks")
    return updated


async def sync_financial_factors(target_codes: list = None):
    """同步 ROE/股息率/近3年盈利增速到 StockValuation 表。

    数据来源: akshare 新浪财务指标 (ROE+股息率) + 财报表计算 (eps_growth_3y)。
    target_codes 为 None 时同步全部持仓+自选。
    """
    from app.models.models import WatchlistItem

    async with async_session() as db:
        if target_codes:
            codes = list(target_codes)
        else:
            pos_res = await db.execute(select(Position.stock_code))
            wl_res = await db.execute(select(WatchlistItem.stock_code))
            codes = list(set([r[0] for r in pos_res.all()] + [r[0] for r in wl_res.all()]))

    if not codes:
        return 0

    a_codes = [c for c in codes if len(c) == 6]
    if not a_codes:
        logger.info("[FinancialFactors] No A-share stocks to sync")
        return 0

    import akshare as ak
    from app.models.models import FinancialStatement

    updated = 0
    logger.info(f"[FinancialFactors] Syncing ROE/eps_growth for {len(a_codes)} A-share stocks")

    async with async_session() as db:
        for code in a_codes:
            try:
                # ── ROE + 股息率 ──
                roe_val = div_val = None
                try:
                    df = await asyncio.to_thread(
                        ak.stock_financial_analysis_indicator, symbol=code, start_year="2020")
                    if df is not None and not df.empty:
                        latest = df.iloc[-1]
                        roe_col = _find_column(df, ['净资产收益率', '%'])
                        if roe_col is not None and str(latest[roe_col]) != 'nan':
                            roe_val = float(latest[roe_col])
                        div_col = _find_column(df, ['股息率', '股利支付率'])
                        if div_col is not None and str(latest[div_col]) != 'nan':
                            div_val = float(latest[div_col])
                except Exception:
                    pass

                # ── eps_growth_3y ──
                eps_growth = None
                try:
                    rows = await db.execute(
                        select(FinancialStatement.report_date, FinancialStatement.parent_profit)
                        .where(FinancialStatement.stock_code == code)
                        .order_by(FinancialStatement.report_date.desc())
                        .limit(12)
                    )
                    profits = [(r[0], r[1]) for r in rows.all() if r[1] and r[1] != 0]
                    if len(profits) >= 8:
                        recent_ttm = sum(p[1] for p in profits[:4])
                        old_ttm = sum(p[1] for p in profits[8:12]) if len(profits) >= 12 else sum(p[1] for p in profits[4:8])
                        if old_ttm and old_ttm > 0:
                            years = 2 if len(profits) >= 12 else 1
                            eps_growth = round(((recent_ttm / old_ttm) ** (1 / years) - 1) * 100, 2)
                except Exception:
                    pass

                # ── 写入 StockValuation ──
                val = await db.get(StockValuation, code)
                if not val:
                    val = StockValuation(stock_code=code)
                    db.add(val)

                dirty = False
                if roe_val is not None:
                    val.roe = round(roe_val, 2)
                    dirty = True
                if eps_growth is not None:
                    val.eps_growth_3y = eps_growth
                    dirty = True
                if div_val is not None:
                    val.dividend_yield = round(div_val, 2)
                    dirty = True
                if dirty:
                    val.updated_at = dt.now()
                    updated += 1

                await asyncio.sleep(0)

            except Exception as e:
                logger.warning(f"[FinancialFactors] {code} sync failed: {e}")

        await db.commit()

    logger.info(f"[FinancialFactors] Synced {updated}/{len(a_codes)} stocks")
    return updated


# ═══ 基本面估值数据保鲜度检查 ═══════════════════

async def check_fundamentals_freshness(code: str) -> dict:
    """检查基本面估值数据 (PE/PB/市值/ROE) 存在性

    不阻塞, 仅检查 StockValuation 表是否有该股票记录。

    Returns:
        has_data: 是否有 PE/PB 等估值数据
        has_name: StockMaster 中是否有名称
        pe_ttm: 当前 PE (或 None)
        pb: 当前 PB (或 None)
        mcap_yi: 市值(亿元) (或 None)
        roe: ROE% (或 None)
    """
    async with async_session() as db:
        try:
            from sqlalchemy import outerjoin, collate
            j = outerjoin(StockMaster, StockValuation,
                          StockMaster.stock_code == collate(StockValuation.stock_code, 'utf8mb4_unicode_ci'))
            row = await db.execute(
                select(StockMaster, StockValuation)
                .select_from(j)
                .where(StockMaster.stock_code == code)
            )
            r = row.first()
            if r is None:
                return {"has_data": False, "has_name": False,
                        "pe_ttm": None, "pb": None, "mcap_yi": None, "roe": None}
            m, v = r
            return {
                "has_data": v is not None and v.pe_ttm is not None,
                "has_name": m.stock_name is not None,
                "name": m.stock_name,
                "industry": m.industry,
                "pe_ttm": v.pe_ttm if v else None,
                "pb": v.pb if v else None,
                "mcap_yi": v.mcap_yi if v else None,
                "roe": v.roe if v else None,
            }
        except Exception:
            return {"has_data": False, "has_name": False,
                    "pe_ttm": None, "pb": None, "mcap_yi": None, "roe": None}


async def resolve_sync_codes(codes: list = None) -> list:
    """统一股票代码解析：codes 有值直接返回去重列表，None 返回 Position ∪ WatchlistItem"""
    if codes:
        return list(set(str(c) for c in codes if c))
    from app.models.models import Position, WatchlistItem
    async with async_session() as db:
        pos = await db.execute(select(Position.stock_code))
        wl = await db.execute(select(WatchlistItem.stock_code))
        all_codes = set()
        for r in pos.all():
            all_codes.add(r[0])
        for r in wl.all():
            all_codes.add(r[0])
        return list(all_codes)
