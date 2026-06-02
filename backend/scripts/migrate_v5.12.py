"""迁移 V5.12: StockInfo 新增 total_shares (总股本) 和 float_shares (流通股本)"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from app.framework.database.session import engine
from sqlalchemy import text
import asyncio

NEW_COLS = [
    ("total_shares", "FLOAT DEFAULT NULL COMMENT '总股本(股)'"),
    ("float_shares", "FLOAT DEFAULT NULL COMMENT '流通股本(股)'"),
]

async def migrate():
    async with engine.begin() as conn:
        for col_name, col_def in NEW_COLS:
            try:
                await conn.execute(text(
                    f"ALTER TABLE stock_info ADD COLUMN {col_name} {col_def}"
                ))
                print(f"  [OK] Added {col_name}")
            except Exception as e:
                if "Duplicate column" in str(e) or "already exists" in str(e):
                    print(f"  [SKIP] {col_name} already exists")
                else:
                    print(f"  [FAIL] {col_name}: {e}")
    print("V5.12 migration complete.")

if __name__ == "__main__":
    asyncio.run(migrate())
