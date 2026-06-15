"""Try different EM datacenter reports for stock industry"""
import httpx, json

headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"}

with httpx.Client(headers=headers, timeout=15, verify=False) as client:
    # Common reports that might contain industry info
    reports = [
        "RPT_F10_BASIC_INFO_COMPANY",
        "RPT_F10_BASIC_INFO_PROFILE",
        "RPT_F10_BASIC_MAIN_BUSINESS",
        "RPT_F10_BASIC_INDUSTRY",
        "RPT_F10_BASIC_INDUSTRY_DIVISION",
        "RPT_F10_BASIC_INFORMATION",
        "RPT_F10_BASIC_BACKGROUND",
        "RPT_F10_BASIC_BUSINESS",
        "RPT_F10_BASIC_INDUSTRY_CLASSIFICATION",
        "RPT_LICO_FN_CPD",
    ]

    for report in reports:
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
                result = data.get("result", {})
                records = result.get("data", [])
                if records:
                    # Show available columns
                    sample = records[0]
                    cols = list(sample.keys())
                    print(f"\n[{report}] SUCCESS")
                    print(f"  Columns ({len(cols)}): {cols}")
                    # Show industry-related fields
                    for c in cols:
                        if "INDUSTRY" in c or "industry" in c or "HY" in c or "CLASS" in c:
                            print(f"  {c}: {sample[c]}")
                else:
                    print(f"[{report}] empty data")
            else:
                msg = data.get("message", str(data.get("code", "")))
                print(f"[{report}] {msg}")
        except Exception as e:
            print(f"[{report}] error: {e}")
