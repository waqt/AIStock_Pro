"""Verify derived indicators (Layer 2) are properly integrated into FQS"""
import sys
sys.path.insert(0, r'E:\workspace\AIResearch\AIStock_Pro\backend')

from app.domain.quant.engine.financial_query_service import FinancialQueryService

catalog = FinancialQueryService.get_catalog()
print('=== Derived Indicators in Catalog ===')
for name, meta in sorted(catalog.get('derived_indicators', {}).items()):
    print(f"  {name} ({meta['label']}) — {meta['description'][:60]}...")

print(f"\nSummary: {catalog['summary']}")

# Check format_catalog_for_prompt() includes Layer 2
prompt = FinancialQueryService.format_catalog_for_prompt()
assert 'Layer 2' in prompt, 'Layer 2 section missing from prompt'
assert 'ar_turnover_days' in prompt, 'ar_turnover_days missing from prompt'
assert 'fixed_asset_turnover' in prompt, 'fixed_asset_turnover missing from prompt'
assert 'sga_ratio' in prompt, 'sga_ratio missing from prompt'
assert 'ocf_to_revenue_ratio' in prompt, 'ocf_to_revenue_ratio missing from prompt'
print(f'\nAll 4 derived indicators present in prompt: OK')
print(f'Prompt total length: {len(prompt)} chars')
print(f'\n=== All derived indicator verifications passed! ===')
