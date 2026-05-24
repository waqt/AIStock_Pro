"""V5.7 迁移: stock_info 增加 ROE/股息率/盈利增速列"""
import sys, os, asyncio
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text

columns = [
    ("roe", "FLOAT", "净资产收益率(%)"),
    ("dividend_yield", "FLOAT", "股息率(%)"),
    ("eps_growth_3y", "FLOAT", "近3年盈利复合增速(%)"),
]

async def run():
    from app.framework.database.session import engine
    async with engine.begin() as conn:
        for col_name, col_type, col_comment in columns:
            try:
                await conn.execute(text(
                    f"ALTER TABLE stock_info ADD COLUMN {col_name} {col_type} COMMENT '{col_comment}'"
                ))
                print(f"  OK: {col_name}")
            except Exception as e:
                if "Duplicate" in str(e):
                    print(f"  SKIP: {col_name} already exists")
                else:
                    print(f"  ERROR: {col_name} — {e}")
    print("V5.7 migration complete.")

if __name__ == "__main__":
    asyncio.run(run())
