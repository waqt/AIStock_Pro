"""V5.6 迁移: 清理旧 FULL_SCAN 指标 + 去重 + 加唯一约束"""
import asyncio, sys
sys.path.insert(0, '.')
from app.framework.database.session import async_session, engine
from sqlalchemy import text

async def migrate():
    async with engine.begin() as conn:
        # 1. 删除旧 FULL_SCAN 行 (只有5个基础指标, 用新路径重算)
        r = await conn.execute(text(
            "DELETE FROM stock_indicators WHERE indicator_type = 'FULL_SCAN'"))
        print(f"Deleted {r.rowcount} FULL_SCAN rows")

        # 2. 统一 indicator_type → DAILY (不再区分 SNAPSHOT/DAILY)
        r = await conn.execute(text(
            "UPDATE stock_indicators SET indicator_type = 'DAILY' WHERE indicator_type != 'DAILY'"))
        print(f"Updated {r.rowcount} rows to DAILY")

        # 3. 去重: 同 stock_code+analysis_date 保留 id 最大的
        r = await conn.execute(text("""
            DELETE s1 FROM stock_indicators s1
            INNER JOIN stock_indicators s2
            ON s1.stock_code = s2.stock_code
               AND s1.analysis_date = s2.analysis_date
               AND s1.id < s2.id
        """))
        print(f"Dedup deleted {r.rowcount} duplicate rows")

        # 4. 加唯一约束 (先 DROP 旧的同名约束, 避免报错)
        try:
            await conn.execute(text(
                "ALTER TABLE stock_indicators ADD UNIQUE KEY uq_stock_date (stock_code, analysis_date)"))
            print("Added unique constraint uq_stock_date")
        except Exception as e:
            if "Duplicate key" in str(e) or "already exists" in str(e):
                print("Constraint already exists, skipping")
            else:
                print(f"Constraint error: {e}")

    print("V5.6 migration complete.")

asyncio.run(migrate())
