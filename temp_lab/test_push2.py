"""Test various ways to reach EM push2 for total_shares"""
import os
os.environ['NO_PROXY'] = '*'
os.environ['no_proxy'] = '*'
os.environ.pop('REQUESTS_CA_BUNDLE', None)
os.environ.pop('CURL_CA_BUNDLE', None)
os.environ.pop('SSL_CERT_FILE', None)

# Test 1: requests via HTTP (not HTTPS)
import requests
import urllib3
urllib3.disable_warnings()

code = '300567'
market_code = 0

# HTTP version (like our httpx fallback)
url = f'http://push2.eastmoney.com/api/qt/stock/get'
params = {"fltt": "2", "invt": "2",
          "fields": "f57,f58,f84,f85,f189,f20",
          "secid": f"{market_code}.{code}"}
try:
    r = requests.get(url, params=params, timeout=10)
    print(f'HTTP status={r.status_code}')
    if r.status_code == 200:
        d = r.json().get('data', {})
        print(f'f84 total_shares: {d.get("f84")}')
        print(f'f85 float_shares: {d.get("f85")}')
        print(f'f20 mcap: {d.get("f20")}')
        print(f'f57 code: {d.get("f57")}')
except Exception as e:
    print(f'HTTP failed: {e}')

# HTTPS with verify=False
try:
    r = requests.get(url.replace('http://', 'https://'), params=params, timeout=10, verify=False)
    print(f'\nHTTPS status={r.status_code}')
    if r.status_code == 200:
        d = r.json().get('data', {})
        print(f'f84 total_shares: {d.get("f84")}')
        print(f'f20 mcap: {d.get("f20")}')
except Exception as e:
    print(f'HTTPS failed: {e}')

# Compare: f84 vs f20 ratio
print('\n--- Analysis ---')
print('f84 / f20 =', round(float(d.get('f84', 0)) / float(d.get('f20', 1)), 4) if d.get('f20') else 'N/A')

# Also try with the full field list from akshare
params2 = {"fltt": "2", "invt": "2",
           "fields": "f120,f121,f122,f174,f175,f59,f163,f43,f57,f58,f169,f170,f46,f44,f51,f168,f47,f164,f116,f60,f45,f52,f50,f48,f167,f117,f71,f161,f49,f530,f135,f136,f137,f138,f139,f141,f142,f144,f145,f147,f148,f140,f143,f146,f149,f55,f62,f162,f92,f173,f104,f105,f84,f85,f183,f184,f185,f186,f187,f188,f189,f190,f191,f192,f107,f111,f86,f177,f78,f110,f262,f263,f264,f267,f268,f255,f256,f257,f258,f127,f199,f128,f198,f259,f260,f261,f171,f277,f278,f279,f288,f152,f250,f251,f252,f253,f254,f269,f270,f271,f272,f273,f274,f275,f276,f265,f266,f289,f290,f286,f285,f292,f293,f294,f295,f43",
           "secid": f"{market_code}.{code}"}
try:
    r = requests.get(url, params=params2, timeout=10)
    print(f'\nFull fields HTTP status={r.status_code}')
    if r.status_code == 200:
        d = r.json().get('data', {})
        print(f'f84: {d.get("f84")}')
        print(f'f85: {d.get("f85")}')
except Exception as e:
    print(f'Full fields failed: {e}')
if d:
    print(f'\nTotal shares (f84): {d.get("f84")}')
