"""Check current StockMaster state"""
import asyncio, sys
sys.path.insert(0, r"E:\workspace\AIResearch\AIStock_Pro\backend")

from app.framework.database.session import async_session
from app.models.models import StockMaster, Position, WatchlistItem
from sqlalchemy import select

async def main():
    async with async_session() as db:
        # Total StockMaster records
        total = (await db.execute(select(StockMaster.stock_code))).scalars().all()
        print(f"Total StockMaster records: {len(total)}")

        # Records WITH industry
        has_ind = (await db.execute(
            select(StockMaster).where(StockMaster.industry.isnot(None))
        )).scalars().all()
        print(f"With industry: {len(has_ind)}")
        for r in has_ind:
            print(f"  {r.stock_code} {r.stock_name}: {r.industry}")

        # Records WITHOUT industry
        no_ind = (await db.execute(
            select(StockMaster).where(StockMaster.industry.is_(None))
        )).scalars().all()
        print(f"\nWithout industry: {len(no_ind)}")
        for r in no_ind:
            print(f"  {r.stock_code} {r.stock_name or '?'}")

        # Positions
        pos = (await db.execute(select(Position.stock_code))).scalars().all()
        print(f"\nPositions: {len(pos)}")

        # Watchlist
        wl = (await db.execute(select(WatchlistItem.stock_code))).scalars().all()
        print(f"Watchlist: {len(wl)}")

        # Combined portfolio + watchlist
        all_codes = set(pos) | set(wl)
        print(f"\nPortfolio+Watchlist total: {len(all_codes)}")

        # Which are missing industry?
        missing = []
        for code in all_codes:
            sm = (await db.execute(
                select(StockMaster).where(StockMaster.stock_code == code)
            )).scalar()
            if sm is None or not sm.industry:
                missing.append(code)
        print(f"Missing industry: {len(missing)}")
        for code in missing:
            print(f"  {code}")

asyncio.run(main())
