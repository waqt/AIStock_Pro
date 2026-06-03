"""Verify all changes for Step 6 financial data integration"""
import sys
sys.path.insert(0, r'E:\workspace\AIResearch\AIStock_Pro\backend')

# 1. ROICIndicator with new fields
from app.domain.quant.indicators.fundamental.profitability.roic import ROICIndicator
meta = ROICIndicator.meta()
output = meta['output']
print(f'ROIC outputs: {output}')
assert 'roic_adjusted' in output, 'roic_adjusted missing!'
assert 'roic_pct_adjusted' in output, 'roic_pct_adjusted missing!'
print('  roic_adjusted and roic_pct_adjusted present: OK')

# 2. OCFProfitRatio
from app.domain.quant.indicators.fundamental.health.ocf_profit_ratio import OCFProfitRatio
meta2 = OCFProfitRatio.meta()
print(f'OCF Profit Ratio outputs: {meta2["output"]}')
print(f'  description: {meta2["description"][:50]}...')

# 3. Registry
from app.domain.quant.indicators.fundamental import FINANCIAL_REGISTRY
print(f'\nTotal indicators registered: {len(FINANCIAL_REGISTRY)}')
assert 'ocf_profit_ratio_ttm' in FINANCIAL_REGISTRY, 'ocf_profit_ratio_ttm not registered!'
print(f'  ocf_profit_ratio_ttm: registered OK')
for name in sorted(FINANCIAL_REGISTRY.keys()):
    print(f'    - {name}')

# 4. FinancialQueryService catalog
from app.domain.quant.engine.financial_query_service import FinancialQueryService
catalog = FinancialQueryService.get_catalog()
print(f'\nCatalog indicators: {catalog["summary"]["total_indicators"]}')
print(f'Catalog raw fields: {catalog["summary"]["total_raw_fields"]}')
print(f'Categories: {list(catalog["summary"]["categories"].keys())}')

# 5. Catalog prompt contains new indicator
prompt = FinancialQueryService.format_catalog_for_prompt()
print(f'\nCatalog prompt length: {len(prompt)} chars')
assert 'ocf_profit_ratio_ttm' in prompt, 'New indicator not in prompt!'
print(f'  ocf_profit_ratio_ttm in prompt: OK')
assert 'roic_adjusted' in prompt, 'roic_adjusted not in prompt!'
print(f'  roic_adjusted in prompt: OK')

# 6. ToolCall/ChatResult imports
from app.framework.ai.providers.base import ToolCall, ChatResult
print(f'\nToolCall/ChatResult: OK')

# 7. Query financial tool registration
from app.domain.research.agents.base import TOOL_REGISTRY, DEFAULT_TOOL_DEFINITIONS
print(f'Tool registry keys: {list(TOOL_REGISTRY.keys())}')
assert 'query_financial_data' in TOOL_REGISTRY, 'query_financial_data not registered!'
print(f'  query_financial_data tool: registered OK')
print(f'  Tool definitions count: {len(DEFAULT_TOOL_DEFINITIONS)}')

print('\n=== All verifications passed! ===')
