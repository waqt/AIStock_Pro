"""
商业化拐点期指标 — "研发→收益"验证窗口
核心问题: 收入在涨, 是"真的开始赚钱"还是"增收不增利"?
"""
from .base import FinancialIndicator, register_financial


@register_financial
class RDToRevenueTrend(FinancialIndicator):
    name = "rd_to_revenue_trend"
    label = "研发费率趋势(百分点)"
    description = "研发费用率的同比变化。正数=研发费率在下降(收入增速>研发增速)，是商业化拐点确认信号。负数=费率上升(研发增速>收入增速)，仍在投入期。"
    judgment = "正数越大越好:>3pp=收入爆发式增长,拐点确认; 1~3pp=良性趋势; 0~1pp=拐点初期。负值=仍在投入期,关注何时转正。从负转正是关键拐点信号。"
    category = "fundamental"
    indicator_type = "moat"
    applicable_stages = ["inflection"]
    params = {}
    output = ["rd_to_revenue_trend"]
    requires = ["rd_expense", "revenue"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        """研发费率同比变化。正值=费率在下降(收入增速>研发增速), 拐点确认"""
        if len(financials) < 8:
            return {"rd_to_revenue_trend": None}
        rd_t = sum(float(q.get("rd_expense", 0) or 0) for q in financials[:4])
        rev_t = sum(float(q.get("revenue", 0) or 0) for q in financials[:4])
        rd_t1 = sum(float(q.get("rd_expense", 0) or 0) for q in financials[4:8])
        rev_t1 = sum(float(q.get("revenue", 0) or 0) for q in financials[4:8])
        if not rev_t or not rev_t1:
            return {"rd_to_revenue_trend": None}
        intensity_t = rd_t / rev_t * 100
        intensity_t1 = rd_t1 / rev_t1 * 100
        # 正值 = 研发费率在下降 (好), 负值 = 在上升
        return {"rd_to_revenue_trend": round(intensity_t1 - intensity_t, 1)}


@register_financial
class RevenueAcceleration(FinancialIndicator):
    name = "revenue_acceleration"
    label = "营收加速度(百分点)"
    description = "本期营收同比增速减去上期同比增速。正值=营收在加速增长(需求扩张),负值=增速放缓。是判断爆发前夜的关键拐点指标。"
    judgment = ">10pp=爆发式加速,需求井喷; 3~10pp=显著加速; 0~3pp=温和加速; -3~0pp=轻微放缓(关注); <-3pp=显著减速(警惕)。连续2Q加速=强趋势确认。"
    category = "fundamental"
    indicator_type = "prosperity"
    applicable_stages = ["inflection", "growth"]
    params = {}
    output = ["revenue_acceleration"]
    requires = ["revenue"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        """营收同比增速的变化。正值=营收在加速, 爆发前夜"""
        if len(financials) < 12:
            return {"revenue_acceleration": None}
        # TTM 营收 YoY: t vs t-4
        rev = [sum(float(q.get("revenue", 0) or 0) for q in financials[i:i+4]) for i in range(0, 8, 4)]
        if not rev[1] or not rev[2]:
            return {"revenue_acceleration": None}
        yoy_current = (rev[0] / rev[1] - 1) * 100 if rev[1] else 0
        yoy_prior = (rev[1] / rev[2] - 1) * 100 if rev[2] else 0
        return {"revenue_acceleration": round(yoy_current - yoy_prior, 1)}


@register_financial
class ProfitTurnaround(FinancialIndicator):
    name = "profit_turnaround"
    label = "扭亏信号"
    description = "判断公司是否从亏损转向盈利。1=扭亏(利润由负转正), 0=一直盈利或一直亏损, -1=仍在亏损。是拐点期最重要的验证信号之一。"
    judgment = "1=关键拐点确认,利润从负转正,可开始用ROIIC评估成长质量; 0=持续盈利或持续亏损(无方向变化); -1=仍在亏损,不适合价值评估,需关注技术/产品进展。"
    category = "fundamental"
    indicator_type = "prosperity"
    applicable_stages = ["inflection"]
    params = {}
    output = ["profit_turnaround"]
    requires = ["parent_profit"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        """刚刚扭亏? 1=是, 0=否, -1=仍在亏损或一直盈利"""
        if len(financials) < 8:
            return {"profit_turnaround": 0}
        profit_t = sum(float(q.get("profit", q.get("parent_profit", 0)) or 0) for q in financials[:4])
        profit_t1 = sum(float(q.get("profit", q.get("parent_profit", 0)) or 0) for q in financials[4:8])
        if profit_t > 0 and profit_t1 < 0:
            return {"profit_turnaround": 1}
        if profit_t < 0:
            return {"profit_turnaround": -1}
        return {"profit_turnaround": 0}


@register_financial
class RevenueQoQ(FinancialIndicator):
    name = "revenue_qoq"
    label = "营收环比增速(%)"
    description = "最新季度营收相对前一季度的增速。环比增速比同比更灵敏，能更早捕捉景气度变化和季节性拐点。"
    judgment = ">30%=爆发式增长(需确认是否为季节因素); 10~30%=强劲增长; 5~10%=稳定增长; 0~5%=停滞; <0=环比下滑。连续2Q环比下滑=趋势逆转预警。"
    category = "fundamental"
    indicator_type = "prosperity"
    applicable_stages = ["inflection", "growth"]
    params = {}
    output = ["revenue_qoq"]
    requires = ["revenue"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        """最新季度相对前一季度的营收增速, 捕捉季度拐点"""
        if len(financials) < 2:
            return {"revenue_qoq": None}
        rev_q = float(financials[0].get("revenue", 0) or 0)
        rev_prev = float(financials[1].get("revenue", 0) or 0)
        if not rev_prev:
            return {"revenue_qoq": None}
        return {"revenue_qoq": round((rev_q / rev_prev - 1) * 100, 1)}
