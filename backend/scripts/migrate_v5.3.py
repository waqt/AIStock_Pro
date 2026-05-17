"""V5.3 Migration: Add exchange_rates table"""
import asyncio, sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database import engine, Base
from app.models.models import ExchangeRate

async def migrate():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("[OK] V5.3 Migration complete — exchange_rates table created.")

if __name__ == "__main__":
    asyncio.run(migrate())
