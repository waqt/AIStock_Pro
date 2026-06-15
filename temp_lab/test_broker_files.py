"""Test with real broker .xls files (TSV masquerading as Excel)"""
import httpx, asyncio, io

async def test_broker_files():
    base = 'http://127.0.0.1:8000/api/ai'
    root = r'E:\workspace\AIResearch\AIStock_Pro\Local_data\position20260608'

    files_to_test = [
        (r'{}\我的持仓_融资融券.xls'.format(root), 'position'),
        (r'{}\我的持仓_普通.xls'.format(root), 'position'),
    ]

    async with httpx.AsyncClient(timeout=120.0) as c:
        for fpath, sheet_type in files_to_test:
            fname = fpath.split('\\')[-1]
            print(f'\n=== {fname} ===')

            with open(fpath, 'rb') as f:
                file_bytes = f.read()

            r = await c.post(f'{base}/upload-excel',
                files={'file': (fname, file_bytes, 'application/vnd.ms-excel')},
                data={'sheet_type': sheet_type})
            d = r.json()
            print(f'  status={r.status_code} count={d.get("count",0)}')

            if d.get("data"):
                for item in d["data"][:5]:
                    code = item.get("stock_code", "")
                    name = item.get("stock_name", "")
                    shares = item.get("shares", 0)
                    cost = item.get("cost_price", 0)
                    print(f'  code={code} name={name} qty={shares} cost={cost}')
                print(f'  ... total {len(d["data"])} records')
            elif d.get("detail"):
                print(f'  Error: {d["detail"]}')
            elif d.get("message"):
                print(f'  Message: {d.get("message")[:100]}')

    print('\nDone')

asyncio.run(test_broker_files())
