"""
向后兼容层 — 将旧的 DataService 调用委托给新的 DataRouter。
旧代码: from app.core.data_service import data_service; await data_service.get_daily_data(...)
新架构: DataRouter 自动在 AkShare → Sina 之间切换
"""
import pandas as pd
from typing import List
from app.domain.market_data.sources.router import data_router


class DataService:
    """向后兼容的 DataService 包装器"""

    async def get_daily_data(self, stock_code: str, days: int = 120) -> pd.DataFrame:
        return await data_router.get_daily_data(stock_code, days)

    async def get_realtime_quotes(self, stock_codes: List[str]) -> dict:
        return await data_router.get_realtime_quotes(stock_codes)

    async def close(self):
        await data_router.close_all()


data_service = DataService()
