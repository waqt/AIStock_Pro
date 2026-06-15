"""测试 Tushare 批量获取行业分类"""
import tushare as ts
import pandas as pd
from datetime import datetime

print(f"Current time: {datetime.now().strftime('%H:%M:%S')}")

ts.set_token('7bd999653a2e10e4bf1ffca503d27e1cf82b158a18bd8a2e2e40f66c')
pro = ts.pro_api()

try:
    df = pro.stock_basic(fields='ts_code,name,industry,list_date,market')
    if df is not None and not df.empty:
        print(f"Success! Got {len(df)} stocks")
        industries = df[df['industry'].notna() & (df['industry'] != '')]
        print(f"With industry: {len(industries)}")
        print(df.head(3))
        # Show industry distribution
        print("\nTop 20 industries:")
        print(industries['industry'].value_counts().head(20))
    else:
        print("Empty result")
except Exception as e:
    print(f"Failed: {e}")
