"""Test FinancialRawDataService API endpoints - debug mode"""
import sys, json, urllib.request

BASE = "http://127.0.0.1:8000/api/data"

def test_query():
    body = json.dumps({"code": "600699", "fields": ["revenue", "parent_profit"], "periods": 2}).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}/financial-raw/query",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        r = urllib.request.urlopen(req)
        d = json.loads(r.read())
        print(f"[OK] Query: {d['data']}")
    except urllib.error.HTTPError as e:
        print(f"[FAIL] HTTP {e.code}: {e.read().decode()[:500]}")

def test_compare():
    body = json.dumps({"code": "600699", "fields": ["revenue"], "periods": 8}).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}/financial-raw/compare",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        r = urllib.request.urlopen(req)
        d = json.loads(r.read())
        comps = d["data"]["comparisons"]
        ttm = d["data"]["ttm"]
        print(f"[OK] Compare: {len(comps)} periods, revenue_ttm={ttm.get('revenue_ttm')}")
    except urllib.error.HTTPError as e:
        print(f"[FAIL] HTTP {e.code}: {e.read().decode()[:500]}")

def test_query_bulk():
    body = json.dumps({"codes": ["600699", "688012"], "fields": ["revenue"], "periods": 2}).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}/financial-raw/query-bulk",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        r = urllib.request.urlopen(req)
        d = json.loads(r.read())
        print(f"[OK] Bulk: {len(d['data']['results'])} results, {d['data']['summary']}")
    except urllib.error.HTTPError as e:
        print(f"[FAIL] HTTP {e.code}: {e.read().decode()[:500]}")

if __name__ == "__main__":
    test_query()
    print()
    test_compare()
    print()
    test_query_bulk()
