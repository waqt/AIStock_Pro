"""
早期阶段指标 — 适用于初创/研发期公司
核心问题: "它是在烧钱等死, 还是在烧钱建护城河?"
"""
from .base import FinancialIndicator, register_financial


@register_financial
class BurnRateMonths(FinancialIndicator):
    name = "burn_rate_months"
    label = "现金跑道(月)"
    description = "现金余额 / 每月净烧钱额。衡量初创公司在耗尽现金前还能运营多久。经营现金流为正的公司此值无意义(显示None)。"
    judgment = ">24月=现金充裕,无需短期融资; 12~24月=安全,但需关注融资节奏; 6~12月=需要尽快融资; <6月=危险,有流动性危机。若OCF已转正则无烧钱风险。"
    category = "fundamental"
    indicator_type = "prosperity"
    applicable_stages = ["startup"]
    params = {}
    output = ["burn_rate_months"]
    requires = ["cash", "op_cashflow"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        """现金能撑几个月? cash / monthly_burn。burn = |季度经营CF(若为负)| / 3"""
        if not financials:
            return {"burn_rate_months": None}
        cash = float(financials[0].get("cash", 0) or 0)
        ocf_4q = sum(float(q.get("op_cashflow", 0) or 0) for q in financials[:4])
        if ocf_4q >= 0:
            return {"burn_rate_months": None}  # 经营现金流为正, 无burn
        monthly_burn = abs(ocf_4q) / 3  # 季度→月度
        if not monthly_burn:
            return {"burn_rate_months": None}
        return {"burn_rate_months": round(cash / monthly_burn, 1)}


@register_financial
class RDToOpex(FinancialIndicator):
    name = "rd_to_opex"
    label = "研发占运营支出比"
    description = "研发费用 / (研发+销售+管理费用)。衡量公司的运营支出结构——偏技术驱动(硬件投入)还是偏销售驱动(市场投入)。"
    judgment = ">70%=极偏技术驱动,科学家文化; 50~70%=技术主导; 30~50%=平衡型; 15~30%=偏销售驱动; <15%=纯销售驱动。越高并不一定越好,需结合商业模式判断。"
    category = "fundamental"
    indicator_type = "moat"
    applicable_stages = ["startup", "inflection"]
    params = {}
    output = ["rd_to_opex"]
    requires = ["rd_expense", "sale_expense", "manage_expense"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        """rd_expense / (rd + sale + manage)。越高=越偏技术驱动, 越低=越偏销售驱动"""
        if not financials:
            return {"rd_to_opex": None}
        rd = sum(float(q.get("rd_expense", 0) or 0) for q in financials[:4])
        sga = sum(float(q.get("sale_expense", 0) or 0) + float(q.get("manage_expense", 0) or 0) for q in financials[:4])
        total = rd + sga
        if not total:
            return {"rd_to_opex": None}
        return {"rd_to_opex": round(rd / total * 100, 1)}
