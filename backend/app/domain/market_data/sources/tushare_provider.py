"""Tushare 数据提供者 — 投研分析兜底数据源"""
import pandas as pd
import tushare as ts
from typing import List, Optional
from datetime import date, timedelta
from app.framework.config import settings
from app.framework.logger import logger

# 初始化
ts.set_token(settings.TUSHARE_TOKEN)
_pro_api = None


def _get_pro():
    global _pro_api
    if _pro_api is None:
        _pro_api = ts.pro_api()
    return _pro_api


class TushareProvider:
    """Tushare 数据源 — akshare 不可用时的兜底"""

    @staticmethod
    def available() -> bool:
        return bool(settings.TUSHARE_TOKEN and settings.TUSHARE_TOKEN != "your_tushare_token")

    # ── 日线行情 ──────────────────────────────

    @staticmethod
    async def get_daily(code: str, days: int = 500) -> pd.DataFrame:
        """获取日线数据 (复权)"""
        if not TushareProvider.available():
            return pd.DataFrame()
        try:
            loop = __import__('asyncio').get_event_loop()
            return await loop.run_in_executor(None, TushareProvider._fetch_daily, code, days)
        except Exception as e:
            logger.warning(f"[Tushare] Daily {code} failed: {e}")
            return pd.DataFrame()

    @staticmethod
    def _fetch_daily(code: str, days: int) -> pd.DataFrame:
        pro = _get_pro()
        end = date.today().strftime('%Y%m%d')
        start = (date.today() - timedelta(days=days + 30)).strftime('%Y%m%d')
        df = pro.daily(ts_code=TushareProvider._ts_code(code), start_date=start, end_date=end)
        if df.empty:
            return df
        df = df.rename(columns={
            'trade_date': 'trade_date', 'open': 'open', 'high': 'high',
            'low': 'low', 'close': 'close', 'vol': 'volume', 'amount': 'amount'
        })
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        df = df.sort_values('trade_date')
        return df[['trade_date', 'open', 'high', 'low', 'close', 'volume']]

    # ── 股票基本信息 ──────────────────────────

    @staticmethod
    async def get_stock_info(code: str) -> dict:
        """获取股票基本信息: 行业/上市日期/名称等"""
        if not TushareProvider.available():
            return {}
        try:
            loop = __import__('asyncio').get_event_loop()
            return await loop.run_in_executor(None, TushareProvider._fetch_stock_info, code)
        except Exception as e:
            logger.warning(f"[Tushare] Info {code} failed: {e}")
            return {}

    @staticmethod
    def _fetch_stock_info(code: str) -> dict:
        pro = _get_pro()
        ts_code = TushareProvider._ts_code(code)
        df = pro.stock_basic(ts_code=ts_code, fields='ts_code,name,industry,list_date,area')
        if df.empty:
            # Try namechange table
            df = pro.namechange(ts_code=ts_code, fields='ts_code,name')
        if df.empty:
            return {}
        row = df.iloc[0]
        return {
            'name': row.get('name', ''),
            'industry': row.get('industry', ''),
            'list_date': row.get('list_date', ''),
        }

    @staticmethod
    def fetch_all_stock_basic() -> dict:
        """批量获取全部A股基本信息 (一次调用, 缓存友好)

        返回: {stock_code: {name, industry, list_date}, ...}
        """
        pro = _get_pro()
        try:
            df = pro.stock_basic(fields='ts_code,name,industry,list_date,market')
            if df is None or df.empty:
                logger.warning("[Tushare] fetch_all_stock_basic returned empty")
                return {}
            result = {}
            for _, row in df.iterrows():
                ts_code = str(row.get('ts_code', ''))
                if not ts_code:
                    continue
                # ts_code 格式: "000001.SZ" → "000001"
                code = ts_code.split('.')[0].strip()
                result[code] = {
                    'name': str(row.get('name', '')),
                    'industry': str(row.get('industry', '')),
                    'list_date': str(row.get('list_date', '')),
                }
            logger.info(f"[Tushare] fetch_all_stock_basic: {len(result)} stocks")
            return result
        except Exception as e:
            logger.warning(f"[Tushare] fetch_all_stock_basic failed: {e}")
            return {}

    # ── 财务数据 ──────────────────────────────

    @staticmethod
    async def get_financial(code: str, periods: int = 8) -> Optional[pd.DataFrame]:
        """获取最近N个季度的主要财务指标"""
        if not TushareProvider.available():
            return None
        try:
            loop = __import__('asyncio').get_event_loop()
            return await loop.run_in_executor(None, TushareProvider._fetch_financial, code, periods)
        except Exception as e:
            logger.warning(f"[Tushare] Financial {code} failed: {e}")
            return None

    @staticmethod
    def _fetch_financial(code: str, periods: int) -> pd.DataFrame:
        pro = _get_pro()
        ts_code = TushareProvider._ts_code(code)
        end = date.today().strftime('%Y%m%d')
        start = (date.today() - timedelta(days=periods * 120)).strftime('%Y%m%d')
        df = pro.fina_indicator(ts_code=ts_code, start_date=start, end_date=end)
        if df.empty:
            return df
        df = df.sort_values('end_date')
        cols = ['end_date', 'revenue', 'n_income', 'cfo', 'inventory', 'ar', 'total_assets',
                'total_liab', 'current_assets', 'fix_assets']
        available = [c for c in cols if c in df.columns]
        return df[available].tail(periods)

    # ── 估值 / 基本面 ─────────────────────────

    @staticmethod
    async def get_daily_basic(code: str, days: int = 10) -> pd.DataFrame:
        """获取每日估值指标: PE/PB/市值/换手率"""
        if not TushareProvider.available():
            return pd.DataFrame()
        try:
            loop = __import__('asyncio').get_event_loop()
            return await loop.run_in_executor(None, TushareProvider._fetch_daily_basic, code, days)
        except Exception as e:
            logger.warning(f"[Tushare] Basic {code} failed: {e}")
            return pd.DataFrame()

    @staticmethod
    def _fetch_daily_basic(code: str, days: int) -> pd.DataFrame:
        pro = _get_pro()
        end = date.today().strftime('%Y%m%d')
        start = (date.today() - timedelta(days=days + 5)).strftime('%Y%m%d')
        df = pro.daily_basic(ts_code=TushareProvider._ts_code(code), start_date=start, end_date=end)
        if df.empty:
            return df
        df = df.sort_values('trade_date')
        cols = ['trade_date', 'pe', 'pe_ttm', 'pb', 'total_mv', 'circ_mv', 'turnover_rate']
        available = [c for c in cols if c in df.columns]
        return df[available]

    # ── 工具 ──────────────────────────────────

    @staticmethod
    def _ts_code(code: str) -> str:
        """将 6位代码 转为 tushare 格式: 600519.SH / 000001.SZ"""
        c = str(code).strip().upper()
        if '.' in c:
            return c
        if c.startswith('6') or c.startswith('9'):
            return f'{c}.SH'
        return f'{c}.SZ'
