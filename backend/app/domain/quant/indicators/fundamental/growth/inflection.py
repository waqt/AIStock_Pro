"""拐点信号 — 营收加速/利润反转/R&D占比趋势/QoQ"""
from ..base import FinancialIndicator, register, _pct


@register
class RevenueAcceleration(FinancialIndicator):
    name = "revenue_acceleration"
    label = "营收加速"
    description = "最新单季YoY增速相比前一季是提升(加速)还是下降(减速)。相邻两期比较,非趋势判断。"
    judgment = "accelerating=增速提升; decelerating=增速放缓; stable=变化<2pp。加速需结合后续确认趋势,减速注意拐点风险。"
    category = "growth"
    indicator_type = "prosperity"
    applicable_stages = ["inflection", "growth"]
    params = {}
    output = ["revenue_acceleration"]
    text_output = ["revenue_acceleration"]
    requires = ["revenue"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        if len(financials) < 9:
            return {"revenue_acceleration": None}
        latest_yoy = _pct(float(financials[0].get("revenue", 0) or 0), float(financials[4].get("revenue", 0) or 0))
        prev_yoy = _pct(float(financials[1].get("revenue", 0) or 0), float(financials[5].get("revenue", 0) or 0))
        if latest_yoy is None or prev_yoy is None:
            return {"revenue_acceleration": None}
        # 使用绝对百分点变化: 对大小基数都公平
        if latest_yoy > prev_yoy + 2.0:
            return {"revenue_acceleration": "accelerating"}
        elif latest_yoy < prev_yoy - 2.0:
            return {"revenue_acceleration": "decelerating"}
        return {"revenue_acceleration": "stable"}


@register
class ProfitTurnaround(FinancialIndicator):
    name = "profit_turnaround"
    label = "利润反转"
    description = "利润从亏损到盈利的拐点信号。识别转折型投资机会。"
    judgment = "turnaround=利润从负转正,可能处于经营拐点; sustained=持续盈利; risk=利润从正转负,需警惕; negative=持续亏损。"
    category = "growth"
    indicator_type = "prosperity"
    applicable_stages = ["startup", "inflection"]
    params = {}
    output = ["profit_turnaround"]
    text_output = ["profit_turnaround"]
    requires = ["profit"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        if len(financials) < 8:
            return {"profit_turnaround": None}
        cur_profits = [float(q.get("profit", q.get("parent_profit", 0)) or 0) for q in financials[:4]]
        prev_profits = [float(q.get("profit", q.get("parent_profit", 0)) or 0) for q in financials[4:8]]
        cur_any_positive = any(p > 0 for p in cur_profits)
        prev_any_positive = any(p > 0 for p in prev_profits)
        if not prev_any_positive and cur_any_positive:
            return {"profit_turnaround": "turnaround"}
        if cur_any_positive and prev_any_positive:
            return {"profit_turnaround": "sustained"}
        if prev_any_positive and not cur_any_positive:
            return {"profit_turnaround": "risk"}
        return {"profit_turnaround": "negative"}


@register
class RDToRevenueTrend(FinancialIndicator):
    name = "rd_to_revenue_trend"
    label = "研发费用率趋势"
    description = "研发费用/营收的比例变化趋势: rising/stable/declining。"
    judgment = "rising=公司在加大研发投入构建护城河; declining(营收增长快于研发)=规模化效应显现; declining(研发削减)=需关注。"
    category = "growth"
    indicator_type = "moat"
    applicable_stages = ["startup", "inflection", "growth"]
    params = {}
    output = ["rd_to_revenue_trend"]
    text_output = ["rd_to_revenue_trend"]
    requires = ["rd_expense", "revenue"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        if len(financials) < 4:
            return {"rd_to_revenue_trend": None}
        ratios = []
        for q in financials[:4]:
            rev = float(q.get("revenue", 0) or 0)
            rd = float(q.get("rd_expense", 0) or 0)
            ratios.append(rd / rev if rev else 0)
        if len(ratios) >= 3 and ratios[0] > ratios[1] > ratios[2]:
            return {"rd_to_revenue_trend": "rising"}
        if len(ratios) >= 3 and ratios[0] < ratios[1] < ratios[2]:
            return {"rd_to_revenue_trend": "declining"}
        return {"rd_to_revenue_trend": "stable"}


@register
class RevenueQoQ(FinancialIndicator):
    name = "revenue_qoq"
    label = "营收环比(%)"
    description = "营收环比增速。比同比更敏感的短期景气指标,但受季节性影响大。"
    judgment = ">20%=爆发式增长(需确认可持续性); 10~20%=强劲; 0~10%=正常; <0%=环比下滑。季节性强的行业需与去年同期环比对比。"
    category = "growth"
    indicator_type = "prosperity"
    applicable_stages = ["inflection", "growth"]
    params = {}
    output = ["revenue_qoq"]
    requires = ["revenue"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        if len(financials) < 2:
            return {"revenue_qoq": None}
        cur = float(financials[0].get("revenue", 0) or 0)
        prev = float(financials[1].get("revenue", 0) or 0)
        return {"revenue_qoq": _pct(cur, prev)}
