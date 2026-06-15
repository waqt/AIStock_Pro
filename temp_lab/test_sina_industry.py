"""Test Sina industry ranking page for stock-industry mapping"""
import httpx, json, re

headers = {"User-Agent": "Mozilla/5.0"}

with httpx.Client(headers=headers, timeout=15) as client:
    resp = client.get(
        "http://vip.stock.finance.sina.com.cn/q/go.php/vIndustryRank/kind/sshy/p/1/num/5000/"
    )
    print(f"Status: {resp.status_code}, len={len(resp.text)}")
    if resp.status_code == 200:
        text = resp.text.replace("&nbsp;", " ")

        # Print structure
        print("\nFirst 2000 chars:")
        print(text[:2000])
