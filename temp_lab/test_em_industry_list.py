"""Try EM stock screener API that returns all stocks with industry"""
import httpx, json

headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"}

with httpx.Client(headers=headers, timeout=15, verify=False) as client:
    # EM stock screener API
    # Try common report names for stock list with industry
    reports = [
        "RPT_STOCK_INDUSTRY",
        "RPT_STOCK_INDUSTRY_LIST",
        "RPT_STOCK_INDUSTRY_CLASSIFY",
        "RPT_STOCK_INDUSTRY_CLASSIFICATION",
        "RPT_STOCK_INDUSTRY_MAP",
        "RPT_DIME_STOCK_INDUSTRY",
        "RPT_DIME_STOCK_INDUSTRY_CLASSIFICATION",
        "RPT_LABEL_STOCK_INDUSTRY",
        "RPT_INDUSTRY_STOCK_LIST",
        "RPT_STOCK_INDUSTRY_EM",
    ]
    for report in reports:
        try:
            resp = client.get(
                "http://datacenter.eastmoney.com/api/data/v1/get",
                params={
                    "reportName": report,
                    "columns": "ALL",
                    "filter": '(ISNEW="1")',
                    "pageNumber": 1,
                    "pageSize": 5,
                    "source": "WEB",
                    "client": "PC",
                },
            )
            data = resp.json()
            if data.get("success"):
                result = data.get("result", {})
                records = result.get("data", [])
                if records:
                    sample = records[0]
                    cols = list(sample.keys())
                    print(f"\n[{report}] SUCCESS")
                    print(f"  Columns: {cols}")
                    for c in cols:
                        if "CODE" in c or "NAME" in c or "INDUSTRY" in c or "HY" in c:
                            print(f"  {c}: {sample[c]}")
                else:
                    print(f"[{report}] empty (total={result.get('total', '?')})")
            else:
                msg = data.get("message", str(data.get("code", "")))
                if "reportName" not in msg:
                    print(f"[{report}] {msg}")
        except Exception as e:
            pass
