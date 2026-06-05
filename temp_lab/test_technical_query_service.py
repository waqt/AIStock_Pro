"""验证 Phase 4: TechnicalQueryService"""
import sys
sys.path.insert(0, r'E:\workspace\AIResearch\AIStock_Pro\backend')

from app.domain.quant.engine.technical_query_service import TechnicalQueryService

print("=== TechnicalQueryService Test ===")

# 1. Catalog
catalog = TechnicalQueryService.get_catalog()
total = catalog["summary"]["total_indicators"]
categories = catalog["summary"]["categories"]
print(f"Catalog: {total} indicators, {len(categories)} categories")
for cat, names in sorted(categories.items()):
    print(f"  {cat}: {len(names)} indicators -> {names[:3]}...")

# 2. Format for prompt
prompt = TechnicalQueryService.format_catalog_for_prompt()
assert len(prompt) > 100, "Prompt should be substantial"
print(f"\nPrompt length: {len(prompt)} chars")
print(f"First 200 chars:\n{prompt[:200]}")

# 3. Query with specific indicators
result = TechnicalQueryService.query("600519", indicators=["macd_cross"])
print(f"\nQuery test: {result}")
assert "stock_code" in result, "Should contain stock_code"

# 4. Query without indicators (all fields)
all_result = TechnicalQueryService.query("600519")
assert "stock_code" in all_result, "Should contain stock_code"
print(f"All fields query: {len(all_result)} keys")

print("\n=== ALL PASS ===")
