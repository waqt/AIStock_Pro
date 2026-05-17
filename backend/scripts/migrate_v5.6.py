"""V5.6: Add PE/PB/mcap fields to stock_info"""
import asyncio, sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.framework.database.session import engine
from sqlalchemy import text

COLS = [
    ("stock_info", "pe_ttm", "DOUBLE"),
    ("stock_info", "pb", "DOUBLE"),
    ("stock_info", "mcap_yi", "DOUBLE"),
    ("stock_info", "float_mcap_yi", "DOUBLE"),
    ("stock_info", "turnover_pct", "DOUBLE"),
]

async def migrate():
    async with engine.begin() as conn:
        for table, col, col_def in COLS:
            try:
                await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}"))
                print(f"[OK] Added {table}.{col}")
            except Exception as e:
                if "Duplicate" in str(e) or "already exists" in str(e):
                    print(f"[SKIP] {table}.{col} already exists")
                else:
                    print(f"[WARN] {e}")
    print("[OK] V5.6 Migration complete.")

if __name__ == "__main__":
    asyncio.run(migrate())
