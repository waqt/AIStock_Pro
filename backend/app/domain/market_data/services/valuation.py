"""持仓估值同步 — 从腾讯行情获取 PE/PB/市值 + 从东财获取行业等基本信息

表拆分（V5.16）:
  - sync_stock_info  → StockMaster（静态：名称/行业/上市日/总股本）
  - sync_valuation   → StockValuation（动态：PE/PB/市值/换手率）
  - sync_financial_factors → StockValuation（动态：ROE/股息率/盈利增速）
"""
from datetime import datetime as dt, date
from app.framework.database.session import async_session
from app.models.models import StockMaster, StockValuation, Position
from app.domain.market_data.sources.tencent import get_tencent_quotes
from app.framework.logger import logger
from sqlalchemy import select
import asyncio


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


async def sync_stock_info(code: str) -> bool:
    """同步单只股票的基本信息 (行业/总股本/上市时间/名称) → StockMaster

    数据源: akshare 东财 (stock_individual_info_em), Tushare 兜底
    """
    try:
        import akshare as ak
        loop = asyncio.get_event_loop()

        def _fetch():
            import os
            for k in ('HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy'):
                os.environ[k] = ''
            return ak.stock_individual_info_em(code)

        df = await loop.run_in_executor(None, _fetch)
        if df is None or df.empty:
            return False

        info = {}
        for _, row in df.iterrows():
            item = str(row['item'])
            value = row['value']
            if '行业' in item:
                info['industry'] = str(value)
            elif '总股本' in item:
                if '流通' in item:
                    try: info['float_shares'] = float(value)
                    except: pass
                else:
                    try: info['total_shares'] = float(value)
                    except: pass
            elif '上市时间' in item:
                try:
                    val_str = str(int(value))
                    info['list_date'] = date(int(val_str[:4]), int(val_str[4:6]), int(val_str[6:8]))
                except: pass
            elif '股票简称' in item:
                info['name'] = str(value)

        if not info:
            from app.domain.market_data.sources.tushare_provider import TushareProvider
            if TushareProvider.available():
                ts_info = await loop.run_in_executor(None, TushareProvider._fetch_stock_info, code)
                if ts_info.get('name'):
                    info['name'] = ts_info['name']
                if ts_info.get('industry'):
                    info['industry'] = ts_info['industry']
                if ts_info.get('list_date'):
                    try:
                        info['list_date'] = date.fromisoformat(str(ts_info['list_date']))
                    except: pass
        if not info:
            return False

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
        logger.warning(f"[StockMaster] {code} info sync failed: {e}")
        return False


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

            # 写入/更新 StockValuation
            val = await db.get(StockValuation, code)
            if val:
                val.pe_ttm = q.get("pe_ttm")
                val.pb = q.get("pb")
                val.mcap_yi = q.get("mcap_yi")
                val.float_mcap_yi = q.get("float_mcap_yi")
                val.turnover_pct = q.get("turnover_pct")
                val.updated_at = dt.now()
            else:
                db.add(StockValuation(
                    stock_code=code,
                    pe_ttm=q.get("pe_ttm"), pb=q.get("pb"),
                    mcap_yi=q.get("mcap_yi"), float_mcap_yi=q.get("float_mcap_yi"),
                    turnover_pct=q.get("turnover_pct"),
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
            from sqlalchemy import outerjoin
            j = outerjoin(StockMaster, StockValuation,
                          StockMaster.stock_code == StockValuation.stock_code)
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
