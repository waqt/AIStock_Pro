"""Debug financial indicator computation - test RevenueAcceleration and adjusted ROIC/ROIIC"""
import sys, asyncio
sys.path.insert(0, r'E:\workspace\AIResearch\AIStock_Pro\backend')

from app.domain.research.services.financial_data_loader import load_financials
from app.domain.quant.indicators.fundamental.inflection import RevenueAcceleration
from app.framework.finance.roiic import compute_roic, compute_roiic
from app.framework.finance.rd_adjustment import adjust_rd_capitalization


async def test():
    # Test 1: RevenueAcceleration
    print("=== Test 1: RevenueAcceleration for 688012 ===")
    fin = await load_financials('688012', periods=20, mode='local')
    quarters = fin.get('quarters', [])
    recent_first = list(reversed(quarters))
    print(f'Total quarters: {len(recent_first)}')

    q0 = recent_first[0]
    keys = list(q0.keys())
    print(f'Keys count: {len(keys)}')
    print(f'Has revenue: {"revenue" in keys}')
    print(f'revenue={q0.get("revenue")}, report_date={q0.get("report_date")}')

    # Try 5 window positions
    for i in range(5):
        fw = recent_first[i:]
        result = RevenueAcceleration.compute(fw)
        print(f'  i={i}, len(fw)={len(fw)}, result={result}')

    # Test 2: ROIC/ROIIC adjusted
    print("\n=== Test 2: adjust_rd_capitalization for 688012 ===")
    for i in range(3):
        window_8q = recent_first[i:i+8]
        ri = compute_roiic(window_8q)
        roic_d = compute_roic(recent_first[i:i+4])
        try:
            adj = adjust_rd_capitalization(window_8q)
            print(f'  i={i}: roic_pct={roic_d.get("roic_pct")}, roiic_pct={ri.get("roiic_pct")}')
            print(f'    adj material={adj.get("material")}, profit_ratio={adj.get("adjusted_profit_yi",0)/max(adj.get("reported_profit_yi",0.01),0.01):.2f}')
        except Exception as e:
            print(f'  i={i}: adjust_rd_capitalization failed: {e}')

    # Test 3: Check if GROSS_MARGIN_TREND has the fix
    print("\n=== Test 3: Verify GrossMarginTrend fix ===")
    from app.domain.quant.indicators.fundamental.profit_quality import GrossMarginTrend
    # Simulate: margins consistently rising (newest > previous > older)
    # data is newest-first, so gms[0] > gms[1] > gms[2] means rising
    mock_data = [
        {"revenue": 100, "operate_cost": 30},   # newest: 70% margin
        {"revenue": 100, "operate_cost": 35},   # 65% margin
        {"revenue": 100, "operate_cost": 40},   # 60% margin
        {"revenue": 100, "operate_cost": 45},   # 55% margin
    ]
    result = GrossMarginTrend.compute(mock_data)
    print(f'Rising margins test → {result["gross_margin_trend"]} (should be rising)')

    mock_data2 = [
        {"revenue": 100, "operate_cost": 50},   # newest: 50% margin
        {"revenue": 100, "operate_cost": 45},   # 55% margin
        {"revenue": 100, "operate_cost": 40},   # 60% margin
        {"revenue": 100, "operate_cost": 35},   # 65% margin
    ]
    result2 = GrossMarginTrend.compute(mock_data2)
    print(f'Declining margins test → {result2["gross_margin_trend"]} (should be declining)')

    # Test 4: Check RevenueAcceleration with correct range
    print("\n=== Test 4: RevenueAcceleration range fix verification ===")
    # With range(0, 12, 4): rev has 3 elements [sum0-3, sum4-7, sum8-11]
    rev = [sum(float(q.get("revenue", 0) or 0) for q in recent_first[i:i+4]) for i in range(0, 12, 4)]
    print(f'len(rev)={len(rev)}, rev={[round(r/1e8,1) for r in rev]}')
    # With old code range(0, 8, 4): rev would have 2 elements, rev[2] would IndexError
    rev_old = [sum(float(q.get("revenue", 0) or 0) for q in recent_first[i:i+4]) for i in range(0, 8, 4)]
    print(f'OLD len(rev)={len(rev_old)}, rev[2] would cause IndexError')


asyncio.run(test())
