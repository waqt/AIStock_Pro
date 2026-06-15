"""Test Tencent F10 API for stock industry data"""
import httpx, json

headers = {"User-Agent": "Mozilla/5.0"}

with httpx.Client(headers=headers, timeout=15) as client:
    # Tencent F10 page for individual stock
    # The Tencent stock page has a section for company profile
    test_urls = [
        # Tencent SZ stock page
        ("SZ F10", "http://proxy.finance.qq.com/ifzqgtimg/appstock/app/F10/Industry?symbol=sz000001"),
        # Alternative Tencent API
        ("Sina stockinfo", "https://stock.finance.sina.com.cn/stockinfo/index.php?code=sh600519"),
    ]

    for name, url in test_urls:
        try:
            resp = client.get(url)
            print(f"{name}: {resp.status_code}, len={len(resp.text)}")
            if resp.status_code == 200:
                print(resp.text[:300])
        except Exception as e:
            print(f"{name}: {e}")

    # Test Tencent stock suggestion API (sometimes has industry)
    try:
        resp = client.get(
            "http://smartbox.gtimg.cn/s3/?q=000001&t=stock&f=json"
        )
        print(f"\nSmartbox: {resp.status_code}")
        if resp.status_code == 200:
            print(resp.text[:500])
    except Exception as e:
        print(f"Smartbox: {e}")
