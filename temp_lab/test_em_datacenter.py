"""Test East Money datacenter API for stock industry classification"""
import httpx, json

headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"}

with httpx.Client(headers=headers, timeout=15, verify=False) as client:
    # Try push2ex for industry board constituents
    try:
        resp = client.get(
            "http://push2ex.eastmoney.com/getIndustryStockList",
            params={
                "ut": "7eea3edcaed734bea9c8b9e8faa5d0b2",
                "dession": "1",
                "industryCode": "BK0477",
                "pageSize": 100,
                "pageNum": 1,
                "sort": "3",
                "asc": "0",
            },
        )
        print(f"push2ex industry stock list: {resp.status_code}")
        if resp.status_code == 200:
            print(resp.text[:500])
    except Exception as e:
        print(f"push2ex failed: {e}")

    # Try datacenter stock list API
    try:
        resp = client.get(
            "http://datacenter.eastmoney.com/api/data/v1/get",
            params={
                "reportName": "RPT_F10_FINANCE_MAINFINADATA",
                "columns": "SECUCODE,SECURITY_NAME_ABBR,TRADE_MARKET,INDUSTRY",
                "filter": '(SECUCODE="000001.SZ")',
                "pageNumber": 1,
                "pageSize": 10,
                "source": "HSF10",
                "client": "PC",
            },
        )
        print(f"datacenter: {resp.status_code}")
        if resp.status_code == 200:
            print(resp.text[:1000])
    except Exception as e:
        print(f"datacenter failed: {e}")
