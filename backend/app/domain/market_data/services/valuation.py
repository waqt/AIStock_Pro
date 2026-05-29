"""持仓估值同步 — 从腾讯行情获取 PE/PB/市值 + 从东财获取行业等基本信息"""
from datetime import datetime as dt
from app.framework.database.session import async_session
from app.models.models import StockInfo, Position
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
    # 放宽: 只要包含任一关键词
    for col in df_columns:
        col_str = str(col)
        if any(kw in col_str for kw in keywords):
            return col
    return None


async def sync_stock_info(code: str) -> bool:
    """同步单只股票的基本信息 (行业/总股本/上市时间) 从 akshare 东财接口"""
    try:
        import akshare as ak, httpx, os
        loop = asyncio.get_event_loop()
        # akshare 内部用 requests, 需绕过系统代理
        def _fetch():
            import os
            os.environ['HTTP_PROXY'] = ''
            os.environ['HTTPS_PROXY'] = ''
            os.environ['http_proxy'] = ''
            os.environ['https_proxy'] = ''
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
            elif '总股本' in item and '流通' not in item:
                try: info['total_shares'] = float(value)
                except: pass
            elif '上市时间' in item:
                try:
                    from datetime import date
                    val_str = str(int(value))
                    info['list_date'] = date(int(val_str[:4]), int(val_str[4:6]), int(val_str[6:8]))
                except: pass
            elif '股票简称' in item:
                info['name'] = str(value)

        if not info:
            # Tushare 兜底
            from app.domain.market_data.sources.tushare_provider import TushareProvider
            if TushareProvider.available():
                ts_info = await loop.run_in_executor(None, TushareProvider._fetch_stock_info, code)
                if ts_info.get('name'):
                    info['name'] = ts_info['name']
                if ts_info.get('industry'):
                    info['industry'] = ts_info['industry']
                if ts_info.get('list_date'):
                    try:
                        from datetime import date as d2
                        info['list_date'] = d2.fromisoformat(str(ts_info['list_date']))
                    except: pass
        if not info:
            return False

        async with async_session() as db:
            existing = await db.get(StockInfo, code)
            if existing:
                if 'industry' in info and info['industry']:
                    existing.industry = info['industry']
                if 'list_date' in info:
                    existing.list_date = info['list_date']
                if 'name' in info and (not existing.stock_name or existing.stock_name == code):
                    existing.stock_name = info['name']
                existing.updated_at = dt.now()
            else:
                db.add(StockInfo(
                    stock_code=code,
                    stock_name=info.get('name', code),
                    exchange='HK' if len(code) == 5 else ('SH' if code.startswith(('6','9')) else 'SZ'),
                    industry=info.get('industry'),
                    list_date=info.get('list_date'),
                ))
            await db.commit()

        logger.info(f"[StockInfo] Synced {code}: industry={info.get('industry','?')}")
        return True
    except Exception as e:
        logger.warning(f"[StockInfo] {code} info sync failed: {e}")
        return False


async def sync_valuation(target_codes: list = None):
    """同步 PE/PB/市值到 stock_info 表。target_codes 为 None 时同步全部持仓"""
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
            if not q.get("name"):
                continue
            existing = await db.get(StockInfo, code)
            if existing:
                existing.stock_name = q["name"] or existing.stock_name
                existing.pe_ttm = q.get("pe_ttm")
                existing.pb = q.get("pb")
                existing.mcap_yi = q.get("mcap_yi")
                existing.float_mcap_yi = q.get("float_mcap_yi")
                existing.turnover_pct = q.get("turnover_pct")
                existing.updated_at = dt.now()
            else:
                db.add(StockInfo(
                    stock_code=code, stock_name=q["name"],
                    exchange="HK" if len(code) == 5 else ("SH" if code.startswith(("6","9")) else "SZ"),
                    pe_ttm=q.get("pe_ttm"), pb=q.get("pb"),
                    mcap_yi=q.get("mcap_yi"), float_mcap_yi=q.get("float_mcap_yi"),
                    turnover_pct=q.get("turnover_pct"),
                ))
            updated += 1
        await db.commit()

    logger.info(f"[✅] Valuation synced: {updated} stocks")
    return updated


