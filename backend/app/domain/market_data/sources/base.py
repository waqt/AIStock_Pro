from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
import pandas as pd


@dataclass
class SourceStatus:
    name: str
    priority: int
    online: bool = True
    latency_ms: float = 0.0
    error_count: int = 0
    last_used: Optional[str] = None


class DataSourceProtocol(ABC):
    """数据源统一接口 — 所有数据源必须实现此协议"""

    @abstractmethod
    async def get_daily_data(self, stock_code: str, days: int = 120) -> pd.DataFrame:
        """获取历史日线 (OHLCV + change_pct)"""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """探测数据源是否可用"""
        ...

    @abstractmethod
    def source_name(self) -> str:
        """返回数据源名称, 如 'AkShare'"""
        ...

    @abstractmethod
    def priority(self) -> int:
        """返回默认优先级, 数字越小优先级越高"""
        ...
