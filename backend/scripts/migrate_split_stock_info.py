"""
V5.16: Split stock_info into stock_master (static) + stock_valuation (dynamic).
Remove redundant stock_name from positions and watchlist tables.

迁移步骤:
  1. CREATE TABLE stock_master, stock_valuation（通过 metadata.create_all）
  2. INSERT INTO stock_master FROM stock_info（迁移静态数据）
  3. INSERT INTO stock_valuation FROM stock_info（迁移估值数据）
  4. ALTER TABLE positions DROP COLUMN stock_name
  5. ALTER TABLE watchlist DROP COLUMN stock_name
"""
import asyncio, sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.framework.database.session import engine, Base
from sqlalchemy import text, select
from app.models.models import StockMaster, StockValuation, StockInfo, Position, WatchlistItem


async def migrate():
    async with engine.begin() as conn:
        # ── 1. 建新表（幂等：已存在则跳过） ──
        await conn.run_sync(Base.metadata.create_all)
        print("[OK] Tables created (stock_master, stock_valuation)")

        # ── 2. 迁移静态数据到 stock_master ──
        has_master_data = await conn.execute(text("SELECT COUNT(*) FROM stock_master"))
        if has_master_data.scalar() == 0:
            await conn.execute(text("""
                INSERT INTO stock_master (stock_code, stock_name, exchange, industry, list_date,
                                          total_shares, float_shares, status, created_at)
                SELECT stock_code, stock_name, exchange, industry, list_date,
                       total_shares, float_shares, 'active', NOW()
                FROM stock_info
            """))
            print(f"[OK] stock_master populated from stock_info")
        else:
            print("[SKIP] stock_master already has data")

        # ── 3. 迁移估值数据到 stock_valuation ──
        has_val_data = await conn.execute(text("SELECT COUNT(*) FROM stock_valuation"))
        if has_val_data.scalar() == 0:
            await conn.execute(text("""
                INSERT INTO stock_valuation (stock_code, pe_ttm, pb, mcap_yi, float_mcap_yi,
                                             turnover_pct, roe, dividend_yield, eps_growth_3y, updated_at)
                SELECT stock_code, pe_ttm, pb, mcap_yi, float_mcap_yi,
                       turnover_pct, roe, dividend_yield, eps_growth_3y, updated_at
                FROM stock_info
                WHERE pe_ttm IS NOT NULL OR pb IS NOT NULL OR mcap_yi IS NOT NULL
            """))
            print(f"[OK] stock_valuation populated from stock_info")
        else:
            print("[SKIP] stock_valuation already has data")

        # ── 4. ALTER positions DROP stock_name ──
        try:
            await conn.execute(text("ALTER TABLE positions DROP COLUMN stock_name"))
            print("[OK] positions.stock_name dropped")
        except Exception as e:
            err = str(e).lower()
            if "duplicate" in err or "check that column/key exists" in err or "unknown column" in err:
                print("[SKIP] positions.stock_name already dropped or not found")
            else:
                print(f"[WARN] positions DROP COLUMN: {e}")

        # ── 5. ALTER watchlist DROP stock_name ──
        try:
            await conn.execute(text("ALTER TABLE watchlist DROP COLUMN stock_name"))
            print("[OK] watchlist.stock_name dropped")
        except Exception as e:
            err = str(e).lower()
            if "duplicate" in err or "check that column/key exists" in err or "unknown column" in err:
                print("[SKIP] watchlist.stock_name already dropped or not found")
            else:
                print(f"[WARN] watchlist DROP COLUMN: {e}")

    print("[OK] V5.16 Migration complete.")


if __name__ == "__main__":
    asyncio.run(migrate())
