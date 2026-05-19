"""持仓估值同步 — 从腾讯行情获取 PE/PB/市值"""
from datetime import datetime as dt
from app.framework.database.session import async_session
from app.models.models import StockInfo, Position
from app.domain.market_data.sources.tencent import get_tencent_quotes
from app.framework.logger import logger
from sqlalchemy import select


async def sync_valuation(target_codes: list = None):
    """同步 PE/PB/市值到 stock_info 表。target_codes 为 None 时同步全部持仓"""
    async with async_session() as db:
        res = await db.execute(select(Position.stock_code))
        codes = list(set(r[0] for r in res.all() if r[0]))
        if target_codes:
            codes = [c for c in codes if c in set(target_codes)]

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
