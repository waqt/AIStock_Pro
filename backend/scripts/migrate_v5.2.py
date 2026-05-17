"""V5.2 Migration: Add import-related fields"""
import asyncio, sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database import engine
from sqlalchemy import text

MIGRATIONS = [
    ("trade_history", "amount", "DOUBLE DEFAULT 0.0"),
    ("trade_history", "commission", "DOUBLE DEFAULT 0.0"),
    ("trade_history", "stamp_tax", "DOUBLE DEFAULT 0.0"),
    ("trade_history", "notes", "TEXT"),
    ("positions", "first_buy_date", "DATE"),
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
    print("[OK] V5.2 Migration complete.")

if __name__ == "__main__":
    asyncio.run(migrate())
