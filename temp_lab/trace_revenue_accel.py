"""Trace exactly what the API/task does for RevenueAcceleration"""
import sys, json
sys.path.insert(0, r'E:\workspace\AIResearch\AIStock_Pro\backend')

from app.domain.quant.indicators.fundamental import FINANCIAL_REGISTRY
from app.domain.research.services.financial_data_loader import load_financials
import asyncio

async def main():
    # Step 1: Check if RevenueAcceleration is in the registry
    print("=== Registry check ===")
    names = sorted(FINANCIAL_REGISTRY.keys())
    print(f'Total registered: {len(names)}')
    has_ra = 'revenue_acceleration' in FINANCIAL_REGISTRY
    print(f'RevenueAcceleration registered: {has_ra}')
    if has_ra:
        cls = FINANCIAL_REGISTRY['revenue_acceleration']
        import inspect
        src = inspect.getsource(cls.compute)
        print(f'RevenueAcceleration.compute has range(0, 12, 4): {"range(0, 12, 4)" in src}')
        print(f'RevenueAcceleration.compute has range(0, 8, 4): {"range(0, 8, 4)" in src}')

    # Step 2: Load real data and trace through the exact task logic
    print("\n=== Task logic trace for 688012 ===")
    fin = await load_financials('688012', periods=20, mode='local')
    quarters = fin.get('quarters', [])
    recent_first = list(reversed(quarters))
    print(f'Total quarters: {len(recent_first)}')

    # fin_indicators excludes roic/roiic
    fin_indicators = [(n, cls) for n, cls in FINANCIAL_REGISTRY.items() if n not in ("roic","roiic")]

    for i in range(len(recent_first) - 3):
        full_window = recent_first[i:]
        for name, cls in fin_indicators:
            if name == 'revenue_acceleration':
                try:
                    result = cls.compute(full_window)
                    print(f'  i={i}, len(fw)={len(full_window)}, result={result}')
                except Exception as e:
                    print(f'  i={i}, ERROR: {e}')

asyncio.run(main())
