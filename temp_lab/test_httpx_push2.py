"""Test httpx with verify=False to push2"""
import asyncio
import httpx

async def main():
    code = '300567'
    market_code = 0
    async with httpx.AsyncClient(proxy=None, timeout=10, verify=False,
                                  headers={"User-Agent": "Mozilla/5.0"}) as client:
        resp = await client.get(
            f"https://push2.eastmoney.com/api/qt/stock/get",
            params={"fltt": "2", "invt": "2",
                    "fields": "f57,f58,f84,f85,f189,f116",
                    "secid": f"{market_code}.{code}"}
        )
        data = resp.json()
        d = data.get("data", {})
        print(f'f84 total_shares: {d.get("f84")}')
        print(f'f85 float_shares: {d.get("f85")}')
        print(f'f116 total_mcap_yuan: {d.get("f116")}')
        print(f'f189 list_date: {d.get("f189")}')
        print(f'f57 code: {d.get("f57")}')
        print(f'f58 name: {d.get("f58")}')

asyncio.run(main())
