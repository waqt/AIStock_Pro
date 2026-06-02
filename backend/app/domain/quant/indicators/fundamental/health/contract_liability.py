"""合同负债 — 在手订单先行指标"""
from ..base import FinancialIndicator, register, _pct


@register
class ContractLiability(FinancialIndicator):
    name = "contract_liability"
    label = "合同负债"
    description = "合同负债(预收账款)余额+同比增速。客户预先支付的款项,是未来收入的先行指标。"
    judgment = "正增长=合同负债同比增加(新订单增长); 负增长=同比减少。合同负债增速>营收增速=新订单增速高于营收确认速度。"
    category = "health"
    indicator_type = "prosperity"
    applicable_stages = ["inflection", "growth"]
    params = {}
    output = ["contract_liability_yoy", "contract_liability_yi"]
    requires = ["contract_liability"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        if not financials or len(financials) < 5:
            return {"contract_liability_yoy": None, "contract_liability_yi": None}
        cl = float(financials[0].get("contract_liability", 0) or 0)
        cl_4q = float(financials[4].get("contract_liability", 0) or 0)
        return {
            "contract_liability_yoy": _pct(cl, cl_4q),
            "contract_liability_yi": round(cl / 1e8, 2),
        }
