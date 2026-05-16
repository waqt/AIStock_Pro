import asyncio
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database import engine
from sqlalchemy import text


async def migrate():
    async with engine.begin() as conn:
        # 1. 添加 change_pct 列
        try:
            await conn.execute(text(
                "ALTER TABLE market_data ADD COLUMN change_pct FLOAT NULL COMMENT 'change_pct'"
            ))
            print("[OK] Added change_pct column to market_data")
        except Exception as e:
            if "Duplicate" in str(e) or "already exists" in str(e):
                print("[OK] change_pct column already exists")
            else:
                print(f"[WARN] {e}")

        # 2. 添加唯一约束
        try:
            await conn.execute(text(
                "ALTER TABLE market_data ADD UNIQUE INDEX uq_market_data_code_date (stock_code, trade_date)"
            ))
            print("[OK] Added unique constraint on (stock_code, trade_date)")
        except Exception as e:
            if "Duplicate" in str(e) or "already exists" in str(e):
                print("[OK] Unique constraint already exists")
            else:
                print(f"[WARN] {e}")

    print("[OK] Migration V5.1 complete.")


if __name__ == "__main__":
    asyncio.run(migrate())
