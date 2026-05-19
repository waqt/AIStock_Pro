"""策略基类 — TiminStrategy + SignalResult + 装饰器自注册"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel


class SignalResult(BaseModel):
    stock_code: str
    strategy_name: str = ""
    strategy_category: str = ""
    signal: str = "HOLD"
    confidence: float = 0.5
    reasoning: str = ""
    indicators_snapshot: dict = {}
    weight: float = 1.0
    generated_at: str = ""

    @classmethod
    def create(cls, stock_code: str, strategy_name: str, category: str,
               signal: str, confidence: float, reasoning: str,
               snapshot: dict = None, weight: float = 1.0):
        return cls(
            stock_code=stock_code, strategy_name=strategy_name,
            strategy_category=category, signal=signal,
            confidence=round(confidence, 2), reasoning=reasoning,
            indicators_snapshot=snapshot or {},
            weight=weight,
            generated_at=datetime.now().isoformat(),
        )


class StrategyDetail(BaseModel):
    strategy_name: str
    category: str
    signal: str
    confidence: float
    reasoning: str

    @classmethod
    def from_signal(cls, s: SignalResult):
        return cls(strategy_name=s.strategy_name, category=s.strategy_category,
                   signal=s.signal, confidence=s.confidence, reasoning=s.reasoning)


class VoteSummary(BaseModel):
    buy_count: int = 0
    sell_count: int = 0
    hold_count: int = 0
    buy_score: float = 0.0
    sell_score: float = 0.0
    decision_logic: str = ""


class RiskFlags(BaseModel):
    chip_risk: bool = False
    crowding_risk: bool = False
    crowding_detail: str = ""


class DecisionReport(BaseModel):
    stock_code: str
    decision_date: str
    strategy_results: List[StrategyDetail] = []
    final_signal: str = "HOLD"
    final_confidence: float = 0.0
    vote_summary: VoteSummary = VoteSummary()
    risk_flags: RiskFlags = RiskFlags()


# 策略注册表
_registry: Dict[str, type] = {}


def register_strategy(cls):
    _registry[cls.name] = cls
    return cls


def get_registry() -> dict:
    return _registry


class TimingStrategy(ABC):
    """择时策略基类"""
    name: str = ""
    description: str = ""
    category: str = "traditional"
    required_indicators: List[str] = []
    weight: float = 1.0

    async def load_indicators(self, stock_code: str) -> dict:
        """加载策略所需的指标数据"""
        from app.framework.database.session import async_session
        from app.models.models import StockIndicator
        from sqlalchemy import select
        async with async_session() as db:
            res = await db.execute(
                select(StockIndicator.data_json)
                .where(StockIndicator.stock_code == stock_code)
                .order_by(StockIndicator.analysis_date.desc())
                .limit(1)
            )
            row = res.scalars().first()
            return row or {}

    @abstractmethod
    async def analyze(self, stock_code: str) -> SignalResult:
        ...
