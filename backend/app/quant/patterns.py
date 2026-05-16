import pandas as pd
import numpy as np
from typing import List, Dict, Any

class Patterns:
    """逻辑导向的形态识别算子"""

    @staticmethod
    def detect_andy_123(df: pd.DataFrame) -> Dict[str, Any]:
        """Andy 123法则 (看涨版)"""
        if len(df) < 30: return {"detected": False}
        
        last_low = df['low'].iloc[-20:-5].min()
        recent_min = df['low'].iloc[-5:].min()
        last_high = df['high'].iloc[-20:-5].max()
        current_close = df['close'].iloc[-1]

        # 逻辑链条
        logic_steps = [
            {"step": "趋势回踩", "pass": bool(recent_min > last_low), "desc": "低点抬高，未创新低"},
            {"step": "结构突破", "pass": bool(current_close > last_high), "desc": "放量突破前高结构位"}
        ]

        detected = all(s['pass'] for s in logic_steps)
        return {
            "detected": detected,
            "name": "Andy-123法则",
            "logic_chain": logic_steps,
            "score": 85 if detected else 0
        }

    @staticmethod
    def detect_joy_bottom(df: pd.DataFrame) -> Dict[str, Any]:
        """Joy 底部三步曲"""
        if len(df) < 30: return {"detected": False}
        
        avg_v_15 = df['volume'].iloc[-15:-1].mean()
        curr_v = df['volume'].iloc[-1]
        price_std = df['close'].iloc[-15:-1].std()
        avg_p_15 = df['close'].iloc[-15:-1].mean()
        curr_p = df['close'].iloc[-1]

        logic_steps = [
            {"step": "地量筑底", "pass": bool(avg_v_15 < df['volume'].mean() * 0.8), "desc": "近期持续缩量"},
            {"step": "窄幅震荡", "pass": bool((price_std / avg_p_15) < 0.02), "desc": "价格波动极小，蓄势充分"},
            {"step": "放量启动", "pass": bool(curr_v > avg_v_15 * 1.5 and curr_p > avg_p_15 * 1.03), "desc": "今日放量长阳突破"}
        ]

        detected = all(s['pass'] for s in logic_steps)
        return {
            "detected": detected,
            "name": "Joy-底部三步曲",
            "logic_chain": logic_steps,
            "score": 92 if detected else 0
        }

    @staticmethod
    def detect_top_risk(df: pd.DataFrame) -> Dict[str, Any]:
        """风险预警：天量滞涨或顶背离"""
        if len(df) < 20: return {"detected": False}
        
        curr_v = df['volume'].iloc[-1]
        v_ma10 = df['v_ma10'].iloc[-1] if 'v_ma10' in df.columns else df['volume'].mean()
        change = (df['close'].iloc[-1] - df['close'].iloc[-2]) / df['close'].iloc[-2]

        logic_steps = [
            {"step": "天量信号", "pass": bool(curr_v > v_ma10 * 2.5), "desc": "成交量异常放大"},
            {"step": "滞涨特征", "pass": bool(abs(change) < 0.01), "desc": "股价涨不动，筹码派发明显"}
        ]

        detected = all(s['pass'] for s in logic_steps)
        return {
            "detected": detected,
            "name": "高位天量滞涨",
            "type": "BEARISH",
            "logic_chain": logic_steps,
            "score": 90 if detected else 0
        }

    @classmethod
    def scan(cls, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """扫描所有形态算子"""
        results = []
        # 执行各算子并收集通过逻辑链的结果
        for method in [cls.detect_andy_123, cls.detect_joy_bottom, cls.detect_top_risk]:
            res = method(df)
            if res["detected"]:
                results.append(res)
        return results
