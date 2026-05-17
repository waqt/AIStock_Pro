import asyncio
import httpx
import json
import pandas as pd
from app.core.data_sources.base import DataSourceProtocol
from app.framework.logger import logger


class SinaSource(DataSourceProtocol):
    """新浪/腾讯财经数据源 — A 股用新浪, 港股用腾讯"""

    _is_hk = lambda self, code: len(code) == 5

    def __init__(self):
        self.client = httpx.AsyncClient(
            proxy=None,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            },
            timeout=10.0
        )
        self._error_count = 0

    def source_name(self) -> str:
        return "Sina/Tencent"

    def priority(self) -> int:
        return 2

    async def health_check(self) -> bool:
        try:
            resp = await self.client.get(
                "http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol=sh000001&scale=240&ma=no&datalen=1",
                timeout=5.0
            )
            return resp.status_code == 200
        except Exception:
            return False

    async def _fetch_sina_a_stock(self, stock_code: str, days: int) -> pd.DataFrame:
        """A股日线 — 新浪接口"""
        prefix = 'sh' if stock_code.startswith(('6', '9')) else 'sz'
        symbol = f"{prefix}{stock_code}"
        url = (
            f"http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
            f"CN_MarketData.getKLineData?symbol={symbol}&scale=240&ma=no&datalen={days}"
        )
        resp = await self.client.get(url, timeout=10.0)
        if resp.status_code != 200 or not resp.text:
            return pd.DataFrame()
        data = resp.json()
        if not data:
            return pd.DataFrame()

        df = pd.DataFrame(data)
        df = df.rename(columns={'day': 'trade_date', 'vol': 'volume'})
        df['trade_date'] = pd.to_datetime(df['trade_date']).dt.date
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col])
        df['change_pct'] = df['close'].pct_change() * 100
        if 'amount' not in df.columns:
            df['amount'] = df['close'] * df['volume']
        else:
            df['amount'] = pd.to_numeric(df['amount'])
        return df

    async def _fetch_tencent_hk_stock(self, stock_code: str, days: int) -> pd.DataFrame:
        """港股日线 — 使用 akshare 库"""
        try:
            import akshare as ak
            df = await asyncio.to_thread(ak.stock_hk_daily, symbol=stock_code, adjust="")
            if df is None or df.empty:
                return pd.DataFrame()
            df = df.rename(columns={'date': 'trade_date'})
            df['trade_date'] = pd.to_datetime(df['trade_date']).dt.date
            df['change_pct'] = df['close'].pct_change() * 100
            return df.tail(days) if len(df) > days else df
        except Exception as e:
            logger.error(f"[❌] Sina HK fetch error {stock_code}: {e}")
            return pd.DataFrame()

    async def get_daily_data(self, stock_code: str, days: int = 120) -> pd.DataFrame:
        try:
            if self._is_hk(stock_code):
                df = await self._fetch_tencent_hk_stock(stock_code, days)
            else:
                df = await self._fetch_sina_a_stock(stock_code, days)

            if df.empty:
                self._error_count += 1
            return df
        except Exception as e:
            self._error_count += 1
            logger.error(f"[❌] Sina fetch error {stock_code}: {e}")
            return pd.DataFrame()

    async def close(self):
        await self.client.aclose()
