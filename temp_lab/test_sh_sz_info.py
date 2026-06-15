"""Test Shanghai and Shenzhen stock info APIs"""
import akshare as ak
import pandas as pd
pd.set_option("display.max_columns", 30)
pd.set_option("display.width", 500)

# Test SH stock info
for symbol in ["sh", "SH", "1"]:
    try:
        df = ak.stock_info_sh_name_code(symbol=symbol)
        print(f"\nSH ({symbol}): cols={df.columns.tolist()}, rows={len(df)}")
        print(df.head(3))
    except Exception as e:
        print(f"SH ({symbol}) failed: {e}")

# Test SZ stock info
for symbol in ["sz", "SZ", "2"]:
    try:
        df = ak.stock_info_sz_name_code(symbol=symbol)
        print(f"\nSZ ({symbol}): cols={df.columns.tolist()}, rows={len(df)}")
        print(df.head(3))
    except Exception as e:
        print(f"SZ ({symbol}) failed: {e}")
