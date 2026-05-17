import asyncio
import httpx
import json
import pandas as pd
from typing import List
from app.core.data_sources.base import DataSourceProtocol
from app.framework.logger import logger


class AkShareSource(DataSourceProtocol):
    """AkShare/东方财富数据源 — 优先级最高, 提供实时行情 + 日线"""

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
        return "AkShare (EastMoney)"

    def priority(self) -> int:
        return 1

    async def health_check(self) -> bool:
        try:
            resp = await self.client.get(
                "http://89.push2.eastmoney.com/api/qt/ulist/get?"
                "ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2"
                "&fields=f12&secids=0.000001",
                timeout=5.0
            )
            return resp.status_code == 200
        except Exception:
            return False

    def _market_prefix(self, stock_code: str) -> str:
        """东方财富市场前缀: 1=沪市, 0=深市"""
        if len(stock_code) == 5:
            return f"116.{stock_code}"  # 港股
        return f"{'1' if stock_code.startswith(('6', '9')) else '0'}.{stock_code}"

    def _sina_prefix(self, stock_code: str) -> str:
        """新浪市场前缀"""
        if len(stock_code) == 5:
            return f"hk{stock_code}"
        return f"{'sh' if stock_code.startswith(('6', '9')) else 'sz'}{stock_code}"

    async def get_realtime_quotes(self, stock_codes: List[str]) -> dict:
        """批量获取实时行情 (价格、PE、总市值)"""
        if not stock_codes:
            return {}
        secids = ",".join([self._market_prefix(c) for c in stock_codes])
        url = (
            f"http://89.push2.eastmoney.com/api/qt/ulist/get?"
            f"ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2"
            f"&fields=f12,f14,f2,f9,f20&secids={secids}"
        )
        try:
            resp = await self.client.get(url, timeout=10.0)
            data = resp.json()
            items = (data.get('data') or {}).get('diff', [])
            quotes = {}
            for item in items:
                code = item.get('f12', '')
                quotes[code] = {
                    "price": item.get('f2'),
                    "pe": item.get('f9'),
                    "market_cap": item.get('f20')
                }
            return quotes
        except Exception as e:
            logger.error(f"[❌] AkShare realtime failed: {e}")
            return {}

    async def get_daily_data(self, stock_code: str, days: int = 120) -> pd.DataFrame:
        """获取日线 — A股用新浪, 港股用腾讯"""
        try:
            if len(stock_code) == 5:
                return await self._fetch_tencent_hk(stock_code, days)
            else:
                return await self._fetch_sina_a(stock_code, days)
        except Exception as e:
            self._error_count += 1
            logger.error(f"[❌] AkShare daily error {stock_code}: {e}")
            return pd.DataFrame()

    async def _fetch_sina_a(self, stock_code: str, days: int) -> pd.DataFrame:
        symbol = self._sina_prefix(stock_code)
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

    async def _fetch_tencent_hk(self, stock_code: str, days: int) -> pd.DataFrame:
        """港股日线 — 使用 akshare 库 (已验证可用)"""
        try:
            import akshare as ak
            df = await asyncio.to_thread(ak.stock_hk_daily, symbol=stock_code, adjust="")
            if df is None or df.empty:
                return pd.DataFrame()
            df = df.rename(columns={'date': 'trade_date'})
            df['trade_date'] = pd.to_datetime(df['trade_date']).dt.date
            df['change_pct'] = df['close'].pct_change() * 100
            # 保留最近 days 条
            return df.tail(days) if len(df) > days else df
        except Exception as e:
            logger.error(f"[❌] AkShare HK fetch error {stock_code}: {e}")
            return pd.DataFrame()

    async def close(self):
        await self.client.aclose()
