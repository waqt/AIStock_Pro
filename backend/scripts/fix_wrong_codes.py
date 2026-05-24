"""Fix wrong stock codes in stock_info and positions"""
import asyncio, sys
sys.path.insert(0, r'E:\workspace\AIResearch\AIStock_Pro\backend')
from app.framework.database.session import async_session
from app.framework.logger import logger
from sqlalchemy import text

async def main():
    async with async_session() as db:
        # 1. Fix stock_info: correct the wrong names
        fixes = {
            '688602': '康鹏科技',   # was wrongly "京仪装备", real 京仪装备 is 688652
            '688620': '安凯微',     # was wrongly "中微半导体设备", real 中微公司 is 688012
        }
        for code, correct_name in fixes.items():
            r = await db.execute(
                text('UPDATE stock_info SET stock_name=:name WHERE stock_code=:code'),
                {'name': correct_name, 'code': code})
            print(f"stock_info: {code} -> {correct_name} (rows updated: {r.rowcount})")

        # 2. Fix positions: reassign codes
        # 688602 (康鹏科技) -> 688652 (京仪装备)
        r = await db.execute(
            text("UPDATE positions SET stock_code='688652', stock_name='京仪装备' WHERE stock_code='688602'"))
        print(f"positions: 688602 -> 688652 (京仪装备), rows: {r.rowcount}")

        # 688620 (安凯微) -> 688012 (中微公司)
        r = await db.execute(
            text("UPDATE positions SET stock_code='688012', stock_name='中微公司' WHERE stock_code='688620'"))
        print(f"positions: 688620 -> 688012 (中微公司), rows: {r.rowcount}")

        await db.commit()
        print("\nDone. Please re-sync market data for the new codes.")

asyncio.run(main())
