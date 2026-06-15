"""Test EM board industry constituents with direct httpx"""
import httpx, json

headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"}

with httpx.Client(headers=headers, timeout=15, verify=False) as client:
    # Try EM board constituent API directly
    # This is the API that stock_board_industry_cons_em calls
    # It might use push2.eastmoney.com or a different domain
    for domain in [
        "push2.eastmoney.com",
        "datacenter.eastmoney.com",
        "push2ex.eastmoney.com",
    ]:
        try:
            resp = client.get(
                f"https://{domain}/api/qt/clist/get",
                params={
                    "pn": 1,
                    "pz": 100,
                    "po": 1,
                    "np": 1,
                    "ut": "bd1d9ddb04089700cf9c27f6f7426281",
                    "fltt": 2,
                    "invt": 2,
                    "fid": "f3",
                    "fs": "m:90+t:2+f:!50",
                    "fields": "f12,f14,f2,f3,f4,f5,f6,f7,f8,f9,f10",
                },
            )
            print(f"[{domain}] status={resp.status_code}")
            if resp.status_code == 200:
                print(resp.text[:200])
        except Exception as e:
            print(f"[{domain}] error: {e}")

    # Try using HTTP instead
    for domain in [
        "push2.eastmoney.com",
        "datacenter.eastmoney.com",
        "push2ex.eastmoney.com",
    ]:
        try:
            resp = client.get(
                f"http://{domain}/api/qt/clist/get",
                params={
                    "pn": 1,
                    "pz": 100,
                    "po": 1,
                    "np": 1,
                    "ut": "bd1d9ddb04089700cf9c27f6f7426281",
                    "fltt": 2,
                    "invt": 2,
                    "fid": "f3",
                    "fs": "m:90+t:2+f:!50",
                    "fields": "f12,f14,f2,f3,f4,f5,f6,f7,f8,f9,f10",
                },
            )
            print(f"[http {domain}] status={resp.status_code}")
            if resp.status_code == 200:
                print(resp.text[:200])
        except Exception as e:
            print(f"[http {domain}] error: {e}")
