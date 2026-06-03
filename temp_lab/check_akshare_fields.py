"""检查 akshare stock_individual_info_em 返回的全部字段"""
import os, sys
for k in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']:
    os.environ.pop(k, None)

import akshare as ak
df = ak.stock_individual_info_em(symbol='603777')
for _, row in df.iterrows():
    print(f"  {row['item']:20s} = {row['value']}")
