"""行业溢价分析 — 当前 PE vs 行业中位数 PE 对比

衡量个股相对于行业整体的估值溢价/折价。
行业 PE 中位数通过 StockValuation 跨股票查询获取。
"""
from app.domain.quant.valuation.base import ValuationMethod, register_valuation


@register_valuation
class IndustryPremiumMethod(ValuationMethod):
    name = "industry_premium"
    label = "行业溢价分析"
    category = "advanced"
    description = "个股 PE(TTM) 与所属行业中位数 PE 的对比。正溢价 = 比行业贵, 负溢价 = 比行业便宜"
    output = ["industry_pe_median", "premium_pct", "industry_verdict"]
    requires = ["pe_ttm", "industry"]
    text_output = ["industry_verdict"]
    requires_financial_data = True
    judgment = "premium_pct>50%→个股显著高于行业中位数(可能高估或包含成长溢价); premium_pct<-30%→低于行业中位数(可能低估或基本面弱于同行)"
    applicable_scenarios = "适用于同行可比公司多的行业(银行/制造/消费); PE为负的行业自动显示N/A"
    limitations = "行业内公司差异大时中位数缺乏代表性; 未对规模/增速/杠杆率做标准化调整; 行业分类粒度影响结果"

    @classmethod
    def compute(cls, pe_ttm: float = None, industry: str = None, **kwargs) -> dict:
        if pe_ttm is None or not industry:
            return {k: None for k in cls.output}

        # 行业 PE 中位数通过外部注入 (由 ValuationRunner 查询后传入)
        # 这里作为纯函数, 期待 runner 传入 industry_pe_median
        median = kwargs.get("industry_pe_median")
        if median is None or median <= 0:
            return {"industry_pe_median": None, "premium_pct": None,
                    "industry_verdict": "缺少行业对比数据"}

        premium = (pe_ttm - median) / median * 100
        if premium > 30:
            verdict = "显著溢价"
        elif premium > 10:
            verdict = "小幅溢价"
        elif premium < -30:
            verdict = "显著折价"
        elif premium < -10:
            verdict = "小幅折价"
        else:
            verdict = "与行业持平"

        return {
            "industry_pe_median": round(median, 2),
            "premium_pct": round(premium, 1),
            "industry_verdict": verdict,
        }
