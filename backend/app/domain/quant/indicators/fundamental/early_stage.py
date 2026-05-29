"""
早期阶段指标 — 适用于初创/研发期公司
核心问题: "它是在烧钱等死, 还是在烧钱建护城河?"
"""
from .base import FinancialIndicator, register_financial


@register_financial
class BurnRateMonths(FinancialIndicator):
    name = "burn_rate_months"
    label = "现金跑道(月)"
    category = "fundamental"
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
    category = "fundamental"
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
