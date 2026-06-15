"""Check Tushare rate limit status"""
import tushare as ts
from datetime import datetime

print(f"Current time: {datetime.now().strftime('%H:%M:%S')}")

ts.set_token('7bd999653a2e10e4bf1ffca503d27e1cf82b158a18bd8a2e2e40f66c')
pro = ts.pro_api()

try:
    # Try per-stock query (rate limit: 1/min)
    df = pro.stock_basic(ts_code='000001.SZ', fields='ts_code,name,industry,list_date')
    if df is not None:
        print(f"Per-stock query: SUCCESS")
        print(f"Result: {df.to_dict('records')}")
    else:
        print(f"Per-stock query: empty result")
except Exception as e:
    print(f"Per-stock query: {e}")

try:
    # Try batch query (rate limit: 1/hour)
    df = pro.stock_basic(fields='ts_code,name,industry,list_date,market')
    if df is not None and not df.empty:
        print(f"\nBatch query: SUCCESS! Got {len(df)} stocks")
        industries = df[df['industry'].notna() & (df['industry'] != '')]
        print(f"With industry: {len(industries)}")
        print(df.head(3))
    else:
        print(f"\nBatch query: empty result")
except Exception as e:
    print(f"\nBatch query: {e}")
