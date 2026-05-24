"""V5.9 迁移: exchange_rates 加 biz_date + 清理 US10YT 错误历史数据"""
import sys, os, asyncio
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text

async def run():
    from app.framework.database.session import engine

    # 1. 加 biz_date 列
    async with engine.begin() as conn:
        try:
            await conn.execute(text(
                "ALTER TABLE exchange_rates ADD COLUMN biz_date DATE COMMENT '数据业务日期'"))
            print("  OK: exchange_rates.biz_date")
        except Exception as e:
            if "Duplicate" in str(e):
                print("  SKIP: biz_date already exists")
            else:
                print(f"  ERROR: biz_date — {e}")

    # 2. 删除 US10YT 的错误历史数据 (之前存的是中国10Y-2Y利差 0.49，不是美债10Y)
    async with engine.begin() as conn:
        result = await conn.execute(text(
            "DELETE FROM macro_history WHERE code = 'US10YT'"))
        n = result.rowcount
        print(f"  OK: deleted {n} bad US10YT macro_history rows")

    async with engine.begin() as conn:
        result = await conn.execute(text(
            "DELETE FROM exchange_rates WHERE code = 'US10YT'"))
        print(f"  OK: deleted US10YT from exchange_rates (will re-sync)")

    print("V5.9 migration complete. Run POST /data/macro/sync?mode=historical to re-sync.")

if __name__ == "__main__":
    asyncio.run(run())
