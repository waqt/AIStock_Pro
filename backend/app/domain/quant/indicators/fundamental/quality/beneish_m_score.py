"""Beneish M-Score — 财务造假概率评估"""
from ..base import FinancialIndicator, register, _safe_div


@register
class BeneishMScoreIndicator(FinancialIndicator):
    name = "beneish_m_score"
    label = "Beneish M-Score"
    description = "M-Score = -4.84 + 0.92*DSRI + 0.528*GMI + 0.404*AQI + 0.892*SGI + 0.115*DEPI - 0.172*SGAI + 4.679*TATA - 0.327*LVGI。8因子财务造假检测模型。"
    judgment = "<-2.22=造假概率低(安全); -2.22~-1.78=灰色区域(需关注); >-1.78=造假概率较高(危险)。M-Score不是确证,但可做排雷初筛。阈值来自Beneish(1999)原文。"
    category = "quality"
    indicator_type = "both"
    applicable_stages = ["growth", "mature"]
    params = {}
    output = ["m_score", "m_score_interpretation", "m_score_components"]
    text_output = ["m_score_interpretation", "m_score_components"]
    requires = ["revenue", "operate_cost", "profit", "total_assets", "current_assets",
                "fixed_assets", "total_liabilities", "sale_expense", "manage_expense"]

    @classmethod
    def compute(cls, quarters: list) -> dict:
        if len(quarters) < 8:
            return {"m_score": None, "m_score_interpretation": "insufficient_data"}
        t = quarters[0]
        t1 = quarters[1]; t2 = quarters[2]; t3 = quarters[3]
        t4 = quarters[4]; t5 = quarters[5]; t6 = quarters[6]; t7 = quarters[7]
        def _f(q, k): return float(q.get(k, 0) or 0)
        try:
            rev_t = sum(_f(q, "revenue") for q in quarters[:4])
            rev_t4 = sum(_f(q, "revenue") for q in quarters[4:8])
            rec_t = _f(t, "accounts_receivable") or _f(t, "accounts_receivable_net") or 0
            rec_t4 = _f(t4, "accounts_receivable") or _f(t4, "accounts_receivable_net") or 0
            cogs_t = sum(_f(q, "operate_cost") for q in quarters[:4])
            cogs_t4 = sum(_f(q, "operate_cost") for q in quarters[4:8])
            TA_t = _f(t, "total_assets"); TA_t4 = _f(t4, "total_assets")
            CA_t = _f(t, "current_assets"); CA_t4 = _f(t4, "current_assets")
            FA_t = _f(t, "fixed_assets") or 0
            FA_t4 = _f(t4, "fixed_assets") or 0
            TL_t = _f(t, "total_liabilities"); TL_t4 = _f(t4, "total_liabilities")
            SGA_t = sum(_f(q, "sale_expense") + _f(q, "manage_expense") for q in quarters[:4])
            SGA_t4 = sum(_f(q, "sale_expense") + _f(q, "manage_expense") for q in quarters[4:8])
        except Exception:
            return {"m_score": None, "m_score_interpretation": "calc_error"}
        DSRI = _safe_div(rec_t / rev_t, rec_t4 / rev_t4) if rev_t and rev_t4 else 1
        # GMI = GrossMargin_t-1 / GrossMargin_t, 其中 GM = (Rev-COGS)/Rev = 1-COGS/Rev
        # >1 = 毛利率恶化(更高造假概率), <1 = 毛利率改善
        gm_current = (1 - cogs_t / rev_t) if rev_t else 0
        gm_prior = (1 - cogs_t4 / rev_t4) if rev_t4 else 0
        if gm_current <= 0:
            GMI = 2.0  # 当期毛利率归零或负 → 极高造假动机
        else:
            GMI = _safe_div(gm_prior, gm_current)
        AQI = _safe_div(1 - (CA_t + FA_t) / TA_t, 1 - (CA_t4 + FA_t4) / TA_t4) if TA_t and TA_t4 else 1
        SGI = _safe_div(rev_t, rev_t4) if rev_t4 else 1
        DPR_t = _safe_div(FA_t, FA_t + cogs_t) if (FA_t + cogs_t) else 1
        DPR_t4 = _safe_div(FA_t4, FA_t4 + cogs_t4) if (FA_t4 + cogs_t4) else 1
        DEPI = _safe_div(DPR_t4, DPR_t) if DPR_t else 1
        SGAI = _safe_div(SGA_t / rev_t, SGA_t4 / rev_t4) if rev_t and rev_t4 else 1
        profit_t = sum(_f(q, "profit") or _f(q, "parent_profit") or 0 for q in quarters[:4])
        ocf_t = sum(_f(q, "op_cashflow") for q in quarters[:4])
        TATA = _safe_div(profit_t - ocf_t, TA_t) if TA_t else 0
        LVGI = _safe_div(TL_t / TA_t, TL_t4 / TA_t4) if TA_t and TA_t4 else 1
        m_score = -4.84 + 0.92 * DSRI + 0.528 * GMI + 0.404 * AQI + 0.892 * SGI + 0.115 * DEPI - 0.172 * SGAI + 4.679 * TATA - 0.327 * LVGI
        # Beneish(1999) 标准阈值: < -2.22 → low_risk; -2.22 ~ -1.78 → grey; > -1.78 → high_risk
        if m_score > -1.78:
            interpretation = "high_risk"
        elif m_score > -2.22:
            interpretation = "grey_area"
        else:
            interpretation = "low_risk"
        return {
            "m_score": round(m_score, 2),
            "m_score_interpretation": interpretation,
            "m_score_components": {
                "DSRI": round(DSRI, 4), "GMI": round(GMI, 4), "AQI": round(AQI, 4),
                "SGI": round(SGI, 4), "DEPI": round(DEPI, 4),
                "SGAI": round(SGAI, 4), "TATA": round(TATA, 4), "LVGI": round(LVGI, 4),
            },
        }
