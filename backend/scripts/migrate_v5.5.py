"""V5.5 Migration: Add stock_info table"""
import asyncio, sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.framework.database.session import engine, Base
from app.models.models import StockInfo

async def migrate():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("[OK] V5.5 Migration complete — stock_info table created.")
    print("[*] To sync stock list: POST /api/data/stock-list/sync")

if __name__ == "__main__":
    asyncio.run(migrate())
