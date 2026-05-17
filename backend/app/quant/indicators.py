import pandas as pd
import numpy as np
from typing import List, Optional, Dict, Any

# ═══════════════════════════════════════════
# 指标注册表 (V5.1)
# ═══════════════════════════════════════════

INDICATOR_REGISTRY: Dict[str, Dict[str, Any]] = {
    "ma": {
        "name": "移动平均线",
        "category": "趋势",
        "params": {"periods": [5, 10, 20, 60, 120, 250]},
        "description": "计算指定周期的收盘价简单移动平均线(SMA)，用于判断趋势方向和支撑/压力位。",
        "output_fields": ["ma5", "ma10", "ma20", "ma60", "ma120", "ma250"],
        "chart_overlay": True  # 可叠加到K线主图
    },
    "macd": {
        "name": "MACD 异同移动平均线",
        "category": "动量",
        "params": {"fast": 12, "slow": 26, "signal": 9},
        "description": "快慢均线差值(DIF)与信号线(DEA)的交叉判断买卖点，柱状图反映多空强度。",
        "output_fields": ["macd", "macd_signal", "macd_hist"],
        "chart_overlay": False  # 副图显示
    },
    "rsi": {
        "name": "相对强弱指数 RSI",
        "category": "超买超卖",
        "params": {"period": 14},
        "description": "衡量价格变动速度和幅度的震荡指标。RSI>70超买，RSI<30超卖。",
        "output_fields": ["rsi"],
        "chart_overlay": False
    },
    "bollinger": {
        "name": "布林带",
        "category": "波动",
        "params": {"period": 20, "std_dev": 2},
        "description": "中轨(MA20)加减标准差构成上下轨，价格触及上轨可能回调，触及下轨可能反弹。",
        "output_fields": ["bb_upper", "bb_mid", "bb_lower"],
        "chart_overlay": True
    },
    "volume_ma": {
        "name": "成交量均线",
        "category": "量能",
        "params": {"periods": [5, 10, 20]},
        "description": "成交量移动平均线，放量突破均量线通常意味着资金进场。",
        "output_fields": ["v_ma5", "v_ma10", "v_ma20"],
        "chart_overlay": False
    }
}


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
