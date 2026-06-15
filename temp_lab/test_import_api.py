"""Test import API endpoints after fixes"""
import httpx, json, asyncio

async def test():
    base = 'http://127.0.0.1:8000/api/ai'
    async with httpx.AsyncClient() as c:
        # 1. 文本解析 - 持仓
        r = await c.post(f'{base}/parse-text', json={'text': '600519 贵州茅台 100 1750\n000858 五粮液 200 135', 'parse_type': 'position'})
        d = r.json()
        print(f'[parse-text position] status={r.status_code} count={d.get("count",0)} ok={d.get("success")}')
        if d.get("data"):
            for item in d["data"][:2]:
                print(f'  {item.get("stock_code")} {item.get("stock_name")} qty={item.get("shares")} cost={item.get("cost_price")}')

        # 2. 文本解析 - 交易
        r = await c.post(f'{base}/parse-text', json={'text': '600519 贵州茅台 BUY 100 1800 2025-06-01\n000858 五粮液 SELL 200 135 2025-06-15', 'parse_type': 'trade'})
        d = r.json()
        print(f'\n[parse-text trade] status={r.status_code} count={d.get("count",0)} ok={d.get("success")}')
        if d.get("data"):
            for item in d["data"][:2]:
                print(f'  {item.get("stock_code")} {item.get("stock_name")} {item.get("trade_type")} qty={item.get("shares")} price={item.get("price")} date={item.get("trade_date")}')

        # 3. CSV 格式文本
        r = await c.post(f'{base}/parse-text', json={'text': '代码,名称,数量,成本价\n600519,贵州茅台,100,1750.50\n000858,五粮液,200,135.00', 'parse_type': 'position'})
        d = r.json()
        print(f'\n[parse-text csv] status={r.status_code} count={d.get("count",0)}')

        # 4. 中文格式文本 (常见券商复制格式)
        r = await c.post(f'{base}/parse-text', json={'text': '证券代码	证券名称	持股数量	成本价	市价\n600519	贵州茅台	100	1750.00	1820.50\n000858	五粮液	200	135.00	142.30', 'parse_type': 'position'})
        d = r.json()
        print(f'\n[parse-text chinese] status={r.status_code} count={d.get("count",0)}')
        if d.get("data"):
            for item in d["data"][:2]:
                print(f'  {item.get("stock_code")} {item.get("stock_name")} qty={item.get("shares")} cost={item.get("cost_price")}')

        print('\n✅ All tests completed')

asyncio.run(test())
