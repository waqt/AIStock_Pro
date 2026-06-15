"""Test Sina stock suggest API for industry data"""
import httpx

headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn"}

with httpx.Client(headers=headers, timeout=15) as client:
    # Sina suggest API - used for search autocomplete
    # type=11 means stock
    try:
        resp = client.get(
            "https://suggest3.sinajs.cn/suggest/",
            params={"type": 11, "key": "600519", "name": "sug"},
        )
        print(f"Sina suggest: {resp.status_code}")
        if resp.status_code == 200:
            print(resp.text[:500])
    except Exception as e:
        print(f"error: {e}")

    # Try different type params
    for t in [1, 2, 3, 4, 5, 11, 12]:
        try:
            resp = client.get(
                "https://suggest3.sinajs.cn/suggest/",
                params={"type": t, "key": "000001", "name": "sug"},
            )
            if resp.status_code == 200 and len(resp.text) > 10:
                print(f"\ntype={t}: {resp.text[:200]}")
        except:
            pass
