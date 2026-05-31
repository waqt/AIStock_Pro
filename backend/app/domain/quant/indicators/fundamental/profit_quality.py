"""
成长质量/利润质量指标
适用于 Growth/Inflection 和 Mature 阶段
"""
from .base import FinancialIndicator, register_financial


@register_financial
class RDIntensity(FinancialIndicator):
    name = "rd_intensity"
    label = "研发费用率(%)"
    description = "研发费用占营收比例。衡量公司对技术/创新的投入力度，高研发投入是科技公司构建护城河的基础。"
    judgment = ">15%=高强度研发投入(多数生物科技/半导体); 8~15%=企业级软件/硬科技; 3~8%=稳健投入型; <3%=研发投入不足,需关注是否壁垒足够。结合营收增速看性价比。"
    category = "fundamental"
    indicator_type = "moat"
    applicable_stages = ["startup", "inflection"]
    params = {}
    output = ["rd_intensity"]
    requires = ["rd_expense", "revenue"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        if not financials:
            return {"rd_intensity": None}
        rd = sum(float(q.get("rd_expense", 0) or 0) for q in financials[:4])
        rev = sum(float(q.get("revenue", 0) or 0) for q in financials[:4])
        if not rev:
            return {"rd_intensity": None}
        return {"rd_intensity": round(rd / rev * 100, 1)}


@register_financial
class GrossMargin(FinancialIndicator):
    name = "gross_margin"
    label = "毛利率(%)"
    description = "毛利率 = (营收-营业成本)/营收。衡量公司定价权和议价能力的核心指标，反映护城河深度。毛利率水平取决于行业结构和竞争格局。"
    judgment = ">70%=极强定价权(品牌/技术垄断); 50~70%=强护城河(差异化优势); 30~50%=中等(行业竞争可承受); 20~30%=竞争激烈(成本驱动型); <20%=红海市场。毛利率持续下降是危险信号。"
    category = "fundamental"
    indicator_type = "moat"
    applicable_stages = ["inflection", "growth", "mature"]
    params = {}
    output = ["gross_margin"]
    requires = ["revenue", "operate_cost"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        if not financials:
            return {"gross_margin": None}
        rev = sum(float(q.get("revenue", 0) or 0) for q in financials[:4])
        cost = sum(float(q.get("operate_cost", 0) or 0) for q in financials[:4])
        if not rev:
            return {"gross_margin": None}
        return {"gross_margin": round((rev - cost) / rev * 100, 1)}


@register_financial
class GrossMarginTrend(FinancialIndicator):
    name = "gross_margin_trend"
    label = "毛利率趋势"
    description = "判断毛利率连续4Q的变化方向: rising(上升)、stable(稳定)、declining(下降)。趋势比绝对值更能揭示护城河变化。"
    judgment = "rising=定价权增强/成本降低，护城河在加固; stable=格局稳定，竞争均衡; declining=定价权削弱/成本上升，护城河在侵蚀。连续3Q下降是预警信号。"
    category = "fundamental"
    indicator_type = "moat"
    applicable_stages = ["inflection", "growth", "mature"]
    params = {}
    output = ["gross_margin_trend"]
    requires = ["revenue", "operate_cost"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        """判断毛利率连续趋势: rising/stable/declining"""
        if len(financials) < 4:
            return {"gross_margin_trend": None}
        gms = []
        for q in financials[:4]:
            rev = float(q.get("revenue", 0) or 0)
            cost = float(q.get("operate_cost", 0) or 0)
            gms.append((rev - cost) / rev * 100 if rev else 0)
        if len(gms) >= 3 and gms[0] > gms[1] > gms[2]:
            return {"gross_margin_trend": "rising"}
        if len(gms) >= 3 and gms[0] < gms[1] < gms[2]:
            return {"gross_margin_trend": "declining"}
        return {"gross_margin_trend": "stable"}


@register_financial
class OperatingLeverage(FinancialIndicator):
    name = "operating_leverage"
    label = "经营杠杆"
    description = "经营杠杆 = 利润增速/营收增速。衡量利润对营收变化的敏感度。高经营杠杆：营收小幅增长就能带来利润大幅增长，但反之亦然。"
    judgment = ">2.0=高经营杠杆(固定成本高,增收效应显著); 1.5~2.0=中等; 1.0~1.5=低杠杆; <1.0或负=利润增速落后营收,成本失控。高杠杆公司需关注景气度变化。"
    category = "fundamental"
    indicator_type = "prosperity"
    applicable_stages = ["growth"]
    params = {}
    output = ["operating_leverage"]
    requires = ["revenue", "parent_profit"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        """经营杠杆 = (Δprofit/profit) / (Δrevenue/revenue)"""
        if len(financials) < 8:
            return {"operating_leverage": None}
        rev_t = sum(float(q.get("revenue", 0) or 0) for q in financials[:4])
        rev_t1 = sum(float(q.get("revenue", 0) or 0) for q in financials[4:8])
        profit_t = sum(float(q.get("profit", q.get("parent_profit", 0)) or 0) for q in financials[:4])
        profit_t1 = sum(float(q.get("profit", q.get("parent_profit", 0)) or 0) for q in financials[4:8])
        
        # 优化: 剔除微利或极小营收基数导致的指标失真 (阈值设定为 1000 万)
        if not rev_t1 or not profit_t1 or abs(profit_t1) < 1e7 or abs(rev_t1) < 1e7:
            return {"operating_leverage": None}
            
        rev_growth = (rev_t - rev_t1) / abs(rev_t1)
        profit_growth = (profit_t - profit_t1) / abs(profit_t1)
        
        # 营收几乎不增长时，杠杆乘数失去意义
        if abs(rev_growth) < 0.001:
            return {"operating_leverage": None}
            
        return {"operating_leverage": round(profit_growth / rev_growth, 2)}


@register_financial
class FCFConversion(FinancialIndicator):
    name = "fcf_conversion"
    label = "现金流转化率"
    description = "经营性现金流/净利润。衡量利润是否真实转化为现金。是识别纸面利润和应收账款式伪增长的关键指标。"
    judgment = ">1.0=利润是真金白银，盈利质量优秀; 0.7~1.0=合理，有正常营运资金占用; 0.5~0.7=偏低，应收/存货占用现金; <0.5=利润质量差，需警惕。持续<0.5可能是财务操纵信号。"
    category = "fundamental"
    indicator_type = "moat"
    applicable_stages = ["growth", "mature"]
    params = {}
    output = ["fcf_conversion"]
    requires = ["op_cashflow", "parent_profit"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        """经营性现金流/净利润。>1 = 利润是真金白银"""
        if not financials:
            return {"fcf_conversion": None}
        ocf = sum(float(q.get("op_cashflow", 0) or 0) for q in financials[:4])
        profit = sum(float(q.get("profit", q.get("parent_profit", 0)) or 0) for q in financials[:4])
        if not profit or profit <= 0:
            return {"fcf_conversion": None}
        return {"fcf_conversion": round(ocf / profit, 2)}
