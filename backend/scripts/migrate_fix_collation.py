"""迁移: 修复所有表的 stock_code 列 collation 统一为 utf8mb4_unicode_ci

问题: 不同表在建表时 MySQL session collation 不同, 导致 stock_code 列
      collation 不一致 (部分 utf8mb4_unicode_ci, 部分 utf8mb4_general_ci),
      JOIN 时 Illegal mix of collations 错误。

已发现冲突表:
  - stock_master:   utf8mb4_unicode_ci
  - stock_valuation: utf8mb4_general_ci
  - positions:       utf8mb4_general_ci

修复: 将所有包含 stock_code 列的表的 collation 统一为 utf8mb4_unicode_ci
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from app.framework.database.session import engine
from sqlalchemy import text
import asyncio

# 需要统一 collation 的表 (如有遗漏, 脚本执行时会自动扫描全部)
TABLES = [
    "stock_valuation",
    "positions",
    "market_data",
    "watchlist",
    "financial_statements",
    "stock_info",
]


async def migrate():
    async with engine.begin() as conn:
        # Step 1: 扫描所有包含 stock_code 列的表
        print("=== Step 1: 扫描所有包含 stock_code 列的表 ===")
        try:
            res = await conn.execute(text(
                "SELECT TABLE_NAME, COLUMN_NAME, COLLATION_NAME, CHARACTER_SET_NAME "
                "FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND COLUMN_NAME IN ('stock_code', 'stock_code')"
            ))
            all_cols = {}
            for row in res.fetchall():
                all_cols[row[0]] = {"collation": row[2], "charset": row[3]}
                print(f"  {row[0]}.{row[1]}: charset={row[3]}, collation={row[2]}")
        except Exception as e:
            print(f"  [FAIL] Scan failed: {e}")
            return

        # Step 2: 修复 collation 不是 utf8mb4_unicode_ci 的表
        print("\n=== Step 2: 修复 collation 不一致的表 ===")
        for table, info in all_cols.items():
            if info["collation"] and info["collation"] != "utf8mb4_unicode_ci":
                try:
                    sql = text(
                        f"ALTER TABLE {table} MODIFY COLUMN stock_code VARCHAR(10) "
                        f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                    )
                    await conn.execute(sql)
                    print(f"  [OK] {table}.stock_code -> utf8mb4_unicode_ci")
                except Exception as e:
                    print(f"  [FAIL] {table}: {e}")
            else:
                print(f"  [SKIP] {table}.stock_code already utf8mb4_unicode_ci (or NULL)")

        # Step 3: 验证
        print("\n=== Step 3: 验证 ===")
        try:
            res = await conn.execute(text(
                "SELECT TABLE_NAME, COLLATION_NAME FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND COLUMN_NAME = 'stock_code'"
            ))
            all_ok = True
            for row in res.fetchall():
                status = "OK" if row[1] == "utf8mb4_unicode_ci" else "MISMATCH"
                if status == "MISMATCH":
                    all_ok = False
                print(f"  [{status}] {row[0]}: {row[1]}")
            if all_ok:
                print("\n[OK] 所有表 collation 一致 (utf8mb4_unicode_ci)")
            else:
                print("\n[WARN] 仍有表未修复, 请检查上方的 MISMATCH")
        except Exception as e:
            print(f"  [FAIL] Verification: {e}")

    print("\n迁移完成。请重启后端服务器。")


if __name__ == "__main__":
    asyncio.run(migrate())
