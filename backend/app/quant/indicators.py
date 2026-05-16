import pandas as pd
import numpy as np
from typing import List, Optional

class Indicators:
    """标准化技术指标计算算子"""

    @staticmethod
    def moving_average(df: pd.DataFrame, periods: List[int] = [5, 10, 20, 60, 120, 250]) -> pd.DataFrame:
        """计算移动平均线 (支持多周期)"""
        for p in periods:
            df[f'ma{p}'] = df['close'].rolling(window=p).mean()
        return df

    @staticmethod
    def macd(df: pd.DataFrame, fast=12, slow=26, signal=9) -> pd.DataFrame:
        """计算 MACD 指标"""
        ema_fast = df['close'].ewm(span=fast, adjust=False).mean()
        ema_slow = df['close'].ewm(span=slow, adjust=False).mean()
        df['macd'] = ema_fast - ema_slow
        df['macd_signal'] = df['macd'].ewm(span=signal, adjust=False).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']
        return df

    @staticmethod
    def rsi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """计算 RSI 指标"""
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        return df

    @staticmethod
    def bollinger_bands(df: pd.DataFrame, period=20, std_dev=2) -> pd.DataFrame:
        """计算布林带"""
        df['bb_mid'] = df['close'].rolling(window=period).mean()
        std = df['close'].rolling(window=period).std()
        df['bb_upper'] = df['bb_mid'] + (std * std_dev)
        df['bb_lower'] = df['bb_mid'] - (std * std_dev)
        return df

    @staticmethod
    def volume_ma(df: pd.DataFrame, periods: List[int] = [5, 10, 20]) -> pd.DataFrame:
        """计算成交量均线"""
        for p in periods:
            df[f'v_ma{p}'] = df['volume'].rolling(window=p).mean()
        return df

    @classmethod
    def calculate_all(cls, df: pd.DataFrame) -> pd.DataFrame:
        """一键计算常用基础指标"""
        df = df.copy().sort_values('trade_date')
        df = cls.moving_average(df)
        df = cls.macd(df)
        df = cls.rsi(df)
        df = cls.bollinger_bands(df)
        df = cls.volume_ma(df)
        return df
