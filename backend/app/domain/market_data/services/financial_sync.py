"""财务报告同步 — akshare→DB, 自选股范围"""
import pandas as pd
import asyncio
from datetime import date, datetime
from typing import List, Optional
from app.framework.database.session import async_session
from app.models.models import FinancialStatement
from app.framework.logger import logger
from sqlalchemy import select


async def sync_financials(code: str) -> dict:
    """同步单只股票的财务报告到 DB"""
    prefix = _to_prefix(code)
    if not prefix:
        return {"code": code, "error": "Unsupported code format"}

    loop = asyncio.get_event_loop()
    try:
        income_df = await loop.run_in_executor(None, _fetch_income, prefix)
        cashflow_df = await loop.run_in_executor(None, _fetch_cashflow, prefix)
        balance_df = await loop.run_in_executor(None, _fetch_balance, prefix)
    except Exception as e:
        logger.warning(f"[FinSync] Fetch failed for {code}: {e}")
        return {"code": code, "error": str(e)}

    if income_df is None or income_df.empty:
        return {"code": code, "error": "No income data"}

    merged = _merge(income_df, cashflow_df, balance_df)
    if merged.empty:
        return {"code": code, "error": "Merge failed"}

    stored = await _upsert(code, merged)
    logger.info(f"[FinSync] {code}: {stored} quarters stored")
    return {"code": code, "stored": stored}


async def sync_financials_batch(codes: List[str]) -> dict:
    """批量同步"""
    total = 0
    for code in codes:
        r = await sync_financials(code)
        total += r.get("stored", 0)
    return {"synced_stocks": len(codes), "total_quarters": total}


async def sync_financials_smart(code: str) -> dict:
    """智能同步: 查最新报告期→拉数据→只Upsert新季度"""
    prefix = _to_prefix(code)
    if not prefix:
        return {"code": code, "error": "Unsupported code format"}

    # 查 DB 最新报告期
    async with async_session() as db:
        res = await db.execute(
            select(FinancialStatement.report_date)
            .where(FinancialStatement.stock_code == code)
            .order_by(FinancialStatement.report_date.desc())
            .limit(1)
        )
        latest_in_db = res.scalars().first()

    loop = asyncio.get_event_loop()
    try:
        income_df = await loop.run_in_executor(None, _fetch_income, prefix)
        cashflow_df = await loop.run_in_executor(None, _fetch_cashflow, prefix)
        balance_df = await loop.run_in_executor(None, _fetch_balance, prefix)
    except Exception as e:
        logger.warning(f"[FinSync] Fetch failed for {code}: {e}")
        return {"code": code, "error": str(e)}

    if income_df is None or income_df.empty:
        return {"code": code, "error": "No income data"}

    merged = _merge(income_df, cashflow_df, balance_df)
    if merged.empty:
        return {"code": code, "error": "Merge failed"}

    # 只保留比 DB 更新的行
    if latest_in_db:
        merged = merged[merged["REPORT_DATE"] > pd.Timestamp(latest_in_db)]
        if merged.empty:
            logger.info(f"[FinSync] {code}: already up to date (latest={latest_in_db})")
            return {"code": code, "stored": 0, "status": "uptodate"}

    stored = await _upsert(code, merged)
    logger.info(f"[FinSync] {code}: {stored} new quarters stored")
    return {"code": code, "stored": stored, "status": "ok"}


async def sync_financials_full(code: str) -> dict:
    """全量覆盖: 删除历史数据, 重新全量插入"""
    prefix = _to_prefix(code)
    if not prefix:
        return {"code": code, "error": "Unsupported code format"}

    # 删除已有数据
    async with async_session() as db:
        from sqlalchemy import delete as sa_delete
        await db.execute(
            sa_delete(FinancialStatement).where(FinancialStatement.stock_code == code)
        )
        await db.commit()

    # 重新全量拉取并插入 (复用 sync_financials)
    result = await sync_financials(code)
    result["status"] = "full"
    return result


# ═══ 内部方法 ═══════════════════════════════

def _to_prefix(code: str) -> Optional[str]:
    c = str(code).strip().upper()
    if len(c) == 6:
        if c.startswith(("5", "6", "9")): return f"SH{c}"
        if c.startswith(("0", "2", "3")): return f"SZ{c}"
    return None


def _fetch_income(prefix: str) -> pd.DataFrame:
    import akshare as ak
    df = ak.stock_profit_sheet_by_quarterly_em(symbol=prefix)
    df = df.rename(columns={
        "OPERATE_INCOME": "revenue",
        "PARENT_NETPROFIT": "parent_profit",
        "OPERATE_COST": "operate_cost",
        "SALE_EXPENSE": "sale_expense",
        "MANAGE_EXPENSE": "manage_expense",
        "RESEARCH_EXPENSE": "rd_expense",
    })
    df["REPORT_DATE"] = pd.to_datetime(df["REPORT_DATE"])
    cols = ["REPORT_DATE", "revenue", "parent_profit", "operate_cost",
            "sale_expense", "manage_expense", "rd_expense"]
    return df[[c for c in cols if c in df.columns]]


