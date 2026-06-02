import asyncio
import time
from typing import List, Optional
import pandas as pd
from app.domain.market_data.sources.base import DataSourceProtocol, SourceStatus
from app.domain.market_data.sources.sina import SinaSource
from app.domain.market_data.sources.akshare import AkShareSource
from app.framework.logger import logger
import re


def _parse_biz_date(s: str):
    """解析业务日期, 兼容多种格式:
    '2026-05-20' / '2026年04月份' / '2026-04-30'
    """
    from datetime import date as _d
    if not s: return None
    s = str(s).strip()
    # ISO format
    try: return _d.fromisoformat(s)
    except: pass
    # Chinese format: '2026年04月份' or '2026年04月'
    import re
    m = re.match(r'(\d{4})\s*年\s*(\d{1,2})\s*月', s)
    if m:
        return _d(int(m.group(1)), int(m.group(2)), 1)
    # Try first 10 chars as ISO
    try: return _d.fromisoformat(s[:10])
    except: pass
    return None


class DataRouter:
    """
    V5.0 多源数据调度器
    - 按优先级顺序尝试数据源
    - 主源连续失败 2 次后自动降级
    - 每 5 分钟探测高优先级源是否恢复
    """

    def __init__(self):
        self._sources: List[DataSourceProtocol] = [
            AkShareSource(),   # priority 1
            SinaSource(),      # priority 2
        ]
        self._sources.sort(key=lambda s: s.priority())
        self._status: dict[str, SourceStatus] = {}
        self._active_source: Optional[str] = None
        self._last_probe_time: float = 0
        self._probe_interval: float = 300  # 5 分钟恢复探测

        # 初始化状态
        for s in self._sources:
            self._status[s.source_name()] = SourceStatus(
                name=s.source_name(),
                priority=s.priority()
            )

    # ── 对外接口 ──────────────────────────

    async def get_daily_data(self, stock_code: str, days: int = 120) -> pd.DataFrame:
        """通过多源调度获取日线数据"""
        for source in self._sources:
            name = source.source_name()
            status = self._status[name]

            # 连续失败 2 次则跳过
            if status.error_count >= 2:
                logger.warning(f"[⚠️] Skipping {name} (errors={status.error_count})")
                continue

            t0 = time.time()
            df = await source.get_daily_data(stock_code, days)
            elapsed_ms = (time.time() - t0) * 1000

            if not df.empty:
                status.latency_ms = round(elapsed_ms, 1)
                status.error_count = 0
                status.online = True
                status.last_used = pd.Timestamp.now().isoformat()
                self._active_source = name
                logger.info(f"[+] {stock_code} data from {name} ({elapsed_ms:.0f}ms)")
                return df
            else:
                status.error_count += 1
                if status.error_count >= 2:
                    status.online = False
                    logger.warning(f"[⚠️] {name} marked OFFLINE after 2 consecutive failures")

        logger.error(f"[❌] All sources failed for {stock_code}")
        return pd.DataFrame()

    async def get_realtime_quotes(self, stock_codes: List[str]) -> dict:
        """获取实时行情 — 优先 AkShare"""
        for source in self._sources:
            if hasattr(source, 'get_realtime_quotes'):
                quotes = await source.get_realtime_quotes(stock_codes)
                if quotes:
                    self._active_source = source.source_name()
                    return quotes
        return {}

    def get_source_status(self) -> List[dict]:
        """获取所有数据源状态"""
        return [
            {
                "name": s.source_name(),
                "priority": s.priority(),
                "online": self._status[s.source_name()].online,
                "latency": f"{self._status[s.source_name()].latency_ms:.0f}ms",
                "error_count": self._status[s.source_name()].error_count,
                "last_used": self._status[s.source_name()].last_used or "—"
            }
            for s in self._sources
        ]

    def get_priority_chain(self) -> List[str]:
        """获取数据源优先级链路"""
        return [s.source_name() for s in self._sources]

    def get_active_source(self) -> str:
        """获取最近一次成功使用的数据源"""
        return self._active_source or "—"

    # ── 健康管理 ──────────────────────────

    async def probe_all(self):
        """主动探测所有数据源健康状态"""
        now = time.time()
        if now - self._last_probe_time < self._probe_interval:
            return
        self._last_probe_time = now

        for source in self._sources:
            name = source.source_name()
            t0 = time.time()
            ok = await source.health_check()
            elapsed = (time.time() - t0) * 1000
            status = self._status[name]
            status.latency_ms = round(elapsed, 1)
            if ok:
                status.online = True
                status.error_count = 0
                logger.debug(f"[+] {name} probe OK ({elapsed:.0f}ms)")
            else:
                logger.warning(f"[⚠️] {name} probe FAILED")

    async def close_all(self):
        for source in self._sources:
            try:
                await source.close()
            except Exception:
                pass

# 全局单例
data_router = DataRouter()
