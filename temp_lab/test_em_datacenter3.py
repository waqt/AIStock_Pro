"""Find EM datacenter API for stock industry - try multiple approaches"""
import httpx, json
import urllib.parse

headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"}

with httpx.Client(headers=headers, timeout=15, verify=False) as client:
    # Approach 1: Try the EM data center securities API
    # This is known to work for various stock lists
    reports_to_try = [
        "RPT_F10_FINANCE_MAINFINADATA",
        "RPT_F10_FINANCE_MAINFINADATA_NEW",
        "RPT_LICO_FN_CPD",
        "RPT_LICO_FN_CPD_NEW",
    ]

    for report in reports_to_try:
        try:
            resp = client.get(
                "http://datacenter.eastmoney.com/securities/api/data/v1/get",
                params={
                    "reportName": report,
                    "columns": "ALL",
                    "filter": '(SECUCODE="000001.SZ")',
                    "pageNumber": 1,
                    "pageSize": 10,
                    "source": "HSF10",
                    "client": "PC",
                },
            )
            data = resp.json()
            if data.get("success"):
                print(f"[{report}] SUCCESS!")
                if data.get("result") and data["result"].get("data"):
                    d = data["result"]["data"][0]
                    print(json.dumps(d, ensure_ascii=False, indent=2)[:500])
            else:
                msg = data.get("message", data.get("code", "unknown"))
                print(f"[{report}] {msg}")
        except Exception as e:
            print(f"[{report}] error: {e}")
