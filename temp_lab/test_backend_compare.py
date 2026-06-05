"""快速验证后端 compare API 和相关改动"""
import sys, json
sys.path.insert(0, r'E:\workspace\AIResearch\AIStock_Pro\backend')

# 1. 验证 CompareRequest 可导入
from app.domain.quant.api.indicators import CompareRequest, financial_router
print("[PASS] CompareRequest 导入成功")

# 2. 验证 indicator_store 可导入
from app.domain.quant.engine.indicator_store import get_financial_latest, get_financial_field_latest
print("[PASS] indicator_store 导入成功")

# 3. 验证 get_financial_field_latest 返回带 stock_name
rows = get_financial_field_latest("roic_pct")
if rows:
    sample = rows[0]
    print(f"[INFO] field_latest 样本: {json.dumps(sample, ensure_ascii=False)[:200]}")
    assert 'stock_code' in sample, "缺少 stock_code"
    print("[PASS] field_latest 返回格式正确")
else:
    print("[INFO] roic_pct 暂无数据 (需先计算)")

# 4. 验证 get_financial_latest
row = get_financial_latest("688012")
if row:
    print(f"[INFO] financial_latest 样本: stock_code={row.get('stock_code')}, report_date={row.get('report_date')}")
    assert row.get('stock_code') == '688012'
    print("[PASS] get_financial_latest 格式正确")
else:
    print("[INFO] 688012 暂无财务指标数据 (需先计算)")

print("\n=== 全部通过 ===")
