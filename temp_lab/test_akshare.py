"""测试 akshare stock_individual_info_em"""
import os
os.environ['NO_PROXY'] = '*'
os.environ['no_proxy'] = '*'
import akshare as ak
df = ak.stock_individual_info_em(symbol='300567')
print(df)
items = dict(zip(df['item'], df['value']))
print('\nTotal shares:', items.get('总股本'))
print('Float shares:', items.get('流通股'))
print('Market cap:', items.get('总市值'))
print('List date:', items.get('上市时间'))
