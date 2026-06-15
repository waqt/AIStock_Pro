"""Try Tushare HTTP API directly (bypass SDK rate limiting)"""
import httpx, json

token = "7bd999653a2e10e4bf1ffca503d27e1cf82b158a18bd8a2e2e40f66c"

with httpx.Client(timeout=15) as client:
    resp = client.post(
        "http://api.tushare.pro",
        json={
            "api_name": "stock_basic",
            "token": token,
            "params": {"fields": "ts_code,name,industry,list_date,market"},
            "fields": "",
        },
    )
    print(f"Status: {resp.status_code}")
    data = resp.json()
    if data.get("code") == 0:
        records = data.get("data", {}).get("items", [])
        fields = data.get("data", {}).get("fields", [])
        print(f"SUCCESS! {len(records)} stocks")
        print(f"Fields: {fields}")
        # Count with industry
        industry_idx = fields.index("industry") if "industry" in fields else -1
        if industry_idx >= 0:
            has_industry = sum(1 for r in records if r[industry_idx])
            print(f"With industry: {has_industry}")
        print(f"First 3: {records[:3]}")
    else:
        print(f"Error: {data.get('msg', data)}")
