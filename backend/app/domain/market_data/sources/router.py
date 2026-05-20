import asyncio
import time
from typing import List, Optional
import pandas as pd
from app.domain.market_data.sources.base import DataSourceProtocol, SourceStatus
from app.domain.market_data.sources.sina import SinaSource
from app.domain.market_data.sources.akshare import AkShareSource
from app.framework.logger import logger


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

    # ── 宏观市场数据 (V5.4: 使用 akshare, 已验证可用) ──

    async def sync_macro_data(self) -> dict:
        """宏观数据同步: 新浪实时(汇率/大宗) + akshare(美债/利率/PPI)"""
        import httpx
        from datetime import datetime as dt, date as d
        result = {}

        # ── Phase 1: 新浪实时行情 ──
        symbols = {
            'DXY': 'hf_DINIW', 'XAU': 'hf_XAU', 'XAG': 'hf_XAG',
            'BRENT': 'hf_OIL', 'USD_CNY': 'fx_susdcny', 'HKD_CNY': 'fx_shkdcny',
        }
        try:
            codes = ','.join(symbols.values())
            url = f"http://hq.sinajs.cn/list={codes}"
            headers = {"Referer": "https://finance.sina.com.cn"}
            async with httpx.AsyncClient(proxy=None, timeout=10.0, headers=headers) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    text = resp.text
                    for code, sina_code in symbols.items():
                        pattern = f'var hq_str_{sina_code}='
                        idx = text.find(pattern)
                        if idx < 0: continue
                        start = text.find('"', idx) + 1
                        end = text.find('"', start)
                        if end < 0: continue
                        fields = text[start:end].split(',')
                        if len(fields) < 2: continue
                        price, change_pct = None, None
                        try:
                            if sina_code.startswith('fx_'):
                                price = float(fields[1]) if fields[1] and fields[1] != '0.0000000000' else None
                                prev = float(fields[2]) if len(fields) > 2 and fields[2] else None
                                if price and prev and prev > 0:
                                    change_pct = round((price - prev) / prev * 100, 4)
                            elif sina_code.startswith('hf_'):
                                price = float(fields[0]) if fields[0] and fields[0] != '0.0000' else None
                                prev = float(fields[1]) if len(fields) > 1 and fields[1] and fields[1] != '0.0000' else None
                                if price and prev and prev > 0:
                                    change_pct = round((price - prev) / prev * 100, 4)
                        except (ValueError, IndexError): pass
                        if price:
                            result[code] = {'name': code, 'price': price, 'change_pct': change_pct}
        except Exception as e:
            logger.warning(f"[⚠️] Sina macro fetch failed: {e}")

        # ── Phase 2: akshare 美债收益率 ──
        try:
            import akshare as ak
            loop = __import__('asyncio').get_event_loop()

            # 美国10年期国债收益率 (ak.bond_zh_us_rate)
            try:
                df = await loop.run_in_executor(None, ak.bond_zh_us_rate)
                if df is not None and not df.empty:
                    import math
                    # 列名可能是中文或英文, 找包含 "10" 且非中国国债的列
                    cols = list(df.columns)
                    date_col = cols[0]  # 第一列是日期
                    # 排除日期列和第2-5列(中国国债2/5/10/30), 剩余的是美国国债列
                    us_cols = cols[5:] if len(cols) > 5 else []
                    us10y_col = [c for c in us_cols if ('10' in c or '10' in str(c))]
                    if not us10y_col:
                        # 回退: 找第一个包含 '10' 的非中国列
                        us10y_col = [c for c in cols[1:] if ('10' in c or '10' in str(c)) and ('2' not in c or '10' in c)][:1]
                    if us10y_col:
                        latest = df.sort_values(date_col).iloc[-1]
                        val = float(latest[us10y_col[0]])
                        if not math.isnan(val):
                            result['US10YT'] = {'name': 'US10YT', 'price': val, 'change_pct': None}
                            await self._save_macro_history('US10YT', df, date_col, us10y_col[0])
                            logger.info(f"[✅] US10YT: {val}%")
            except Exception as e:
                logger.warning(f"[⚠️] US10YT fetch failed: {e}")

        except Exception as e:
            logger.warning(f"[⚠️] akshare macro fetch failed: {e}")

        # ── 注: 以下数据源待接入 ──
        # DXY (美元指数): Sina hf_DINIW 返回空; akshare currency_latest 需要第三方 API key
        # US_FED_RATE: ak.macro_bank_usa_interest_rate 列名乱码+NaN, 数据质量不可用
        # CN_PPI: ak.macro_china_ppi_yearly 最新值 NaN
        # US_PPI: 需要 FRED API key
        # CREDIT_IMPULSE: 需要 PBOC 社融 + GDP 计算逻辑

        # ── 写入 ExchangeRate 表 ──
        if result:
            from app.framework.database.session import async_session
            from app.models.models import ExchangeRate
            import math
            async with async_session() as db:
                for code, info in result.items():
                    price = info['price']
                    if price is None or (isinstance(price, float) and math.isnan(price)):
                        continue
                    existing = await db.get(ExchangeRate, code)
                    if existing:
                        existing.rate = price
                        existing.change_pct = info.get('change_pct')
                        existing.updated_at = dt.now()
                    else:
                        db.add(ExchangeRate(code=code, name=info.get('name', code),
                            rate=price, change_pct=info.get('change_pct')))
                await db.commit()
            logger.info(f"[✅] Macro data synced: {list(result.keys())}")
        return result

    @staticmethod
    async def _save_macro_history(code: str, df, date_col: str, value_col: str):
        """将时间序列存入 macro_history 表"""
        from app.framework.database.session import async_session
        from app.models.models import MacroHistory
        from datetime import date as d
        import math
        async with async_session() as db:
            # 使用 iloc 位置索引, 避免中文列名匹配问题
            date_idx = list(df.columns).index(date_col) if date_col in df.columns else 0
            val_idx = list(df.columns).index(value_col) if value_col in df.columns else date_idx + 1
            for i in range(len(df)):
                row = df.iloc[i]
                dt_val = row.iloc[date_idx]
                val = row.iloc[val_idx]
                if val is None or (isinstance(val, float) and math.isnan(val)):
                    continue
                val = float(val)
                # Date conversion
                if hasattr(dt_val, 'date'): dt_val = dt_val.date()
                else:
                    try: dt_val = d.fromisoformat(str(dt_val)[:10])
                    except: continue
                # Upsert
                from sqlalchemy import select
                res = await db.execute(
                    select(MacroHistory).where(
                        MacroHistory.code == code, MacroHistory.obs_date == dt_val))
                if res.scalars().first(): continue
                db.add(MacroHistory(code=code, obs_date=dt_val, value=val))
            await db.commit()
            logger.info(f"[MacroHistory] Saved {code}: {len(df)} rows")

        if result:
            from app.framework.database.session import async_session
            from app.models.models import ExchangeRate
            from datetime import datetime as dt
            async with async_session() as db:
                for code, info in result.items():
                    price = info.get('price')
                    pct = info.get('change_pct')
                    if price is None:
                        continue
                    existing = await db.get(ExchangeRate, code)
                    if existing:
                        existing.name = info['name']
                        existing.rate = price
                        existing.change_pct = pct
                        existing.updated_at = dt.now()
                    else:
                        db.add(ExchangeRate(code=code, name=info['name'], rate=price, change_pct=pct))
                await db.commit()
            logger.info(f"[✅] Macro data synced: {list(result.keys())}")
        return result


# 全局单例
data_router = DataRouter()
