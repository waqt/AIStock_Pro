"""
重刷总股本 + 重算估值
修复内容:
  1. sync_basic_info: 改用 akshare stock_individual_info_em 获取总股本(修复 f84 返回市值的bug)
  2. fcf_yield: 单位始终亿/隐含价值扣除净债务/负FCF不伪装OCF

用法: conda activate aiteacher && python temp_lab/refresh_shares_and_valuation.py
"""
import asyncio, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from app.framework.database.session import async_session
from app.models.models import StockMaster, StockValuation, Position, WatchlistItem
from sqlalchemy import select
from app.domain.market_data.services.valuation import sync_basic_info
from app.domain.quant.valuation.engine.runner import valuation_runner
from app.framework.logger import logger


async def main():
    # 1. 获取全部股票代码 (持仓+自选)
    async with async_session() as db:
        pos = await db.execute(select(Position.stock_code))
        wl = await db.execute(select(WatchlistItem.stock_code))
        codes = list(set(
            [r[0] for r in pos.all() if r[0]]
            + [r[0] for r in wl.all() if r[0]]
        ))
    codes.sort()
    print(f"Total stocks: {len(codes)}")

    # 2. 重刷总股本 (仅 A 股, akshare stock_individual_info_em)
    print("\n=== Phase 1: Refresh total_shares from akshare ===")
    for code in codes:
        if len(code) != 6:
            print(f"  Skip {code} (not A-share)")
            continue
        try:
            ok = await sync_basic_info(code)
            if ok:
                async with async_session() as db:
                    sm = await db.get(StockMaster, code)
                    if sm:
                        print(f"  {code}: total_shares={sm.total_shares:.0f}  float_shares={sm.float_shares or 'N/A'}")
            await asyncio.sleep(0.3)  # 避免 akshare 频率限制
        except Exception as e:
            print(f"  {code}: ERROR {e}")

    # 3. 重算估值
    print("\n=== Phase 2: Recompute valuation ===")
    results = await valuation_runner.compute_batch(codes, calc_mode="snapshot")
    for r in results:
        code = r.get("stock_code", "?")
        errs = r.get("errors")
        if errs:
            print(f"  {code}: {len(r.get('methods_run', []))} methods, errors={errs}")
        else:
            print(f"  {code}: {len(r.get('methods_run', []))} methods OK")

if __name__ == "__main__":
    asyncio.run(main())
