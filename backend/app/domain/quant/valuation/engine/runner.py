"""ValuationRunner — 估值计算引擎

职责:
  1. 从 DB 拉取所需数据 (StockValuation / FinancialStatement / MarketData)
  2. 遍历 VALUATION_REGISTRY 所有方法，gather_data → compute
  3. 结果写入 SQLite valuation_metrics 表

支持三种模式:
  - snapshot: 仅当天
  - incremental: 补充缺失日期
  - historical: 全量从上市日起算

与 IndicatorRunner 模式一致，但估值方法不需要 3-pass ctx 注入
（估值方法间无指标级别的依赖关系）。
"""
import asyncio
from datetime import date, datetime, timedelta
from typing import Optional
from app.framework.logger import logger
from app.framework.database.session import async_session
from app.models.models import StockValuation, FinancialStatement, MarketData, StockMaster
from sqlalchemy import select, func, collate
import numpy as np

try:
    from app.domain.quant.valuation.engine import store as valuation_store
except ImportError:
    from app.domain.quant.valuation.engine import store as valuation_store


class ValuationRunner:
    """估值计算引擎"""

    def __init__(self):
        self.store = valuation_store
        self.store.init_db()

    # ═══ 数据加载 ═══════════════════════════════

    async def _load_valuation_data(self, code: str) -> dict:
        """从 StockValuation 加载最新估值数据"""
        async with async_session() as db:
            row = await db.get(StockValuation, code)
            if not row:
                return {}
            return {
                "pe_ttm": row.pe_ttm,
                "pb": row.pb,
                "mcap_yi": row.mcap_yi,
                "roe": row.roe,
                "dividend_yield": row.dividend_yield,
                "eps_growth_3y": row.eps_growth_3y,
                "float_mcap_yi": row.float_mcap_yi,
                "turnover_pct": row.turnover_pct,
            }

    async def _load_financial_data(self, code: str) -> dict:
        """从 FinancialStatement 加载 TTM 财务数据"""
        async with async_session() as db:
            rows = await db.execute(
                select(FinancialStatement)
                .where(FinancialStatement.stock_code == code)
                .order_by(FinancialStatement.report_date.desc())
                .limit(8)
            )
            quarters = rows.scalars().all()
        if not quarters:
            return {}

        # TTM: 最近 4 个季度的合计
        recent_4 = quarters[:4]
        rev_ttm = sum(q.revenue or 0 for q in recent_4) if len(recent_4) >= 4 else None
        profit_ttm = sum(q.parent_profit or 0 for q in recent_4) if len(recent_4) >= 4 else None
        ocf_ttm = sum(q.op_cashflow or 0 for q in recent_4) if len(recent_4) >= 4 else None

        rd_ttm = sum(q.rd_expense or 0 for q in recent_4) if len(recent_4) >= 4 else None

        latest = quarters[0]
        return {
            "revenue_ttm": rev_ttm,
            "profit_ttm": profit_ttm,
            "ocf_ttm": ocf_ttm,
            "rd_expense_ttm": rd_ttm,
            "total_assets": latest.total_assets,
            "total_liabilities": latest.total_liabilities,
            "total_equity": latest.total_equity,
            "cash": latest.cash,
            "current_assets": latest.current_assets,
            "current_liabilities": latest.current_liabilities,
            "fixed_assets": latest.fixed_assets,
            "short_loan": latest.short_loan,
            "long_loan": latest.long_loan,
        }

    async def _load_stock_info(self, code: str) -> dict:
        """从 StockMaster 加载基本信息"""
        async with async_session() as db:
            row = await db.get(StockMaster, code)
            if not row:
                return {}
            return {
                "industry": row.industry,
                "total_shares": row.total_shares,
                "float_shares": row.float_shares,
                "list_date": row.list_date,
                "stock_name": row.stock_name,
            }

    async def _load_latest_price(self, code: str) -> Optional[float]:
        """从 MarketData 读最新收盘价 (唯一权威源)"""
        from sqlalchemy import select as _select
        async with async_session() as db:
            row = await db.execute(
                _select(MarketData.close)
                .where(MarketData.stock_code == code)
                .order_by(MarketData.trade_date.desc())
                .limit(1)
            )
            price = row.scalar()
            return float(price) if price else None

    async def _load_pe_history(self, code: str, lookback_days: int = 1095) -> list:
        """加载历史 PE 序列用于百分位计算 (从 StockValuation 的变化历史)

        注意: StockValuation 只有最新值, 历史 PE 序列需要从 MarketData 推算。
        简化: 用每日 price / eps_ttm 近似。
        """
        async with async_session() as db:
            val = await db.get(StockValuation, code)
            if not val or not val.pe_ttm or not val.mcap_yi:
                return []

            # 市盈率变化主要由股价驱动, 用日线 close 推算每日 PE
            rows = await db.execute(
                select(MarketData.trade_date, MarketData.close)
                .where(MarketData.stock_code == code)
                .order_by(MarketData.trade_date.desc())
                .limit(lookback_days)
            )
            prices = rows.all()
            if not prices or not val.pe_ttm:
                return []

            # 用最新 PE 和最新价反推 eps, 然后每天价格 × 这个 eps 估算每日 PE
            latest_price = prices[0].close or 0
            if latest_price <= 0:
                return []
            eps_est = latest_price / val.pe_ttm
            return [round((p.close or 0) / eps_est, 2) for p in reversed(prices) if (p.close or 0) > 0]

    async def _load_pb_history(self, code: str, lookback_days: int = 1095) -> list:
        """加载历史 PB 序列"""
        async with async_session() as db:
            val = await db.get(StockValuation, code)
            if not val or not val.pb or not val.mcap_yi:
                return []

            rows = await db.execute(
                select(MarketData.trade_date, MarketData.close)
                .where(MarketData.stock_code == code)
                .order_by(MarketData.trade_date.desc())
                .limit(lookback_days)
            )
            prices = rows.all()
            if not prices or not val.pb:
                return []

            # 用最新 PB 反推 BVPS
            val_info = await db.get(StockMaster, code)
            shares = val_info.total_shares if val_info else None
            if not shares or shares <= 0:
                return []
            latest_price = prices[0].close or 0
            if latest_price <= 0:
                return []
            mcap = val.mcap_yi * 1e8  # 亿→元
            bvps_est = mcap / shares / val.pb if val.pb else 0
            if bvps_est <= 0:
                return []
            return [round((p.close or 0) / bvps_est, 2) for p in reversed(prices) if (p.close or 0) > 0]

    async def _load_price_history(self, code: str, days: int = 1095) -> list:
        """加载历史收盘价"""
        async with async_session() as db:
            rows = await db.execute(
                select(MarketData.trade_date, MarketData.close)
                .where(MarketData.stock_code == code)
                .order_by(MarketData.trade_date.desc())
                .limit(days)
            )
            return [r.close for r in rows.all() if r.close]

    # ═══ 财务指标加载 (SQLite) ═══════════════════

    def _load_financial_indicators(self, code: str) -> dict:
        """从 financial_indicators (SQLite) 加载最新财务指标快照

        返回动态估值方法需要的营收增速/毛利率/经营杠杆/剪刀差等数据。
        """
        try:
            from app.domain.quant.engine import indicator_store
            row = indicator_store.get_financial_latest(code)
            if not row:
                return {}
            KEYS = [
                "rev_yoy_latest", "avg_rev_yoy_4q", "rev_yoy_ttm", "revenue_4q_yi",
                "gross_margin_pct", "net_margin_pct", "operating_margin_pct",
                "gross_margin_trend", "gross_margin_chg_pp",
                "scissor_gap", "scissor_is_expanding",
                "revenue_acceleration", "revenue_accel_pp",
                "operating_leverage", "roe", "dividend_yield",
            ]
            return {k: row.get(k) for k in KEYS}
        except Exception as e:
            logger.warning(f"[ValuationRunner] {code}: failed to load fin_indicators: {e}")
            return {}

    # ═══ 行业 PE 中位数查询 ══════════════════════

    async def _load_industry_pe_median(self, industry: str) -> Optional[float]:
        """查询同行业所有股票的 PE TTM 中位数"""
        if not industry:
            return None
        try:
            async with async_session() as db:
                rows = await db.execute(
                    select(StockValuation.pe_ttm)
                    .join(StockMaster, collate(StockMaster.stock_code, 'utf8mb4_unicode_ci') == StockValuation.stock_code)
                    .where(StockMaster.industry == industry)
                    .where(StockValuation.pe_ttm.isnot(None))
                    .where(StockValuation.pe_ttm > 0)
                )
                pe_values = [r[0] for r in rows.all()]
            if not pe_values:
                return None
            return float(np.median(pe_values))
        except Exception as e:
            logger.warning(f"[ValuationRunner] industry_pe_median failed for {industry}: {e}")
            return None

    # ═══ 主计算入口 ═════════════════════════════

    async def compute(self, stock_code: str, mode: str = "snapshot") -> dict:
        """计算单只股票的全部估值方法

        Args:
            stock_code: 股票代码
            mode: snapshot | incremental | historical

        Returns:
            {stock_code, trade_date, methods_run, errors, results}
        """
        from app.domain.quant.valuation import VALUATION_REGISTRY

        today = date.today()
        logger.info(f"[ValuationRunner] Starting {mode}: {stock_code}")

        # 1. 加载所有数据
        val_data = await self._load_valuation_data(stock_code)
        fin_data = await self._load_financial_data(stock_code)
        info = await self._load_stock_info(stock_code)
        # price 从 MarketData.close 获取 (唯一权威源)
        current_price = await self._load_latest_price(stock_code)

        if not val_data:
            logger.warning(f"[ValuationRunner] {stock_code}: no valuation data, sync first")
            return {"stock_code": stock_code, "error": "no valuation data, sync first"}

        # 2. 为需要历史数据的方法加载序列
        pe_history = None
        pb_history = None
        price_history = None
        industry_pe_median = None

        # 2b. 加载财务指标 (用于动态方法)
        fin_ind_data = None
        has_fin_ind_methods = any(
            getattr(cls, 'requires_financial_indicators', False)
            for cls in VALUATION_REGISTRY.values()
        )
        if has_fin_ind_methods:
            fin_ind_data = self._load_financial_indicators(stock_code)
            if fin_ind_data:
                logger.info(f"[ValuationRunner] {stock_code}: loaded {len(fin_ind_data)} fin_indicators")

        # 3. 两轮遍历: 先跑非 composite 方法, 再跑 composite 方法
        results = {}
        errors = []
        methods_run = []

        for name, cls in VALUATION_REGISTRY.items():
            # composite 方法(如 valuation_health)在第二轮单独处理
            if getattr(cls, 'category', '') == 'composite':
                continue
            try:
                kwargs = {
                    **val_data,
                    **fin_data,
                    **info,
                    "price": current_price,
                    **cls.params,
                }

                # 注入财务指标数据 (动态方法需要)
                if getattr(cls, 'requires_financial_indicators', False) and fin_ind_data:
                    kwargs.update(fin_ind_data)

                # 按需加载历史数据 (只加载一次)
                if cls.requires_market_data:
                    if pe_history is None:
                        pe_history = await self._load_pe_history(stock_code)
                    if pb_history is None:
                        pb_history = await self._load_pb_history(stock_code)
                    if price_history is None:
                        price_history = await self._load_price_history(stock_code)
                    kwargs["pe_history"] = pe_history
                    kwargs["pb_history"] = pb_history
                    kwargs["price_history"] = price_history

                if cls.requires_financial_data and not fin_data:
                    logger.warning(f"[ValuationRunner] {stock_code}: {name} skipped (no financial data)")
                    errors.append(f"{name}: no financial data")
                    continue

                # 行业 PE 中位数 (懒加载)
                if "industry_pe_median" in cls.requires and industry_pe_median is None:
                    industry = info.get("industry")
                    if industry:
                        industry_pe_median = await self._load_industry_pe_median(industry)
                if "industry_pe_median" in cls.requires:
                    kwargs["industry_pe_median"] = industry_pe_median

                # 检查方法是否适用于当前股票 (如 rNPV 仅适用生物医药)
                if hasattr(cls, 'is_applicable') and not cls.is_applicable(**kwargs):
                    logger.info(f"[ValuationRunner] {stock_code}: {name} skipped (not applicable)")
                    methods_run.append(name)
                    continue

                output = cls.compute(**kwargs)
                if output:
                    results.update(output)
                methods_run.append(name)

            except Exception as e:
                logger.warning(f"[ValuationRunner] {stock_code} {name} failed: {e}")
                errors.append(f"{name}: {e}")

        # 3b. 第二轮: composite 方法 (依赖其他方法的输出)
        for name, cls in VALUATION_REGISTRY.items():
            if getattr(cls, 'category', '') != 'composite':
                continue
            try:
                # 将第一轮结果作为 kwargs 注入
                output = cls.compute(**results)
                if output:
                    results.update(output)
                methods_run.append(name)
            except Exception as e:
                logger.warning(f"[ValuationRunner] {stock_code} {name} failed: {e}")
                errors.append(f"{name}: {e}")

        # 4. 写入存储 (只存估值方法输出, price/pe_ttm/pb 从 MySQL 实时读)
        if results:
            self.store.upsert_snapshot(stock_code, today, results)

        logger.info(f"[ValuationRunner] {stock_code}: {len(methods_run)} methods run, {len(errors)} errors")
        return {
            "stock_code": stock_code,
            "trade_date": str(today),
            "methods_run": methods_run,
            "errors": errors if errors else None,
            "results_count": len(results),
        }

    async def compute_batch(self, codes: list, calc_mode: str = "snapshot") -> list:
        """批量计算"""
        results = []
        for code in codes:
            r = await self.compute(code, calc_mode)
            results.append(r)
            await asyncio.sleep(0)
        return results


# 单例
valuation_runner = ValuationRunner()
