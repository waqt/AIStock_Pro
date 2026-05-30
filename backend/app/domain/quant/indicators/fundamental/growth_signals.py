"""
先行指标 — 适用于 Pre-revenue/Early 阶段公司
利润为负或刚转正时 ROIIC 不可用, 用这些指标捕捉早期信号
"""
from .base import FinancialIndicator, register_financial


@register_financial
class ContractLiabilityYoY(FinancialIndicator):
    name = "contract_liability_yoy"
    label = "合同负债同比增速(%)"
    description = "合同负债=客户已付款但公司尚未交付的合同金额。同比增速反映未来收入的确定性，是领先于营收的先行指标。"
    judgment = "正增长且加速=未来收入保障强,订单饱满; 增速>30%=爆发前夜; 增速在0~20%=稳健; 负增长=新订单不足,远期营收承压。结合营收增速看:合同负债增>营收增=更乐观。"
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
    description = "存货余额的同比增速。存货大幅增加可能是产销两旺(积极信号)，也可能是产品滞销(危险信号)。需结合营收增速判断。"
    judgment = "存货增速<营收增速=产品供不应求,渠道健康; 存货增速>营收增速=有积压风险; 存货增速>30%且营收停滞=严重滞销预警; 负增长(去库存)=短期承压但改善中。"
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
    description = "TTM营收较上年同期的增长幅度。是衡量公司成长性的最基础指标，反映产品或服务的市场需求变化。"
    judgment = ">50%=超高速增长(早期爆发期); 20~50%=高速增长; 10~20%=稳健增长; 0~10%=低增长; <0=衰退。高增速需确认可持续性,且关注利润是否同步。"
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
    description = "研发费用投入的同比增速。反映公司是否在持续加大技术投入。增速持续高于营收增速说明公司在以研发换未来。"
    judgment = ">30%=研发投入大幅扩张,积极构建壁垒; 10~30%=稳定投入; 0~10%=投入不足; <0=削减研发,可能是短期业绩压力。持续研发投入增速>营收增速=好信号(长期主义)。"
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
