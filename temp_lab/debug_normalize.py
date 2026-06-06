"""Trace: check if _normalize preserves quality_detail correctly"""
import sys, os
sys.path.insert(0, r'E:\workspace\AIResearch\AIStock_Pro\backend')
os.environ['APP_ENV'] = 'development'

from app.domain.quant.valuation.engine import store as vstore
from app.domain.quant.valuation import VALUATION_REGISTRY
from app.domain.quant.valuation.methods.advanced.quality_adjusted import QualityAdjustedMethod

# 1. Check what the method returns
output = QualityAdjustedMethod.compute(pe_ttm=55.68, roe=None, dividend_yield=None, eps_growth_3y=None)
print('1. Method output:', output)

# 2. Check what _normalize does with it
normalized = vstore._normalize(output)
print('2. Normalized:', normalized)
print('   quality_detail:', repr(normalized.get('quality_detail')))

# 3. Check ALL_COLS has quality_detail
all_cols = vstore.ALL_COLS()
text_cols = vstore.TEXT_COLS()
print('3. quality_detail in all_cols:', 'quality_detail' in all_cols)
print('   quality_detail in text_cols:', 'quality_detail' in text_cols)

# 4. Check the insert SQL and values
sql = vstore._get_insert_sql()
row = vstore._normalize({'stock_code': 'TEST2', 'trade_date': '2026-06-06', **output})
vals = [row[c] for c in all_cols]
idx = all_cols.index('quality_detail') if 'quality_detail' in all_cols else -1
print(f'4. quality_detail idx in vals: {idx}')
if idx >= 0:
    print(f'   quality_detail value: {repr(vals[idx])}')
print(f'5. SQL cols: {len(all_cols)}, TEXT cols: {len(text_cols)}')

# 5. Test actual DB write
from datetime import date
vstore.init_db()
vstore.upsert_snapshot('TEST2', date.today(), {
    'adjusted_pe': 55.68,
    'quality_detail': '无质量溢价',
    'quality_bonus_pct': 0.0,
    'price': 78.83,
})
test_row = vstore.get_latest('TEST2')
print('6. After upsert:', repr(test_row.get('quality_detail')))
