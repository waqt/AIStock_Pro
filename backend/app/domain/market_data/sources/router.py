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

        # ── Phase 2: akshare 宏观指标 ──
        try:
            import akshare as ak
            import math, pandas as pd
            loop = __import__('asyncio').get_event_loop()

            # ── 中美债券收益率 (bond_zh_us_rate) ──
            try:
                df = await loop.run_in_executor(None, ak.bond_zh_us_rate)
                if df is not None and not df.empty:
                    cols = list(df.columns)
                    date_col = cols[0]
                    # 精确列名匹配
                    col_map = {
                        'US10YT': '美国国债收益率10年',
                        'CN10YT': '中国国债收益率10年',
                        'US2Y': '美国国债收益率2年',
                        'CN2Y': '中国国债收益率2年',
                    }
                    for code, col_name in col_map.items():
                        if col_name in cols:
                            latest = df.sort_values(date_col).iloc[-1]
                            val = float(latest[col_name])
                            biz_d = str(latest[date_col])[:10]
                            if not math.isnan(val):
                                result[code] = {'name': code, 'price': val, 'change_pct': None, 'biz_date': biz_d}
                                await self._save_macro_history(code, df, date_col, col_name)
                                logger.info(f"[✅] {code}: {val}% ({biz_d})")
            except Exception as e:
                logger.warning(f"[⚠️] bond_zh_us_rate fetch failed: {e}")

            # ── 美联储利率 ──
            try:
                df = await loop.run_in_executor(None, ak.macro_bank_usa_interest_rate)
                if df is not None and not df.empty:
                    # 列: indicator, date, value, forecast, previous
                    latest = df[df['value'].notna()].iloc[-1] if 'value' in df.columns else df.iloc[-1]
                    val_col = 'value' if 'value' in df.columns else df.columns[-2]
                    date_c = df.columns[1] if len(df.columns) > 1 else df.columns[0]
                    val = float(latest[val_col])
                    biz_d = str(latest[date_c])[:10]
                    if not math.isnan(val):
                        result['US_FED_RATE'] = {'name': '美联储利率', 'price': val, 'change_pct': None, 'biz_date': biz_d}
                        logger.info(f"[✅] US_FED_RATE: {val}% ({biz_d})")
            except Exception as e:
                logger.warning(f"[⚠️] US_FED_RATE fetch failed: {e}")

            # ── 中国 LPR ──
            try:
                df = await loop.run_in_executor(None, ak.macro_china_lpr)
                if df is not None and not df.empty:
                    latest = df.sort_values(df.columns[0]).iloc[-1]
                    lpr1y = float(latest['LPR1Y']) if 'LPR1Y' in df.columns else None
                    if lpr1y and not math.isnan(lpr1y):
                        biz_d = str(latest[df.columns[0]])[:10]
                        result['CN_LPR1Y'] = {'name': 'LPR 1年期', 'price': lpr1y, 'change_pct': None, 'biz_date': biz_d}
                        # 存历史
                        hist_df = df[['trade_date' if 'trade_date' in df.columns else df.columns[0], 'LPR1Y']].copy()
                        hist_df.columns = ['obs_date', 'value']
                        hist_df['obs_date'] = pd.to_datetime(hist_df['obs_date']).dt.date
                        await self._save_macro_df('CN_LPR1Y', hist_df)
                        logger.info(f"[✅] CN_LPR1Y: {lpr1y}% ({biz_d})")
            except Exception as e:
                logger.warning(f"[⚠️] CN_LPR1Y fetch failed: {e}")

            # ── 中国 M2 同比 ──
            try:
                df = await loop.run_in_executor(None, ak.macro_china_money_supply)
                if df is not None and not df.empty:
                    m2_col = [c for c in df.columns if 'M2' in str(c) and '同比' in str(c)]
                    if m2_col and df.columns[0]:
                        latest = df.sort_values(df.columns[0]).iloc[-1]
                        val = float(latest[m2_col[0]])
                        biz_d = str(latest[df.columns[0]])[:10]
                        if not math.isnan(val):
                            result['CN_M2_YOY'] = {'name': 'M2同比', 'price': val, 'change_pct': None, 'biz_date': biz_d}
                            logger.info(f"[✅] CN_M2_YOY: {val}% ({biz_d})")
            except Exception as e:
                logger.warning(f"[⚠️] CN_M2_YOY fetch failed: {e}")

            # ── 中国 PMI ──
            try:
                df = await loop.run_in_executor(None, ak.macro_china_pmi)
                if df is not None and not df.empty:
                    date_c = df.columns[0]
                    latest = df.sort_values(date_c).iloc[-1]
                    biz_d = str(latest[date_c])[:10]
                    for col, code in [('制造业', 'CN_PMI_MFG'), ('非制造业', 'CN_PMI_NONMFG')]:
                        mcol = [c for c in df.columns if col in str(c) and '同比' not in str(c)][:1]
                        if mcol:
                            val = float(latest[mcol[0]])
                            if not math.isnan(val):
                                result[code] = {'name': f'中国{col}PMI', 'price': val, 'change_pct': None, 'biz_date': biz_d}
                                logger.info(f"[✅] {code}: {val} ({biz_d})")
            except Exception as e:
                logger.warning(f"[⚠️] CN_PMI fetch failed: {e}")

            # ── 美国 ISM PMI ──
            try:
                df = await loop.run_in_executor(None, ak.macro_usa_ism_pmi)
                if df is not None and not df.empty:
                    if 'value' in df.columns:
                        latest = df[df['value'].notna()].iloc[-1]
                        val = float(latest['value'])
                        biz_d = str(latest['date']) if 'date' in df.columns else ''
                        biz_d = biz_d[:10]
                        if not math.isnan(val):
                            result['US_ISM_PMI'] = {'name': '美国ISM PMI', 'price': val, 'change_pct': None, 'biz_date': biz_d}
                            logger.info(f"[✅] US_ISM_PMI: {val} ({biz_d})")
            except Exception as e:
                logger.warning(f"[⚠️] US_ISM_PMI fetch failed: {e}")

            # ── 美国 CPI 同比 ──
            try:
                df = await loop.run_in_executor(None, ak.macro_usa_cpi_yoy)
                if df is not None and not df.empty:
                    if 'value' in df.columns:
                        latest = df[df['value'].notna()].iloc[-1]
                        val = float(latest['value'])
                        biz_d = str(latest['date']) if 'date' in df.columns else ''
                        biz_d = biz_d[:10]
                        if not math.isnan(val):
                            result['US_CPI_YOY'] = {'name': '美国CPI同比', 'price': val, 'change_pct': None, 'biz_date': biz_d}
                            logger.info(f"[✅] US_CPI_YOY: {val}% ({biz_d})")
            except Exception as e:
                logger.warning(f"[⚠️] US_CPI_YOY fetch failed: {e}")

            # ── 中国 CPI 同比 ──
            try:
                df = await loop.run_in_executor(None, ak.macro_china_cpi_yearly)
                if df is not None and not df.empty:
                    if 'value' in df.columns:
                        latest = df[df['value'].notna()].iloc[-1]
                        val = float(latest['value'])
                        biz_d = str(latest['date']) if 'date' in df.columns else ''
                        biz_d = biz_d[:10]
                        if not math.isnan(val):
                            result['CN_CPI_YOY'] = {'name': '中国CPI同比', 'price': val, 'change_pct': None, 'biz_date': biz_d}
                            logger.info(f"[✅] CN_CPI_YOY: {val}% ({biz_d})")
            except Exception as e:
                logger.warning(f"[⚠️] CN_CPI_YOY fetch failed: {e}")

        except Exception as e:
            logger.warning(f"[⚠️] akshare macro fetch failed: {e}")

        # ── Phase 3: 写入 ExchangeRate 表 ──
        if result:
            from app.framework.database.session import async_session
            from app.models.models import ExchangeRate
            import math as _m
            async with async_session() as db:
                for code, info in result.items():
                    price = info['price']
                    if price is None or (isinstance(price, float) and _m.isnan(price)):
                        continue
                    biz_d = info.get('biz_date')
                    biz_date = _parse_biz_date(biz_d) if biz_d else None
                    existing = await db.get(ExchangeRate, code)
                    if existing:
                        existing.rate = price
                        existing.change_pct = info.get('change_pct')
                        existing.biz_date = biz_date
                        existing.updated_at = dt.now()
                    else:
                        db.add(ExchangeRate(code=code, name=info.get('name', code),
                            rate=price, change_pct=info.get('change_pct'),
                            biz_date=biz_date))
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
                if pd.isna(val):
                    continue
                try:
                    val = float(val)
                    if math.isnan(val) or math.isinf(val):
                        continue
                except (ValueError, TypeError):
                    continue
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

    @staticmethod
    async def _save_macro_df(code: str, df):
        """将已格式化的 DataFrame (obs_date, value) 存入 macro_history"""
        from app.framework.database.session import async_session
        from app.models.models import MacroHistory
        import math
        async with async_session() as db:
            from sqlalchemy import select
            for i in range(len(df)):
                row = df.iloc[i]
                dt_val = row['obs_date']
                val = row['value']
                if pd.isna(val): continue
                try:
                    val = float(val)
                    if math.isnan(val) or math.isinf(val): continue
                except (ValueError, TypeError): continue
                if hasattr(dt_val, 'date'): dt_val = dt_val.date()
                else:
                    from datetime import date as _d
                    try: dt_val = _d.fromisoformat(str(dt_val)[:10])
                    except: continue
                res = await db.execute(
                    select(MacroHistory).where(
                        MacroHistory.code == code, MacroHistory.obs_date == dt_val))
                if res.scalars().first(): continue
                db.add(MacroHistory(code=code, obs_date=dt_val, value=val))
            await db.commit()


# 全局单例
data_router = DataRouter()
