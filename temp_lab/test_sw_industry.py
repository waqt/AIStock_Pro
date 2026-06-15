"""Test Shenwan industry classification with SSL verification disabled"""
import ssl
import urllib3

# Disable SSL warnings globally
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import akshare as ak
import pandas as pd

pd.set_option("display.max_columns", 30)
pd.set_option("display.width", 500)

try:
    df = ak.stock_industry_clf_hist_sw()
    print(f"SW clf: cols={df.columns.tolist()}, rows={len(df)}")
    print(df.head(5))
    print("\n--- tail ---")
    print(df.tail(5))
except Exception as e:
    print(f"SW clf failed: {e}")
