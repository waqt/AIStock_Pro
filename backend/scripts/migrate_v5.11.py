"""迁移 V5.11: FinancialStatement 新增 ROIIC/ROIC 计算所需字段
- cash (货币资金)
- current_liabilities (流动负债合计)
- short_loan (短期借款)
- long_loan (长期借款)
- accounts_payable (应付账款)
- noncurrent_liab_1year (一年内到期非流动负债)
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from app.framework.database.session import async_session, engine
from sqlalchemy import text
import asyncio

NEW_COLS = [
    ("cash", "FLOAT DEFAULT 0.0 COMMENT '货币资金'"),
    ("current_liabilities", "FLOAT DEFAULT 0.0 COMMENT '流动负债合计'"),
    ("short_loan", "FLOAT DEFAULT 0.0 COMMENT '短期借款'"),
    ("long_loan", "FLOAT DEFAULT 0.0 COMMENT '长期借款'"),
    ("accounts_payable", "FLOAT DEFAULT 0.0 COMMENT '应付账款'"),
    ("noncurrent_liab_1year", "FLOAT DEFAULT 0.0 COMMENT '一年内到期非流动负债'"),
]

async def migrate():
    async with engine.begin() as conn:
        for col_name, col_def in NEW_COLS:
            try:
                await conn.execute(text(
                    f"ALTER TABLE financial_statements ADD COLUMN {col_name} {col_def}"
                ))
                print(f"  [OK] Added {col_name}")
            except Exception as e:
                if "Duplicate column" in str(e) or "already exists" in str(e):
                    print(f"  [SKIP] {col_name} already exists")
                else:
                    print(f"  [FAIL] {col_name}: {e}")
    print("V5.11 migration complete.")

if __name__ == "__main__":
    asyncio.run(migrate())
