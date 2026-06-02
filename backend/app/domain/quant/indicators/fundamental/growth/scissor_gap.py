"""剪刀差 — 利润增速 - 营收增速"""
from ..base import FinancialIndicator, register, _pct


@register
class ScissorGap(FinancialIndicator):
    name = "scissor_gap"
    label = "剪刀差"
    description = "利润YoY - 营收YoY。剪刀差为正表示利润率在扩张, 为负表示利润率在收缩。"
    judgment = ">10=大幅扩张; 5~10=扩张; 0~5=微扩; -5~0=微缩; <-5=大幅收缩。连续3Q为正=利润率改善趋势确立。"
    category = "growth"
    indicator_type = "prosperity"
    applicable_stages = ["inflection", "growth"]
    params = {}
    output = ["scissor_gap", "scissor_is_expanding", "scissor_quarters_count"]
    text_output = ["scissor_is_expanding"]
    requires = ["revenue", "profit"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        if len(financials) < 8:
            return {"scissor_gap": None, "scissor_is_expanding": False, "scissor_quarters_count": 0}
        revs = [float(q.get("revenue", 0) or 0) for q in financials]
        profits = [float(q.get("profit", q.get("parent_profit", 0)) or 0) for q in financials]
        gaps = []
        for i in range(4):
            if i + 4 < len(revs) and i + 4 < len(profits):
                rev_yoy = _pct(revs[i], revs[i + 4])
                profit_yoy = _pct(profits[i], profits[i + 4])
                if rev_yoy is not None and profit_yoy is not None:
                    gaps.append(round(profit_yoy - rev_yoy, 2))
        if not gaps:
            return {"scissor_gap": None, "scissor_is_expanding": False, "scissor_quarters_count": 0}
        expanding = sum(1 for g in gaps if g and g > 0)
        return {
            "scissor_gap": gaps[0],
            "scissor_is_expanding": expanding >= 3,
            "scissor_quarters_count": len(gaps),
        }