def _fetch_cashflow(prefix: str) -> pd.DataFrame:
    import akshare as ak
    df = ak.stock_cash_flow_sheet_by_quarterly_em(symbol=prefix)
    df = df.rename(columns={"NETCASH_OPERATE": "op_cashflow"})
    df["REPORT_DATE"] = pd.to_datetime(df["REPORT_DATE"])
    return df[["REPORT_DATE", "op_cashflow"]]


def _fetch_balance(prefix: str) -> pd.DataFrame:
    import akshare as ak
    df = ak.stock_balance_sheet_by_report_em(symbol=prefix)
    df = df.rename(columns={
        "INVENTORY": "inventory",
        "CONTRACT_LIAB": "contract_liability",
        "ACCOUNTS_RECE": "accounts_receivable",
        "TOTAL_ASSETS": "total_assets",
        # V5.11 fix: TOTAL_CURRENT_ASSETS 而非 CURRENT_ASSET_BALANCE (后者为0/垃圾值)
        "TOTAL_CURRENT_ASSETS": "current_assets",
        "FIXED_ASSET": "fixed_assets",
        "TOTAL_LIABILITIES": "total_liabilities",
        # ★ V5.11 新增: ROIIC/ROIC 精确计算
        "MONETARYFUNDS": "cash",
        "TOTAL_CURRENT_LIAB": "current_liabilities",
        "SHORT_LOAN": "short_loan",
        "LONG_LOAN": "long_loan",
        "ACCOUNTS_PAYABLE": "accounts_payable",
        "NONCURRENT_LIAB_1YEAR": "noncurrent_liab_1year",
    })
    # total_equity field name varies
    for col in df.columns:
        if "EQUITY" in col.upper() and "TOTAL" in col.upper():
            df = df.rename(columns={col: "total_equity"})
            break
    df["REPORT_DATE"] = pd.to_datetime(df["REPORT_DATE"])
    cols = ["REPORT_DATE", "inventory", "contract_liability", "accounts_receivable",
            "total_assets", "current_assets", "fixed_assets", "total_liabilities",
            "total_equity",
            "cash", "current_liabilities", "short_loan",
            "long_loan", "accounts_payable", "noncurrent_liab_1year"]
    return df[[c for c in cols if c in df.columns]]


def _merge(income, cashflow, balance) -> pd.DataFrame:
    merged = income.sort_values("REPORT_DATE")
    for df in [cashflow, balance]:
        if df is not None and not df.empty:
            merged = merged.merge(df, on="REPORT_DATE", how="left")
    for col in ["op_cashflow", "inventory", "contract_liability",
                "accounts_receivable", "total_assets", "current_assets",
                "fixed_assets", "total_liabilities", "total_equity",
                "cash", "current_liabilities", "short_loan",
                "long_loan", "accounts_payable", "noncurrent_liab_1year"]:
        if col not in merged.columns:
            merged[col] = 0.0
    return merged


async def _upsert(code: str, df: pd.DataFrame) -> int:
    async with async_session() as db:
        stored = 0
        for _, row in df.iterrows():
            rpt_date = row["REPORT_DATE"]
            if hasattr(rpt_date, "date"):
                rpt_date = rpt_date.date()

            # 判断报告类型
            month = rpt_date.month
            rpt_type = {3: "Q1", 6: "Q2", 9: "Q3", 12: "Q4"}.get(month, "Q")

            # Upsert by unique constraint
            res = await db.execute(
                select(FinancialStatement).where(
                    FinancialStatement.stock_code == code,
                    FinancialStatement.report_date == rpt_date))
            existing = res.scalars().first()
            if existing is None:
                existing = FinancialStatement(stock_code=code, report_date=rpt_date)
                db.add(existing)

            existing.report_type = rpt_type
            for col in ["revenue", "parent_profit", "operate_cost", "sale_expense",
                        "manage_expense", "rd_expense", "op_cashflow", "inventory",
                        "contract_liability", "accounts_receivable", "total_assets",
                        "current_assets", "fixed_assets", "total_liabilities",
                        "total_equity",
                        "cash", "current_liabilities", "short_loan",
                        "long_loan", "accounts_payable", "noncurrent_liab_1year"]:
                if col in df.columns and pd.notna(row.get(col)):
                    setattr(existing, col, float(row[col]))
            stored += 1

        await db.commit()
        return stored
