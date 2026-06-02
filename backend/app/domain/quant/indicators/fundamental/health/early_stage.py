"""早期阶段 — 烧钱率/研发占运营费用比"""
from ..base import FinancialIndicator, register, _safe_div


@register
class BurnRateMonths(FinancialIndicator):
    name = "burn_rate_months"
    label = "现金消耗月数"
    description = "现金余额/(平均每月经营现金流消耗)。衡量早期公司在不融资情况下的生存时间。"
    judgment = ">24个月=现金充裕; 12~24个月=安全; 6~12个月=需关注; <6个月=资金紧张,需尽快融资。"
    category = "health"
    indicator_type = "moat"
    applicable_stages = ["startup", "inflection"]
    params = {}
    output = ["burn_rate_months"]
    requires = ["cash", "op_cashflow"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        if not financials:
            return {"burn_rate_months": None}
        cash = float(financials[0].get("cash", 0) or 0)
        ocf = sum(float(q.get("op_cashflow", 0) or 0) for q in financials[:4])
        monthly_burn_avg = abs(ocf) / 4 if ocf < 0 else 0

        # 最近单季的烧钱率 (更敏感)
        latest_q_ocf = float(financials[0].get("op_cashflow", 0) or 0)
        monthly_burn_latest = abs(latest_q_ocf) / 3 if latest_q_ocf < 0 else 0

        # 取两者中的较保守值 (TTM 均值可能低估近期加速烧钱)
        if monthly_burn_avg <= 0 and monthly_burn_latest <= 0:
            return {"burn_rate_months": None}
        monthly_burn = max(monthly_burn_avg, monthly_burn_latest)

        return {"burn_rate_months": round(cash / monthly_burn, 1)}


@register
class RDToOpex(FinancialIndicator):
    name = "rd_to_opex"
    label = "研发/运营费用比"
    description = "研发费用/(销售费用+管理费用)。衡量公司在创新vs销售之间的资源分配倾向。"
    judgment = ">1.0=技术驱动,重研发轻销售; 0.5~1.0=均衡; <0.5=重销售轻研发。科技公司该比率应>0.5。"
    category = "profitability"
    indicator_type = "moat"
    applicable_stages = ["startup", "inflection", "growth"]
    params = {}
    output = ["rd_to_opex"]
    requires = ["rd_expense", "sale_expense", "manage_expense"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        if not financials:
            return {"rd_to_opex": None}
        rd = sum(float(q.get("rd_expense", 0) or 0) for q in financials[:4])
        sga = sum(float(q.get("sale_expense", 0) or 0) + float(q.get("manage_expense", 0) or 0) for q in financials[:4])
        if not sga:
            return {"rd_to_opex": None}
        return {"rd_to_opex": round(rd / sga, 2)}
