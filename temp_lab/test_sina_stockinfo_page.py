"""Test Sina stock info page for industry data"""
import httpx, json, re

headers = {"User-Agent": "Mozilla/5.0", "Referer": "http://finance.sina.com.cn"}

with httpx.Client(headers=headers, timeout=15, follow_redirects=True) as client:
    # Test 1: Sina stock info page for SH stocks
    for code, prefix in [("600519", "sh"), ("000001", "sz")]:
        url = f"https://stock.finance.sina.com.cn/stockinfo/index.php?code={prefix}{code}"
        try:
            resp = client.get(url)
            print(f"\n[{code}] {resp.status_code}, len={len(resp.text)}")
            if resp.status_code == 200:
                text = resp.text
                # Search for industry info
                # Usually in a table with "行业" or similar
                for m in re.finditer(r'行业[：:]\s*([^<"&\n]+)', text):
                    print(f"  Industry: {m.group(1)}")
                # Also try to find in the company info table
                for m in re.finditer(r'所属行业[：:]\s*([^<&\n]+)', text):
                    print(f"  Industry2: {m.group(1)}")
                # Print text around "行业"
                surrounding = text[text.find("行业")-50:text.find("行业")+100] if "行业" in text else ""
                if surrounding:
                    print(f"  Context: ...{surrounding}...")
                else:
                    print(f"  No '行业' found")
        except Exception as e:
            print(f"[{code}] error: {e}")

    # Test 2: Try Sina v3 API for stock info
    try:
        resp = client.get(
            "https://stock.finance.sina.com.cn/fund/api/json_v2.php/StockInfo.getStockInfo",
            params={"symbol": "600519"},
        )
        print(f"\n[Sina StockInfo API]: {resp.status_code}")
        if resp.status_code == 200:
            print(resp.text[:500])
    except Exception as e:
        print(f"Sina StockInfo API: {e}")
