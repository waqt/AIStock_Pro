"""Check DB for all stocks with industry data, export to cache"""
import asyncio, sys, json, os
sys.path.insert(0, r"E:\workspace\AIResearch\AIStock_Pro\backend")

from app.framework.database.session import async_session
from app.models.models import StockMaster
from sqlalchemy import select

async def main():
    async with async_session() as db:
        rows = await db.execute(
            select(StockMaster).where(StockMaster.industry.isnot(None))
        )
        records = rows.scalars().all()
        print(f"StockMaster records with industry: {len(records)}")

        # Build mapping
        mapping = {}
        for r in records:
            mapping[r.stock_code] = r.industry
            print(f"  {r.stock_code} {r.stock_name or '?'}: {r.industry}")

        # Save as JSON that matches cache format
        cache_path = r"E:\workspace\AIResearch\AIStock_Pro\backend\data\industry_mapping.json"
        output = {
            "mapping": mapping,
            "timestamp": __import__("datetime").datetime.now().isoformat(),
        }
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"\nSaved {len(mapping)} entries to cache file")

asyncio.run(main())
