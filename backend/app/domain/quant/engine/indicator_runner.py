"""指标计算引擎 — 支持历史全量 / 增量 / 快照三种模式"""
import pandas as pd
import numpy as np
from datetime import date, datetime
from typing import List, Optional
from sqlalchemy import select, delete, and_
from app.framework.database.session import async_session
from app.models.models import MarketData, StockIndicator
from app.domain.quant.indicators import INDICATOR_REGISTRY
from app.framework.logger import logger


class IndicatorRunner:

    # ═══ 快照模式 (仅今日, 快速) ═══════════════

    @staticmethod
    async def compute_snapshot(stock_code: str, indicator_names: List[str] = None) -> dict:
        """计算单只股票最新日期的指标快照 (覆盖写入)"""
        async with async_session() as db:
            df = await IndicatorRunner._load_df(db, stock_code)
            if df is None or df.empty:
                return {"stock_code": stock_code, "error": "No market data", "computed": 0}

            results = IndicatorRunner._run_indicators(df, indicator_names)
            if not results:
                return {"stock_code": stock_code, "computed": 0}

            today = date.today()
            await db.execute(delete(StockIndicator).where(and_(
                StockIndicator.stock_code == stock_code,
                StockIndicator.analysis_date == today)))
            db.add(StockIndicator(stock_code=stock_code, indicator_type="SNAPSHOT",
                data_json=results, logic_chain={}, analysis_date=today))
            await db.commit()
            return {"stock_code": stock_code, "computed": len(results) - 2, "mode": "snapshot"}

    # ═══ 全量历史模式 ═════════════════════════

    @staticmethod
    async def compute_historical(stock_code: str, indicator_names: List[str] = None,
                                 start_date: str = None) -> dict:
        """对每根日K线计算指标, 每条独立持久化。start_date 为空则全量"""
        async with async_session() as db:
            df = await IndicatorRunner._load_df(db, stock_code)
            if df is None or df.empty:
                return {"stock_code": stock_code, "error": "No market data", "computed": 0}

            # 清理旧数据
            if not start_date:
                await db.execute(
                    delete(StockIndicator).where(StockIndicator.stock_code == stock_code))
                await db.commit()

            # 逐日计算 (滚动窗口保证长周期指标准确)
            min_days = 60  # 最少需要60天数据才开始存 (MA60等需要)
            stored = 0
            for i in range(min_days, len(df)):
                trade_dt = df.iloc[i]["trade_date"]
                if hasattr(trade_dt, 'date'):
                    trade_dt = trade_dt.date()
                if start_date and str(trade_dt) < start_date:
                    continue

                # 用截至当日的全部数据计算
                window_df = df.iloc[:i + 1]
                day_results = IndicatorRunner._run_indicators(window_df, indicator_names)
                if not day_results:
                    continue

                # 清理当天已有记录, 再写入
                await db.execute(delete(StockIndicator).where(and_(
                    StockIndicator.stock_code == stock_code,
                    StockIndicator.analysis_date == trade_dt)))
                db.add(StockIndicator(stock_code=stock_code, indicator_type="DAILY",
                    data_json=day_results, logic_chain={}, analysis_date=trade_dt))
                stored += 1

            await db.commit()
            logger.info(f"[IndicatorRunner] Historical: {stock_code} -> {stored} days stored")
            return {"stock_code": stock_code, "days_computed": stored, "mode": "historical"}

    # ═══ 增量模式 ═════════════════════════════

    @staticmethod
    async def compute_incremental(stock_code: str, indicator_names: List[str] = None) -> dict:
        """只计算上次之后的新交易日"""
        async with async_session() as db:
            # 找最后有指标的日期
            last_res = await db.execute(
                select(StockIndicator.analysis_date)
                .where(StockIndicator.stock_code == stock_code)
                .order_by(StockIndicator.analysis_date.desc()).limit(1))
            last_date = last_res.scalars().first()
            start = str(last_date + pd.Timedelta(days=1)) if last_date else None
            if not start:
                return await IndicatorRunner.compute_historical(stock_code, indicator_names)
            return await IndicatorRunner.compute_historical(stock_code, indicator_names, start)

    # ═══ 清理 + 重算 ═══════════════════════════

    @staticmethod
    async def clear_and_recompute(stock_code: str, indicator_names: List[str] = None) -> dict:
        async with async_session() as db:
            await db.execute(
                delete(StockIndicator).where(StockIndicator.stock_code == stock_code))
            await db.commit()
        return await IndicatorRunner.compute_historical(stock_code, indicator_names)

    @staticmethod
    async def clear_all() -> dict:
        async with async_session() as db:
            r = await db.execute(delete(StockIndicator))
            await db.commit()
            return {"deleted": r.rowcount}

    # ═══ 批量 ═════════════════════════════════

    @staticmethod
    async def compute_batch(stock_codes: List[str], mode: str = "snapshot",
                            indicator_names: List[str] = None) -> dict:
        total, errors = 0, 0
        method = {"snapshot": IndicatorRunner.compute_snapshot,
                  "historical": IndicatorRunner.compute_historical,
                  "incremental": IndicatorRunner.compute_incremental}.get(mode)
        for code in stock_codes:
            r = await method(code, indicator_names)
            if "error" in r: errors += 1
            else: total += 1
        return {"mode": mode, "stocks_processed": total, "errors": errors}

    # ═══ 内部 ═════════════════════════════════

    @staticmethod
    async def _load_df(db, stock_code: str) -> pd.DataFrame:
        res = await db.execute(
            select(MarketData).where(MarketData.stock_code == stock_code)
            .order_by(MarketData.trade_date.asc()))
        rows = res.scalars().all()
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame([{
            "trade_date": r.trade_date,
            "open": float(r.open or 0), "high": float(r.high or 0),
            "low": float(r.low or 0), "close": float(r.close or 0),
            "volume": float(r.volume or 0),
        } for r in rows])

    @staticmethod
    def _run_indicators(df: pd.DataFrame, indicator_names: List[str] = None) -> dict:
        results = {}
        for name, cls in INDICATOR_REGISTRY.items():
            if indicator_names and name not in indicator_names:
                continue
            try:
                missing = [f for f in cls.requires if f not in df.columns]
                if missing: continue
                output = cls.compute(df)
                for k, v in output.items():
                    if hasattr(v, 'iloc'):
                        vals = v.dropna()
                        results[k] = float(vals.iloc[-1]) if len(vals) > 0 else None
                        if len(vals) >= 2:
                            results[f"_prev_{k}"] = float(vals.iloc[-2])
                    else:
                        results[k] = float(v) if v is not None else None
            except Exception as e:
                logger.warning(f"[IndicatorRunner] {name}: {e}")
        if df is not None and len(df) > 0:
            results["price"] = float(df.iloc[-1]["close"])
        return results
