"""风险调整净现值 (Risk-Adjusted NPV / rNPV)

核心逻辑:
  按临床阶段成功概率 (Probability of Success, PoS) 对预期现金流加权。
  无具体管线数据时, 用研发费用率推定"隐含管线"价值。
  生物医药/创新药企核心估值方法。

  行业 PoS (2024 BIO/PhRMA):
    Phase 1 → Approval: 肿瘤 4.7%, 罕见病 16.3%, 全行业平均 7.9%
    Phase 2 → Approval: 肿瘤 8.3%, 罕见病 21.2%, 全行业平均 14.5%
    Phase 3 → Approval: 肿瘤 30.0%, 罕见病 47.5%, 全行业平均 45.0%
    ND       → Approval:          85.0%

适用: 尚未盈利或处于研发密集投入阶段的生物医药/创新药公司
"""
import math
from app.domain.quant.valuation.base import ValuationMethod, register_valuation


# 行业成功概率 (按研发强度推定公司类型)
POS_TABLE = {
    "innovative": {  # 创新药企 (rd_intensity > 20%)
        "label": "创新药企",
        "blended_pos": 0.065,   # 加权组合 PoS ~6.5%
        "pipeline_mult": 12.0,  # 隐含管线乘数
        "years_to_peak": 6.0,   # 到峰值年数
    },
    "moderate": {    # 中等创新 (rd_intensity 10-20%)
        "label": "创新型仿制药企",
        "blended_pos": 0.10,
        "pipeline_mult": 8.0,
        "years_to_peak": 5.0,
    },
    "hybrid": {      # 仿制药为主 (rd_intensity 5-10%)
        "label": "仿制药企",
        "blended_pos": 0.15,
        "pipeline_mult": 5.0,
        "years_to_peak": 4.0,
    },
}

# 研发费用占营收比例 → 公司类型映射
POS_THRESHOLDS = [
    (0.20, "innovative"),
    (0.10, "moderate"),
    (0.05, "hybrid"),
]


