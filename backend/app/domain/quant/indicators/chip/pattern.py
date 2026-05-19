"""筹码形态识别 — 六大形态判定 + 操作信号"""
from ..base import BaseIndicator, register
import numpy as np

@register
class ChipPatternIndicator(BaseIndicator):
    name = "chip_pattern"
    category = "chip"
    params = {"window": 90, "concentration_threshold": 12.0}
    output = ["chip_pattern", "chip_signal", "chip_pattern_detail"]
    requires = ["close"]

    @classmethod
    def compute(cls, df):
        """需要依赖 chip_concentration 和 chip_peak_price 的输出。
        这里只做形态判断逻辑, 数据从 context 传入。
        """
        # 此算子需要前置 chip_concentration 和 chip_peak_price 的结果
        # 实际使用时由 IndicatorLoader 串联调用
        return {"chip_pattern": "unknown", "chip_signal": "HOLD", "chip_pattern_detail": {}}

    @classmethod
    def classify(cls, close: float, concentration: float, peaks: list,
                prev_concentration: float = None, price_change_20d: float = 0) -> dict:
        """根据筹码集中度 + 峰值 + 价格位置 → 形态判定"""
        if concentration is None:
            return {"chip_pattern": "insufficient_data", "chip_signal": "HOLD", "chip_pattern_detail": {}}

        pattern = "unknown"
        signal = "HOLD"
        detail = {}

        # 形态1: 低位单峰密集 — 集中度高, 单峰, 价格在峰值附近
        if concentration >= 12.0 and len(peaks) == 1:
            pattern = "低位单峰密集"
            signal = "BUY"
            detail = {"meaning": "主力吸筹完毕, 筹码锁定度高", "action": "高配/买入"}

        # 形态2: 洗盘回归密集 — 集中度高, 价格回调<20%
        elif concentration >= 10.0 and len(peaks) == 1 and price_change_20d < 0 and price_change_20d > -20:
            pattern = "洗盘回归密集"
            signal = "BUY"
            detail = {"meaning": "主力拉升后洗盘, 底部筹码未动", "action": "加仓"}

        # 形态3: 多峰密集上行 — 多峰, 仍有底部峰
        elif 8.0 <= concentration < 12.0 and len(peaks) >= 2:
            pattern = "多峰密集上行"
            signal = "BUY"
            detail = {"meaning": "趋势拉升, 筹码滚雪球式换手", "action": "持有, 上调止损"}

        # 形态4: 向上突破高位密集 — 价格高于峰值, 放量
        elif concentration >= 8.0 and close > peaks[0] if peaks else False:
            pattern = "向上突破高位密集"
            signal = "BUY"
            detail = {"meaning": "突破高位筹码密集区", "action": "逐步减仓, 若换手率过高撤离"}

        # 形态5: 上峰消失, 高位分散 — 集中度低, 多峰在高位
        elif concentration < 8.0 and len(peaks) >= 2:
            if prev_concentration and concentration < prev_concentration * 0.7:
                pattern = "上峰消失高位分散"
                signal = "SELL"
                detail = {"meaning": "主力已彻底派发, 散户站岗", "action": "强制清仓"}

        # 形态6: 缺失筹码(跳空缺口) — 急涨急跌
        elif concentration < 5.0:
            pattern = "筹码分散"
            signal = "HOLD"
            detail = {"meaning": "筹码不集中, 无明显主力迹象", "action": "观望"}

        # 低集中度
        if concentration < 5.0 and prev_concentration and prev_concentration > 8.0:
            pattern = "上峰消失高位分散"
            signal = "SELL"
            detail = {"meaning": "筹码从集中变分散, 主力出货", "action": "强制清仓"}

        return {
            "chip_pattern": pattern,
            "chip_signal": signal,
            "chip_pattern_detail": detail,
        }
