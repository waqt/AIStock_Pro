"""Test CNINFO API for stock industry classification"""
import httpx, json

headers = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "http://www.cninfo.com.cn/",
}

with httpx.Client(headers=headers, timeout=15, verify=False) as client:
    # Try CNINFO stock classification API
    # http://www.cninfo.com.cn/new/data/szse_stock/industry_classification
    endpoints = [
        "http://www.cninfo.com.cn/new/data/szse_stock/industry_classification",
        "http://www.cninfo.com.cn/new/data/szse_stock/industry_classification?stock=000001",
        "https://www.cninfo.com.cn/new/information/topInfo/industry",
    ]
    for ep in endpoints:
        try:
            resp = client.get(ep)
            print(f"[{ep}]: status={resp.status_code}, len={len(resp.text)}")
            if resp.status_code == 200:
                print(resp.text[:300])
        except Exception as e:
            print(f"[{ep}] error: {e}")
