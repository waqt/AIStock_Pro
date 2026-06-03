"""Test FinancialRawDataService API endpoints"""
import sys, json, urllib.request

BASE = "http://127.0.0.1:8000/api/data"

def test_catalog():
    r = urllib.request.urlopen(f"{BASE}/financial-raw/catalog")
    d = json.loads(r.read())
    assert d["success"]
    s = d["data"]["summary"]
    print(f"[OK] Catalog: {s['total_fields']} fields, {len(s['categories'])} categories")
    return d["data"]

def test_query():
    body = json.dumps({"code": "600699", "fields": ["revenue", "parent_profit"], "periods": 2}).encode()
    r = urllib.request.urlopen(f"{BASE}/financial-raw/query", body)
    d = json.loads(r.read())
    assert d["success"]
    data = d["data"]
    print(f"[OK] Query: {data['stock_code']}, report_date={data.get('report_date')}, revenue={data.get('revenue')}")

def test_compare():
    body = json.dumps({"code": "600699", "fields": ["revenue"], "periods": 8}).encode()
    r = urllib.request.urlopen(f"{BASE}/financial-raw/compare", body)
    d = json.loads(r.read())
    assert d["success"]
    comps = d["data"]["comparisons"]
    ttm = d["data"]["ttm"]
    print(f"[OK] Compare: {len(comps)} periods, revenue_ttm={ttm.get('revenue_ttm')}")

if __name__ == "__main__":
    print("=== FinancialRawDataService API Test ===\n")
    cat = test_catalog()
    print()
    test_query()
    print()
    test_compare()
    print("\n=== All tests passed! ===")