@register_valuation
class RiskAdjustedNPVMethod(ValuationMethod):
    name = "risk_adjusted_npv"
    label = "rNPV 风险调整净现值"
    category = "dynamic"
    description = "按临床阶段成功概率(PoS)加权现金流的生物医药估值, 用研发费用推定隐含管线价值"
    output = [
        "rnpv_risk_adjusted_value", "rnpv_upside_pct",
        "rnpv_company_type", "rnpv_implied_pos",
        "rnpv_peak_sales_est", "rnpv_rd_intensity",
        "rnpv_verdict",
    ]
    text_output = ["rnpv_company_type", "rnpv_verdict"]
    requires = ["mcap_yi", "total_shares"]
    requires_financial_data = True
    requires_financial_indicators = True

    judgment = (
        "rnpv_upside_pct>0%→当前市值低于风险调整后管线价值。"
        "rnpv_rd_intensity>20%→真正创新药企, 适用高PoS标准。"
        "rnpv_company_type 显示公司分类。"
        "rNPV不适用于rd_intensity<5%的传统药企"
    )
    applicable_scenarios = (
        "尚未盈利或处于研发密集投入阶段的生物医药/创新药公司; "
        "科创板和港股的Biotech公司; "
        "管线产品以创新药为主的制药企业"
    )
    limitations = (
        "无具体管线数据, 用研发费用推定管线规模存在估算误差; "
        "行业平均PoS不反映单个管线的实际临床数据质量; "
        "未考虑专利悬崖/集采降价/管线失败后的沉没成本; "
        "不适用于中药/传统仿制药/流通企业"
    )

    _field_labels = {
        "rnpv_risk_adjusted_value": "rNPV 每股价值(¥)",
        "rnpv_upside_pct": "rNPV 上行空间(%)",
        "rnpv_company_type": "研发公司类型",
        "rnpv_implied_pos": "隐含成功概率(%)",
        "rnpv_peak_sales_est": "预估峰值营收(亿元)",
        "rnpv_rd_intensity": "研发费用率(%)",
        "rnpv_verdict": "rNPV 判断结论",
    }

    @classmethod
    def is_applicable(cls, **kwargs) -> bool:
        """仅适用于研发费用率>=5%的生物医药/创新药公司"""
        revenue_ttm = kwargs.get("revenue_ttm")
        rd_expense_ttm = kwargs.get("rd_expense_ttm")
        if not revenue_ttm or not rd_expense_ttm:
            return False
        rd_intensity = float(rd_expense_ttm) / float(revenue_ttm) if float(revenue_ttm) > 0 else 0
        return rd_intensity >= 0.05

    @classmethod
    def _get_company_type(cls, rd_intensity: float) -> tuple:
        """根据研发费用率判断公司类型

        Returns:
            (type_key, type_label, blended_pos, pipeline_mult, years_to_peak)
        """
        for threshold, type_key in POS_THRESHOLDS:
            if rd_intensity >= threshold:
                info = POS_TABLE[type_key]
                return (type_key, info["label"], info["blended_pos"],
                        info["pipeline_mult"], info["years_to_peak"])
        return ("traditional", "传统药企", None, 0, 0)

    @classmethod
    def compute(cls, **kwargs) -> dict:
        revenue_ttm = kwargs.get("revenue_ttm")  # 万元 (from FinancialStatement)
        rd_expense_ttm = kwargs.get("rd_expense_ttm")  # 万元 (from FinancialStatement)
        mcap_yi = kwargs.get("mcap_yi")  # 亿元
        total_shares = kwargs.get("total_shares")

        # 数据不足时返回 None
        if not revenue_ttm or not mcap_yi or not total_shares:
            return {k: None for k in cls.output}

        revenue_ttm = float(revenue_ttm)
        revenue_ttm_yi = revenue_ttm / 1e8  # 转亿元

        # 研发费用率 (确定公司类型)
        rd_expense_val = float(rd_expense_ttm or 0)
        rd_intensity = rd_expense_val / revenue_ttm if revenue_ttm > 0 else 0.0

        type_key, type_label, blended_pos, pipeline_mult, years_to_peak = \
            cls._get_company_type(rd_intensity)

        # 传统药企不适用 rNPV
        if type_key == "traditional":
            return {
                "rnpv_risk_adjusted_value": None,
                "rnpv_upside_pct": None,
                "rnpv_company_type": f"传统药企(rd_intensity={rd_intensity*100:.1f}%), rNPV不适用",
                "rnpv_implied_pos": None,
                "rnpv_peak_sales_est": None,
                "rnpv_rd_intensity": round(rd_intensity * 100, 1),
                "rnpv_verdict": "研发费用率<5%, rNPV估值不适用",
            }

        # 参数
        wacc = float(kwargs.get("wacc", 12.0))  # 创新药企 WACC 更高
        tax_rate = 0.15  # 高新技术企业 15%

        # 隐含管线价值 = R&D × pipeline_mult
        rd_yi = rd_expense_val / 1e8
        peak_sales_yi = rd_yi * pipeline_mult

        # 运营利润率 (用于推算运营成本)
        op_margin_pct = kwargs.get("operating_margin_pct") or 10.0
        op_margin = op_margin_pct / 100.0 if op_margin_pct else 0.10

        # rNPV 计算:
        # 研发投入阶段 (3年): 每年投 rd_yi, 失败概率 = 1-PoS
        # 商业化阶段 (后 years_to_peak 年达到峰值):
        #   营收 = peak_sales × success_flag(贝努利), 运营成本递减

        # 简化: 用一次性预期值
        # rNPV = [peak_sales × PoS / (WACC - g)] - PV(累计研发成本)
        terminal_growth = 2.0  # 长期成熟增速

        # 风险调整后峰值营收
        risk_adj_peak = peak_sales_yi * blended_pos

        # 商业化前投入年份的 R&D 成本折现
        dev_years = int(max(3, years_to_peak - 1))
        dev_cost_pv = 0.0
        for yr in range(1, dev_years + 1):
            dev_cost_pv += rd_yi / ((1 + wacc / 100.0) ** yr)

        # 终端价值 (风险调整后)
        if wacc > terminal_growth:
            terminal_after_tax = risk_adj_peak * op_margin * (1 - tax_rate)
            tv = terminal_after_tax / ((wacc - terminal_growth) / 100.0)
            pv_tv = tv / ((1 + wacc / 100.0) ** years_to_peak)
        else:
            pv_tv = 0.0

        fair_value_yi = pv_tv - dev_cost_pv
        fair_value_yi = max(fair_value_yi, 0.0)  # 下限 0

        # 每股价值
        per_share_value = (fair_value_yi * 1e8) / total_shares if total_shares > 0 else 0
        current_price = (mcap_yi * 1e8) / total_shares if total_shares > 0 else 0

        upside = ((per_share_value / current_price) - 1) * 100 if current_price > 0 else 0

        # 结论
        if rd_intensity > 0.20 and upside > 0:
            verdict = f"高研发投入({rd_intensity*100:.0f}%)创新药企, rNPV显示仍有上行空间"
        elif upside > 30:
            verdict = "管线价值显著低估, 市场未充分定价研发管线"
        elif upside > 0:
            verdict = "管线估值合理偏低, 关注催化剂事件"
        elif upside > -30:
            verdict = "估值合理, 管线价值已基本反映"
        else:
            verdict = "估值偏高, 当前价格已透支管线预期"

        return {
            "rnpv_risk_adjusted_value": round(per_share_value, 2),
            "rnpv_upside_pct": round(upside, 1),
            "rnpv_company_type": f"{type_label}(rd_intensity={rd_intensity*100:.1f}%)",
            "rnpv_implied_pos": round(blended_pos * 100, 1) if blended_pos else None,
            "rnpv_peak_sales_est": round(peak_sales_yi, 2),
            "rnpv_rd_intensity": round(rd_intensity * 100, 1),
            "rnpv_verdict": verdict,
        }
