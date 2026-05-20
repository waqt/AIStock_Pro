"""持仓估值同步 — 从腾讯行情获取 PE/PB/市值 + 从东财获取行业等基本信息"""
from datetime import datetime as dt
from app.framework.database.session import async_session
from app.models.models import StockInfo, Position
from app.domain.market_data.sources.tencent import get_tencent_quotes
from app.framework.logger import logger
from sqlalchemy import select
import asyncio


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
