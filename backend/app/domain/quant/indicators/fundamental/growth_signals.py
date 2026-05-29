"""
先行指标 — 适用于 Pre-revenue/Early 阶段公司
利润为负或刚转正时 ROIIC 不可用, 用这些指标捕捉早期信号
"""
from .base import FinancialIndicator, register_financial


@register_financial
class ContractLiabilityYoY(FinancialIndicator):
    name = "contract_liability_yoy"
    label = "合同负债同比增速(%)"
    category = "fundamental"
    indicator_type = "prosperity"
    applicable_stages = ["startup", "inflection", "growth"]
    params = {}
    output = ["contract_liability_yoy"]
    requires = ["contract_liability"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        if len(financials) < 8:
            return {"contract_liability_yoy": None}
        recent = sum(float(q.get("contract_liability", 0) or 0) for q in financials[:4])
        prior = sum(float(q.get("contract_liability", 0) or 0) for q in financials[4:8])
        if not prior:
            return {"contract_liability_yoy": None}
        return {"contract_liability_yoy": round((recent / prior - 1) * 100, 1)}


@register_financial
class InventoryYoY(FinancialIndicator):
    name = "inventory_yoy"
    label = "存货同比增速(%)"
    category = "fundamental"
    indicator_type = "prosperity"
    applicable_stages = ["inflection", "growth"]
    params = {}
    output = ["inventory_yoy"]
    requires = ["inventory"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        if len(financials) < 8:
            return {"inventory_yoy": None}
        recent = float(financials[0].get("inventory", 0) or 0)
        prior = float(financials[4].get("inventory", 0) or 0)
        if not prior:
            return {"inventory_yoy": None}
        return {"inventory_yoy": round((recent / prior - 1) * 100, 1)}


@register_financial
class RevenueYoY(FinancialIndicator):
    name = "revenue_yoy"
    label = "营收同比增速(%)"
    category = "fundamental"
    indicator_type = "prosperity"
    applicable_stages = ["startup", "inflection", "growth", "mature", "decline"]
    params = {}
    output = ["revenue_yoy"]
    requires = ["revenue"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        if len(financials) < 8:
            return {"revenue_yoy": None}
        recent = sum(float(q.get("revenue", 0) or 0) for q in financials[:4])
        prior = sum(float(q.get("revenue", 0) or 0) for q in financials[4:8])
        if not prior:
            return {"revenue_yoy": None}
        return {"revenue_yoy": round((recent / prior - 1) * 100, 1)}


@register_financial
class RDGrowth(FinancialIndicator):
    name = "rd_growth"
    label = "研发费用同比增速(%)"
    category = "fundamental"
    indicator_type = "moat"
    applicable_stages = ["startup", "inflection"]
    params = {}
    output = ["rd_growth"]
    requires = ["rd_expense"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        if len(financials) < 8:
            return {"rd_growth": None}
        recent = sum(float(q.get("rd_expense", 0) or 0) for q in financials[:4])
        prior = sum(float(q.get("rd_expense", 0) or 0) for q in financials[4:8])
        if not prior:
            return {"rd_growth": None}
        return {"rd_growth": round((recent / prior - 1) * 100, 1)}
