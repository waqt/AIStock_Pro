"""Test East Money datacenter API - find correct report name and columns"""
import httpx, json

headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"}

with httpx.Client(headers=headers, timeout=15, verify=False) as client:
    # Try different report names for stock list with industry
    reports_to_try = [
        "RPT_F10_FINANCE_MAINFINADATA",
        "RPT_F10_FINANCE_MAINFINADATA_NEW",
        "RPT_F10_FINANCE_MAINFINADATA_OLD",
        "RPT_LICO_FN_CPD",
        "RPT_DMSK_FN_MAIN",
    ]

    for report_name in reports_to_try:
        try:
            resp = client.get(
                "http://datacenter.eastmoney.com/api/data/v1/get",
                params={
                    "reportName": report_name,
                    "columns": "SECUCODE,SECURITY_NAME_ABBR,INDUSTRY",
                    "filter": '(SECUCODE="000001.SZ")',
                    "pageNumber": 1,
                    "pageSize": 10,
                    "source": "HSF10",
                    "client": "PC",
                },
            )
            data = resp.json()
            if data.get("success"):
                print(f"[{report_name}] SUCCESS: {json.dumps(data, ensure_ascii=False)[:300]}")
            else:
                print(f"[{report_name}] {data.get('message', 'failed')}")
        except Exception as e:
            print(f"[{report_name}] error: {e}")
