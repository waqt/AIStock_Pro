"""Try EM datacenter API for individual stock fundamental data including industry"""
import httpx, json

headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"}

with httpx.Client(headers=headers, timeout=15, verify=False) as client:
    # East Money has a stock F10 API that returns company profile including industry
    # Let's try different approaches:

    # Approach 1: EM datacenter individual stock F10 API
    for url, params in [
        (
            "http://datacenter.eastmoney.com/securities/api/data/v1/get",
            {
                "reportName": "RPT_F10_FINANCE_MAINFINADATA",
                "columns": "SECUCODE,SECURITY_NAME_ABBR,INDUSTRY,TRADE_MARKET",
                "filter": '(SECUCODE="000001.SZ")',
                "pageNumber": 1,
                "pageSize": 10,
                "source": "HSF10",
                "client": "PC",
            },
        ),
        (
            "http://datacenter.eastmoney.com/securities/api/data/v1/get",
            {
                "reportName": "RPT_F10_FINANCE_MAINFINADATA",
                "columns": "ALL",
                "filter": '(SECUCODE="000001.SZ")',
                "pageNumber": 1,
                "pageSize": 10,
                "source": "HSF10",
                "client": "PC",
            },
        ),
        # Try F10 profile API
        (
            "http://datacenter.eastmoney.com/api/data/v1/get",
            {
                "reportName": "RPT_F10_FINANCE_MAINFINADATA",
                "columns": "SECUCODE,SECURITY_NAME_ABBR,INDUSTRY",
                "filter": '(SECUCODE="000001.SZ")',
                "pageNumber": 1,
                "pageSize": 10,
                "source": "HSF10",
                "client": "PC",
            },
        ),
    ]:
        try:
            resp = client.get(url, params=params)
            print(f"\n[GET] {url.split('/')[-1]}")
            print(f"  Status: {resp.status_code}")
            data = resp.json() if resp.text else {}
            success = data.get("success", False)
            print(f"  Success: {success}")
            if success:
                result = data.get("result", {})
                records = result.get("data", [])
                if records:
                    print(f"  Records: {json.dumps(records[0], ensure_ascii=False, indent=2)}")
                else:
                    print(f"  Result keys: {list(result.keys())}")
            else:
                print(f"  Message: {data.get('message', data.get('code', 'unknown'))}")
        except Exception as e:
            print(f"  Error: {e}")
