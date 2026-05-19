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
        """批量计算全量历史指标并批量写入 (向量化, 非逐日循环)"""
        async with async_session() as db:
            df = await IndicatorRunner._load_df(db, stock_code)
            if df is None or df.empty:
                return {"stock_code": stock_code, "error": "No market data", "computed": 0}

            # 一次性计算全部指标时间序列 (向量化)
            all_series = IndicatorRunner._run_indicators_full(df, indicator_names)
            if not all_series:
                return {"stock_code": stock_code, "computed": 0}

            # 清理旧数据
            if not start_date:
                await db.execute(
                    delete(StockIndicator).where(StockIndicator.stock_code == stock_code))
                await db.commit()

            # 批量写入: 每个交易日一条记录
            min_days = 60
            batch = []
            for i in range(min_days, len(df)):
                trade_dt = df.iloc[i]["trade_date"]
                if hasattr(trade_dt, 'date'):
                    trade_dt = trade_dt.date()
                if start_date and str(trade_dt) < start_date:
                    continue
                day_results = {}
                for name, series in all_series.items():
                    val = series.iloc[i]
                    if pd.notna(val):
                        day_results[name] = float(val)
                    # 前一值
                    if i >= 1:
                        prev_val = series.iloc[i - 1]
                        if pd.notna(prev_val):
                            day_results[f"_prev_{name}"] = float(prev_val)
                day_results["price"] = float(df.iloc[i]["close"])
                batch.append(StockIndicator(
                    stock_code=stock_code, indicator_type="DAILY",
                    data_json=day_results, logic_chain={}, analysis_date=trade_dt))
            if batch:
                db.add_all(batch)
                await db.commit()

            logger.info(f"[IndicatorRunner] Historical: {stock_code} -> {len(batch)} days stored")
            return {"stock_code": stock_code, "days_computed": len(batch), "mode": "historical"}

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
    def _run_indicators_full(df: pd.DataFrame, indicator_names: List[str] = None) -> dict:
        """批量计算全部指标, 返回每个指标的完整时间序列 (dict of Series)"""
        all_series = {}
        for name, cls in INDICATOR_REGISTRY.items():
            if indicator_names and name not in indicator_names:
                continue
            try:
                missing = [f for f in cls.requires if f not in df.columns]
                if missing: continue
                output = cls.compute(df)
                for k, v in output.items():
                    if hasattr(v, 'iloc'):
                        all_series[k] = v
                    # 跳过标量输出 (如 chip_pattern 的 dict)
            except Exception as e:
                logger.warning(f"[IndicatorRunner] {name} full: {e}")
        return all_series

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
