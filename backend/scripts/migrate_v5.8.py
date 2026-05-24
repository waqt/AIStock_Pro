"""V5.8 迁移: watchlist 增加 备注/目标价 列"""
import sys, os, asyncio
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text

columns = [
    ("notes", "TEXT", "备注"),
    ("target_price_low", "FLOAT", "目标价下限"),
    ("target_price_high", "FLOAT", "目标价上限"),
]

async def run():
    from app.framework.database.session import engine
    async with engine.begin() as conn:
        for col_name, col_type, col_comment in columns:
            try:
                await conn.execute(text(
                    f"ALTER TABLE watchlist ADD COLUMN {col_name} {col_type} COMMENT '{col_comment}'"
                ))
                print(f"  OK: {col_name}")
            except Exception as e:
                if "Duplicate" in str(e):
                    print(f"  SKIP: {col_name} already exists")
                else:
                    print(f"  ERROR: {col_name} — {e}")
    print("V5.8 migration complete.")

if __name__ == "__main__":
    asyncio.run(run())
