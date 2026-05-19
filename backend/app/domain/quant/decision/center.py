"""智能决策中心 — 多策略并行调度 + 透明加权投票"""
import asyncio
from datetime import date, datetime
from typing import List, Dict

from app.domain.quant.strategies.base import (
    SignalResult, StrategyDetail, VoteSummary,
    RiskFlags, DecisionReport, TimingStrategy,
)
from app.domain.quant.strategies import STRATEGY_REGISTRY
from app.domain.quant.strategies.ai_chain.engine import AILogicChainEngine
from app.framework.logger import logger


class DecisionCenter:
    """多策略加权裁决 — 透明可追溯"""

    def __init__(self, provider=None):
        self.provider = provider

    async def decide(self, stock_codes: List[str]) -> List[DecisionReport]:
        reports = []
        for code in stock_codes:
            report = await self._decide_single(code)
            reports.append(report)
            await self._persist(report)
        return reports

    async def _decide_single(self, stock_code: str) -> DecisionReport:
        # 1. 加载指标 (复用StockIndicator中的最新快照)
        indicators = await self._load_all_indicators(stock_code)

        # 2. 并行执行所有策略
        tasks = []
        for name, strategy_cls in STRATEGY_REGISTRY.items():
            tasks.append(self._run_one(name, strategy_cls, stock_code, indicators))

        results: List[SignalResult] = await asyncio.gather(*tasks)
        results = [r for r in results if r is not None]

        # 3. 加权投票
        return self._aggregate(stock_code, results)

    async def _run_one(self, name: str, strategy_cls, stock_code: str,
                       indicators: dict) -> SignalResult:
        try:
            if hasattr(strategy_cls, 'analyze'):
                strategy = strategy_cls()
                result = await strategy.analyze(stock_code)
                return result
            # AI chain strategies via YAML
            elif name in self._ai_chain_names():
                engine = AILogicChainEngine(self.provider, name)
                result = await engine.execute(stock_code, indicators)
                result.strategy_category = "ai_chain"
                result.weight = 1.2
                return result
        except Exception as e:
            logger.warning(f"[DecisionCenter] Strategy {name} failed for {stock_code}: {e}")
            return SignalResult.create(stock_code, name, "traditional",
                "HOLD", 0.1, f"策略执行异常: {e}")

    def _ai_chain_names(self) -> set:
        from app.domain.quant.strategies.ai_chain.engine import AILogicChainEngine
        return {d["name"] for d in AILogicChainEngine.list_definitions()}

    def _aggregate(self, stock_code: str, results: List[SignalResult]) -> DecisionReport:
        buy_results = [r for r in results if r.signal == "BUY"]
        sell_results = [r for r in results if r.signal == "SELL"]
        hold_results = [r for r in results if r.signal == "HOLD"]

        buy_score = sum(r.confidence * getattr(r, 'weight', 1.0) for r in buy_results)
        sell_score = sum(r.confidence * getattr(r, 'weight', 1.0) for r in sell_results)

        # 判决逻辑 (透明可追溯)
        threshold_multiplier = 1.5
        if buy_score > sell_score * threshold_multiplier:
            final = "BUY"
            logic = (f"BUY_score({buy_score:.2f}) > SELL_score({sell_score:.2f}) "
                     f"× {threshold_multiplier} = {sell_score * threshold_multiplier:.2f} → BUY")
        elif sell_score > buy_score * threshold_multiplier:
            final = "SELL"
            logic = (f"SELL_score({sell_score:.2f}) > BUY_score({buy_score:.2f}) "
                     f"× {threshold_multiplier} = {buy_score * threshold_multiplier:.2f} → SELL")
        else:
            final = "HOLD"
            logic = (f"BUY_score({buy_score:.2f}) vs SELL_score({sell_score:.2f}) "
                     f"差距不足{threshold_multiplier}倍 → HOLD")

        total_score = buy_score + sell_score + 0.01
        confidence = round(max(buy_score, sell_score) / total_score, 2)

        # 风险标记
        chip_risk = any("高位多峰" in r.reasoning or "筹码" in r.reasoning for r in results)
        crowding_risk = any("拥挤" in r.reasoning for r in results)
        crowding_detail = ""
        if crowding_risk:
            for r in results:
                if "拥挤" in r.reasoning:
                    crowding_detail = r.reasoning[:100]
                    break

        return DecisionReport(
            stock_code=stock_code,
            decision_date=date.today().isoformat(),
            strategy_results=[StrategyDetail.from_signal(r) for r in results],
            final_signal=final,
            final_confidence=confidence,
            vote_summary=VoteSummary(
                buy_count=len(buy_results), sell_count=len(sell_results),
                hold_count=len(hold_results),
                buy_score=round(buy_score, 2), sell_score=round(sell_score, 2),
                decision_logic=logic,
            ),
            risk_flags=RiskFlags(
                chip_risk=chip_risk, crowding_risk=crowding_risk,
                crowding_detail=crowding_detail,
            ),
        )

    async def _load_all_indicators(self, stock_code: str) -> dict:
        from app.framework.database.session import async_session
        from app.models.models import StockIndicator
        from sqlalchemy import select
        try:
            async with async_session() as db:
                res = await db.execute(
                    select(StockIndicator.data_json)
                    .where(StockIndicator.stock_code == stock_code)
                    .order_by(StockIndicator.analysis_date.desc())
                    .limit(1)
                )
                row = res.scalars().first()
                return row or {}
        except Exception:
            return {}

    async def _persist(self, report: DecisionReport):
        from app.framework.database.session import async_session
        from app.models.models import StrategySignal
        try:
            async with async_session() as db:
                for detail in report.strategy_results:
                    sig = StrategySignal(
                        stock_code=report.stock_code,
                        strategy_name=detail.strategy_name,
                        strategy_category=detail.category,
                        signal=detail.signal,
                        confidence=detail.confidence,
                        reasoning=detail.reasoning,
                        indicators_snapshot={},
                        decision_date=date.today(),
                        generated_at=datetime.now(),
                    )
                    db.add(sig)
                await db.commit()
        except Exception as e:
            logger.warning(f"[DecisionCenter] Persist failed: {e}")


# 单例
decision_center = DecisionCenter()