async def sync_financial_factors(target_codes: list = None):
    """同步 ROE/股息率/近3年盈利增速到 stock_info 表。
    数据来源: akshare 新浪财务指标 (ROE+股息率) + 财报表计算 (eps_growth_3y)。
    target_codes 为 None 时同步全部持仓+自选。
    """
    from app.models.models import WatchlistItem

    # 确定待同步股票范围
    async with async_session() as db:
        if target_codes:
            codes = list(target_codes)
        else:
            pos_res = await db.execute(select(Position.stock_code))
            wl_res = await db.execute(select(WatchlistItem.stock_code))
            codes = list(set([r[0] for r in pos_res.all()] + [r[0] for r in wl_res.all()]))

    if not codes:
        return 0

    # 过滤港股（新浪财务指标只支持A股）
    a_codes = [c for c in codes if len(c) == 6]
    if not a_codes:
        logger.info("[FinancialFactors] No A-share stocks to sync")
        return 0

    import akshare as ak
    from app.models.models import FinancialStatement
    from sqlalchemy import func

    updated = 0
    logger.info(f"[FinancialFactors] Syncing ROE/eps_growth for {len(a_codes)} A-share stocks")

    async with async_session() as db:
        for code in a_codes:
            try:
                # ── ROE + 股息率: 从 akshare 新浪财务指标获取 ──
                roe_val = None
                div_val = None
                try:
                    df = await asyncio.to_thread(
                        ak.stock_financial_analysis_indicator, symbol=code, start_year="2020")
                    if df is not None and not df.empty:
                        latest = df.iloc[-1]
                        roe_col = _find_column(df, ['净资产收益率', '%'])
                        if roe_col is not None and str(latest[roe_col]) != 'nan':
                            roe_val = float(latest[roe_col])
                        # 股息率: 列名可能是 "股息率(%)" 或 "股利支付率"
                        div_col = _find_column(df, ['股息率', '股利支付率'])
                        if div_col is not None and str(latest[div_col]) != 'nan':
                            div_val = float(latest[div_col])
                except Exception:
                    pass  # 获取失败不阻塞其他字段

                # ── eps_growth_3y: 从财报表计算近12个季度利润复合增速 ──
                eps_growth = None
                try:
                    # 取最近 12 季度 parent_profit
                    rows = await db.execute(
                        select(FinancialStatement.report_date, FinancialStatement.parent_profit)
                        .where(FinancialStatement.stock_code == code)
                        .order_by(FinancialStatement.report_date.desc())
                        .limit(12)
                    )
                    profits = [(r[0], r[1]) for r in rows.all() if r[1] and r[1] != 0]
                    if len(profits) >= 8:
                        # TTM 利润: 最近4个季度 vs 12季度前的4个季度
                        recent_ttm = sum(p[1] for p in profits[:4])
                        old_ttm = sum(p[1] for p in profits[8:12]) if len(profits) >= 12 else sum(p[1] for p in profits[4:8])
                        if old_ttm and old_ttm > 0:
                            years = 2 if len(profits) >= 12 else 1
                            eps_growth = round(((recent_ttm / old_ttm) ** (1 / years) - 1) * 100, 2)
                except Exception:
                    pass

                # ── 写入 stock_info ──
                existing = await db.get(StockInfo, code)
                if existing:
                    dirty = False
                    if roe_val is not None:
                        existing.roe = round(roe_val, 2)
                        dirty = True
                    if eps_growth is not None:
                        existing.eps_growth_3y = eps_growth
                        dirty = True
                    if div_val is not None:
                        existing.dividend_yield = round(div_val, 2)
                        dirty = True
                    if dirty:
                        existing.updated_at = dt.now()
                        updated += 1
                elif roe_val is not None:
                    db.add(StockInfo(
                        stock_code=code, stock_name=code,
                        roe=round(roe_val, 2),
                        eps_growth_3y=eps_growth,
                        dividend_yield=round(div_val, 2) if div_val is not None else None,
                    ))
                    updated += 1
                await asyncio.sleep(0)

            except Exception as e:
                logger.warning(f"[FinancialFactors] {code} sync failed: {e}")

        await db.commit()

    logger.info(f"[FinancialFactors] Synced {updated}/{len(a_codes)} stocks")
    return updated
