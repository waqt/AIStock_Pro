"""临时迁移: 给 positions 表添加 stock_name 列"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
import asyncio
from app.framework.database.session import engine
from sqlalchemy import text

async def migrate():
    async with engine.begin() as conn:
        cols = [
            ("stock_name", "VARCHAR(50) DEFAULT NULL COMMENT '股票名称（唯一真相源）'"),
        ]
        for col_name, col_def in cols:
            try:
                await conn.execute(text(
                    f"ALTER TABLE positions ADD COLUMN {col_name} {col_def}"
                ))
                print(f"  [OK] Added {col_name}")
            except Exception as e:
                if "Duplicate column" in str(e) or "already exists" in str(e):
                    print(f"  [SKIP] {col_name} already exists")
                else:
                    print(f"  [FAIL] {col_name}: {e}")
    print("Migration complete.")

if __name__ == "__main__":
    asyncio.run(migrate())
