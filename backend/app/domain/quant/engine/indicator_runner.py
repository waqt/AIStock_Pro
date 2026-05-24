"""指标计算引擎 — SQLite 宽表存储, 支持时间序列直接查询"""
import pandas as pd
import numpy as np
import time
from datetime import date, datetime
from typing import List, Optional
from sqlalchemy import select
from app.framework.database.session import async_session
from app.models.models import MarketData
from app.domain.quant.indicators import INDICATOR_REGISTRY
from app.domain.quant.engine import indicator_store
from app.framework.logger import logger

# 启动时建表
indicator_store.init_db()


class IndicatorRunner:

    # ═══ 快照模式 (仅今日, 快速) ═══════════════

    @staticmethod
    async def compute_snapshot(stock_code: str, indicator_names: List[str] = None) -> dict:
        """计算单股最新日期的指标快照。
        全量指标 → 全量覆盖; 部分指标 → 只更新选中列, 保留其他列"""
        async with async_session() as db:
            df = await IndicatorRunner._load_df(db, stock_code)
            if df is None or df.empty:
                return {"stock_code": stock_code, "error": "No market data", "computed": 0}

            results = IndicatorRunner._run_indicators(df, indicator_names)
            if not results:
                return {"stock_code": stock_code, "computed": 0}

            today = date.today()
            indicator_store.upsert_snapshot(stock_code, today, results, indicator_names)
            return {"stock_code": stock_code, "computed": len(results) - 2, "mode": "snapshot"}

    # ═══ 全量历史模式 ═════════════════════════

    @staticmethod
    async def compute_historical(stock_code: str, indicator_names: List[str] = None,
                                 start_date: str = None) -> dict:
        """批量计算全量历史指标并批量写入 SQLite (向量化)"""
        async with async_session() as db:
            df = await IndicatorRunner._load_df(db, stock_code)
            if df is None or df.empty:
                return {"stock_code": stock_code, "error": "No market data", "computed": 0}

            all_series = IndicatorRunner._run_indicators_full(df, indicator_names)
            if not all_series:
                return {"stock_code": stock_code, "computed": 0}
            n_fields = len(all_series)
            logger.debug(f"[IndicatorRunner] {stock_code}: computed {n_fields} fields")

            is_partial = bool(indicator_names)
            if not start_date and not is_partial:
                indicator_store.delete_stock(stock_code)
                logger.info(f"[IndicatorRunner] {stock_code}: cleared old data (full recompute)")

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
                        try:
                            day_results[name] = float(val)
                        except (ValueError, TypeError):
                            day_results[name] = val
                day_results["price"] = float(df.iloc[i]["close"])
                batch.append({
                    "stock_code": stock_code,
                    "trade_date": trade_dt,
                    "day_results": day_results,
                })
            if batch:
                merge_mode = "merge" if is_partial else "replace"
                indicator_store.upsert_rows(batch, partial_cols=indicator_names if is_partial else None)
                logger.info(f"[IndicatorRunner] {stock_code}: stored {len(batch)} days ({merge_mode}, {n_fields} fields)")

            logger.success(f"[IndicatorRunner] {stock_code}: {len(batch)}d historical ({len(df)} market rows)")
            return {"stock_code": stock_code, "days_computed": len(batch), "mode": "historical"}

    # ═══ 增量模式 ═════════════════════════════

    @staticmethod
    async def compute_incremental(stock_code: str, indicator_names: List[str] = None) -> dict:
        """只计算上次之后的新交易日。无数据或旧数据缺筹码/拥挤度 → 全量重算"""
        last = indicator_store.get_latest(stock_code)
        if not last:
            return await IndicatorRunner.compute_historical(stock_code, indicator_names)

        last_date_str = last.get("trade_date", "")
        has_chip = last.get("chip_concentration") is not None
        has_crowding = last.get("crowding_ratio") is not None
        if not has_chip or not has_crowding:
            logger.info(f"[IndicatorRunner] {stock_code}: stale data, force full recompute")
            indicator_store.delete_stock(stock_code)
            return await IndicatorRunner.compute_historical(stock_code, indicator_names)

        try:
            last_date = pd.Timestamp(last_date_str).date()
            start = str(last_date + pd.Timedelta(days=1))
        except Exception:
            return await IndicatorRunner.compute_historical(stock_code, indicator_names)

        return await IndicatorRunner.compute_historical(stock_code, indicator_names, start)

    # ═══ 清理 ═════════════════════════════════

    @staticmethod
    async def clear_and_recompute(stock_code: str, indicator_names: List[str] = None) -> dict:
        indicator_store.delete_stock(stock_code)
        return await IndicatorRunner.compute_historical(stock_code, indicator_names)

    @staticmethod
    async def clear_all() -> dict:
        import sqlite3 as _sq
        conn = _sq.connect(indicator_store.DB_PATH)
        conn.execute("DELETE FROM indicators")
        conn.commit()
        conn.close()
        return {"deleted": "all"}

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
        """批量计算全部指标, 返回每个指标的完整时间序列 (dict of Series)
        三轮处理: 确保下游指标 (chip_pattern) 的上游依赖就绪"""
        all_series = {}
        df = df.copy()
        ctx = {}
        skipped = {}
        for _pass in (0, 1, 2):
            items = skipped if _pass == 1 else INDICATOR_REGISTRY
            for name, cls in items.items():
                if indicator_names and name not in indicator_names:
                    continue
                try:
                    missing = [f for f in cls.requires if f not in df.columns and f not in ctx]
                    if missing:
                        if _pass == 0:
                            skipped[name] = cls
                        continue
                    # 注入 ctx 中的值到 df (供 compute 通过 df.iloc[-1].get 读取)
                    for f in cls.requires:
                        if f not in df.columns and f in ctx:
                            val = ctx[f]
                            df[f] = None
                            if isinstance(val, pd.Series):
                                df.at[df.index[-1], f] = val.iloc[-1] if len(val) > 0 else None
                            else:
                                df.at[df.index[-1], f] = val
                    output = cls.compute(df)
                    if _pass >= 1:
                        logger.info(f"[IndicatorRunner] {name}: computed in pass {_pass+1} (full)")
                    for k, v in output.items():
                        if hasattr(v, 'iloc'):
                            # Series-of-list/dict (peaks/valleys) → ctx only; strings → all_series
                            if str(v.dtype) == 'object' and len(v) > 0:
                                sample = v.iloc[-1] if v.notna().any() else None
                                if isinstance(sample, (list, dict)):
                                    ctx[k] = v
                                    df[k] = v
                                else:
                                    all_series[k] = v
                                    df[k] = v
                            else:
                                all_series[k] = v
                                df[k] = v
                        elif isinstance(v, (int, float, np.floating)):
                            all_series[k] = pd.Series(float(v), index=df.index)
                            df[k] = float(v)
                            ctx[k] = float(v)
                        elif isinstance(v, (bool, np.bool_)):
                            # bool → 0/1 in all_series for daily storage
                            fv = 1.0 if v else 0.0
                            all_series[k] = pd.Series(fv, index=df.index)
                            df[k] = fv
                            ctx[k] = v
                        elif isinstance(v, (str,)):
                            all_series[k] = pd.Series(v, index=df.index)
                            ctx[k] = v
                            df[k] = v
                        elif isinstance(v, (list, dict)):
                            ctx[k] = v
                            if k not in df.columns:
                                df[k] = None
                            df.at[df.index[-1], k] = v
                except Exception as e:
                    logger.warning(f"[IndicatorRunner] {name} full: {e}")
                    if _pass == 0:
                        skipped[name] = cls
        return all_series

    @staticmethod
    def _run_indicators(df: pd.DataFrame, indicator_names: List[str] = None) -> dict:
        """快照模式: 三轮处理 + 上下文注入, 确保下游指标能读到上游输出"""
        results = {}
        ctx = {}
        skipped = {}
        for _pass in (0, 1, 2):
            items = skipped if _pass == 1 else INDICATOR_REGISTRY
            for name, cls in items.items():
                if indicator_names and name not in indicator_names:
                    continue
                try:
                    missing = [f for f in cls.requires if f not in df.columns and f not in ctx]
                    if missing:
                        if _pass == 0:
                            skipped[name] = cls
                        continue
                    # 将 ctx 中的上游输出注入 df 最后一行
                    for f in cls.requires:
                        if f not in df.columns and f in ctx:
                            val = ctx[f]
                            df[f] = None
                            if isinstance(val, pd.Series):
                                df.at[df.index[-1], f] = val.iloc[-1] if len(val) > 0 else None
                            else:
                                df.at[df.index[-1], f] = val
                    output = cls.compute(df)
                    if _pass >= 1:
                        logger.info(f"[IndicatorRunner] {name}: computed in pass {_pass+1} (snapshot)")
                    for k, v in output.items():
                        if hasattr(v, 'iloc'):
                            vals = v.dropna()
                            results[k] = float(vals.iloc[-1]) if len(vals) > 0 else None
                            if len(vals) >= 2:
                                results[f"_prev_{k}"] = float(vals.iloc[-2])
                        else:
                            results[k] = IndicatorRunner._safe_scalar(v)
                            ctx[k] = IndicatorRunner._safe_scalar(v)
                except Exception as e:
                    logger.warning(f"[IndicatorRunner] {name}: {e}")
                    if _pass == 0:
                        skipped[name] = cls
        if df is not None and len(df) > 0:
            results["price"] = float(df.iloc[-1]["close"])
        return results

    @staticmethod
    def _safe_scalar(v):
        """将标量值转为 JSON 兼容类型"""
        if v is None:
            return None
        if isinstance(v, (int, float, np.floating)):
            return float(v)
        if isinstance(v, (bool, np.bool_)):
            return bool(v)
        if isinstance(v, (str, list, dict)):
            return v
        try:
            return float(v)
        except (ValueError, TypeError):
            return str(v)
