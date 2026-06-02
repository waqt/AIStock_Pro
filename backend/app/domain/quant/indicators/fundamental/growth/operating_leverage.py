"""经营杠杆 — EBIT增速/营收增速 (DOL)"""
from ..base import FinancialIndicator, register, _safe_div


@register
class OperatingLeverage(FinancialIndicator):
    name = "operating_leverage"
    label = "经营杠杆(DOL)"
    description = "经营杠杆 = %ΔEBIT / %Δ营收。衡量营业利润对营收变化的敏感度, 反映固定成本占比。"
    judgment = ">2.0=高经营杠杆(固定成本高); 1.5~2.0=中等; 1.0~1.5=低; <1.0或负=利润增速落后营收。"
    category = "growth"
    indicator_type = "prosperity"
    applicable_stages = ["growth"]
    params = {}
    output = ["operating_leverage"]
    requires = ["revenue", "operate_cost", "sale_expense", "manage_expense"]

    @classmethod
    def _calc_ebit_ttm(cls, financials: list) -> float:
        """计算 TTM 营业利润 (EBIT ≈ rev - cost - sga)"""
        total = 0.0
        for q in financials[:4]:
            rev = float(q.get("revenue", 0) or 0)
            cost = float(q.get("operate_cost", 0) or 0)
            sga = (float(q.get("sale_expense", 0) or 0) +
                   float(q.get("manage_expense", 0) or 0))
            total += rev - cost - sga
        return total

    @classmethod
    def compute(cls, financials: list) -> dict:
        if len(financials) < 8:
            return {"operating_leverage": None}
        rev_t = sum(float(q.get("revenue", 0) or 0) for q in financials[:4])
        rev_t1 = sum(float(q.get("revenue", 0) or 0) for q in financials[4:8])
        ebit_t = cls._calc_ebit_ttm(financials[:4])
        ebit_t1 = cls._calc_ebit_ttm(financials[4:8])

        if not rev_t1 or not rev_t:
            return {"operating_leverage": None}

        rev_growth = (rev_t - rev_t1) / abs(rev_t1)
        ebit_growth = _safe_div(ebit_t - ebit_t1, abs(ebit_t1))

        if ebit_growth is None or abs(rev_growth) < 0.001:
            return {"operating_leverage": None}

        return {"operating_leverage": round(ebit_growth / rev_growth, 2)}
