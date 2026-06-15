"""Test sync_basic_info with the new requests-based push2"""
import asyncio, sys, os
sys.path.insert(0, r'E:\workspace\AIResearch\AIStock_Pro\backend')

from app.framework.database.session import async_session
from app.models.models import StockMaster
from app.domain.market_data.services.valuation import sync_basic_info
from sqlalchemy import select

async def test(code='300567'):
    print(f'=== Testing sync_basic_info for {code} ===')
    ok = await sync_basic_info(code)
    print(f'Returned: {ok}')

    async with async_session() as db:
        sm = await db.get(StockMaster, code)
        if sm:
            print(f'  name: {sm.stock_name}')
            print(f'  total_shares: {sm.total_shares:.0f}')
            print(f'  float_shares: {sm.float_shares}')
            print(f'  list_date: {sm.list_date}')
            print(f'  industry: {sm.industry}')
        else:
            print(f'  {code}: NOT FOUND in StockMaster')

    print('=== DONE ===')

asyncio.run(test(sys.argv[1] if len(sys.argv) > 1 else '300567'))
