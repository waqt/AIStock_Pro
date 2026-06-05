"""验证 Phase 1+3: 动态列推导"""
import sys
sys.path.insert(0, r'E:\workspace\AIResearch\AIStock_Pro\backend')

from app.domain.quant.engine.indicator_store import (
    INDICATOR_ALL_COLS, INDICATOR_NUMERIC_COLS, INDICATOR_TEXT_COLS,
    _get_dynamic_indicator_cols, _reset_indicator_cols_cache
)

print("=== Dynamic Column Test ===")

# 1. Check column counts
num = INDICATOR_NUMERIC_COLS()
txt = INDICATOR_TEXT_COLS()
cols = INDICATOR_ALL_COLS()

print(f"Total columns: {len(cols)}")
print(f"Numeric: {len(num)}")
print(f"Text: {len(txt)} -> {txt}")

# 2. Check text fields are correctly identified
assert 'chip_pattern' in txt, "chip_pattern should be text"
assert 'chip_signal' in txt, "chip_signal should be text"
assert 'price' in num, "price should be numeric"
assert 'macd' in num, "macd should be numeric"
assert 'rsi' in num, "rsi should be numeric"
print("\nField type checks passed")

# 3. Check no duplicates
assert len(cols) == len(set(cols)), "Duplicate columns found!"
print("No duplicate columns")

# 4. Check cache works
_cache_hit = _get_dynamic_indicator_cols()
assert _cache_hit is not None, "Cache should return tuple"
print("Cache works")

# 5. Reset and re-get
_reset_indicator_cols_cache()
reloaded = INDICATOR_ALL_COLS()
assert len(reloaded) == len(cols), "Reload should match initial"
print("Reset + reload works")

print("\n=== ALL PASS ===")
