import httpx
import pandas as pd
from typing import List, Optional
from app.core.logger import logger

class DataService:
    """异步行情数据服务 (绕过代理，直接对接公开接口)"""
    
    def __init__(self):
        # 初始化异步客户端，强制禁用代理 (新版 httpx 使用 proxy 参数)
        self.client = httpx.AsyncClient(
            proxy=None,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            },
            timeout=10.0
        )

    async def get_daily_data(self, stock_code: str, days: int = 120) -> pd.DataFrame:
        """从新浪财经异步获取历史日线 (支持 A 股与港股)"""
        if len(stock_code) == 5:
            symbol = f"hk{stock_code}"
        else:
            prefix = 'sh' if stock_code.startswith(('6', '9')) else 'sz'
            symbol = f"{prefix}{stock_code}"
            
        url = f"http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={symbol}&scale=240&ma=no&datalen={days}"
        
        try:
            resp = await self.client.get(url, timeout=10.0)
            if resp.status_code != 200:
                logger.error(f"Fetch failed for {stock_code}: {resp.status_code}")
                return pd.DataFrame()
            
            data = resp.json()
            if not data: return pd.DataFrame()
            
            df = pd.DataFrame(data)
            df = df.rename(columns={'day': 'trade_date', 'vol': 'volume'})
            # 格式化日期
            df['trade_date'] = pd.to_datetime(df['trade_date']).dt.date
            # 转为数值
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col])
            
            return df
        except Exception as e:
            logger.error(f"Async fetch error {stock_code}: {str(e)}")
            return pd.DataFrame()

    async def close(self):
        await self.client.aclose()

# 全局单例
data_service = DataService()
