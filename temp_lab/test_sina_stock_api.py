"""Test Sina stock fundamental API for industry data"""
import httpx, json, re

headers = {"User-Agent": "Mozilla/5.0", "Referer": "http://finance.sina.com.cn"}

with httpx.Client(headers=headers, timeout=15) as client:
    # Test 1: Sina v1 stock query API
    try:
        resp = client.get("https://hq.sinajs.cn/list=sh600519")
        print(f"Test 1 - Sina JS: {resp.status_code}")
        if resp.status_code == 200:
            print(resp.text[:300])
    except Exception as e:
        print(f"Test 1 failed: {e}")

    # Test 2: Sina fund flow API for industry
    try:
        resp = client.get(
            "http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
            "Market_Center.getHQ_NodeData",
            params={
                "page": 1,
                "num": 100,
                "sort": "symbol",
                "asc": 1,
                "node": "industry_sshy",
                "symbol": "",
                "_s_r_a": "page",
            },
        )
        print(f"\nTest 2 - Sina HQ Node: {resp.status_code}")
        if resp.status_code == 200:
            print(resp.text[:500])
    except Exception as e:
        print(f"Test 2 failed: {e}")

    # Test 3: Try Tencent stock detail info (includes fundamentals)
    try:
        resp = client.get("https://qt.gtimg.cn/q=ff_000001")
        print(f"\nTest 3 - Tencent fund: {resp.status_code}")
        if resp.status_code == 200:
            print(resp.text[:300])
    except Exception as e:
        print(f"Test 3 failed: {e}")

    # Test 4: Try Tencent stock info with industry fields
    # Some extended Tencent APIs include industry
    try:
        resp = client.get("https://qt.gtimg.cn/q=ff_000001,bk_000001")
        print(f"\nTest 4 - Tencent ext: {resp.status_code}")
        if resp.status_code == 200:
            print(resp.text[:300])
    except Exception as e:
        print(f"Test 4 failed: {e}")

    # Test 5: Xueqiu stock detail
    try:
        resp = client.get(
            "https://stock.xueqiu.com/v5/stock/batch/quote.json",
            params={"symbol": "SH000001", "extend": "detail"},
            headers={**headers, "Cookie": "xq_a_token=test"},
        )
        print(f"\nTest 5 - Xueqiu: {resp.status_code}")
        if resp.status_code == 200:
            print(resp.text[:300])
    except Exception as e:
        print(f"Test 5 failed: {e}")
