"""V5.4 Migration: Extend exchange_rates for market indices"""
import asyncio, sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database import engine
from sqlalchemy import text

MIGRATIONS = [
    ("exchange_rates", "name", "VARCHAR(50)"),
    ("exchange_rates", "change_pct", "DOUBLE"),
]

async def migrate():
    async with engine.begin() as conn:
        for table, col, col_def in MIGRATIONS:
            try:
                await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}"))
                print(f"[OK] Added {table}.{col}")
            except Exception as e:
                if "Duplicate" in str(e) or "already exists" in str(e):
                    print(f"[SKIP] {table}.{col} already exists")
                else:
                    print(f"[WARN] {table}.{col}: {e}")
        # 扩大 code 字段长度以容纳 USD_IDX/BRENT 等
        try:
            await conn.execute(text("ALTER TABLE exchange_rates MODIFY COLUMN code VARCHAR(20)"))
            print("[OK] Modified exchange_rates.code to VARCHAR(20)")
        except Exception as e:
            print(f"[SKIP] code modify: {e}")
    print("[OK] V5.4 Migration complete.")

if __name__ == "__main__":
    asyncio.run(migrate())
