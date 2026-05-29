"""
研发资本化调整 — 还原科技公司被会计准则压低的真实盈利能力

问题: GAAP将研发支出全额计入当期费用, 导致高研发投入的科技公司
      账面利润被大幅压低, ROE/ROIC被低估。
调整: 将研发支出视为无形资产, 按摊销年限资本化处理。

公式:
  RD_Asset = sum( RD_i * unamortized_pct_i )
  Adjusted_Profit = Reported_Profit + Current_RD - Amortization
  Adjusted_Assets = Reported_Assets + RD_Asset
"""
from typing import List, Dict


def adjust_rd_capitalization(financials: List[Dict], amort_years: int = 5) -> dict:
    """
    输入: 最近 8Q 财务数据 (含 rd_expense 字段), 摊销年限默认5年
    输出: {adjusted_profit, adjusted_roe, rd_asset, rd_amortization, profit_impact_pct, note}
    """
    rd_expenses = [float(q.get("rd_expense", 0) or 0) for q in financials]
    total_rd = sum(rd_expenses)

    if total_rd == 0:
        return _no_rd_result(financials)

    # 计算研发资产净值 (按摊销年限折余)
    rd_asset = 0.0
    quarters_per_year = 4
    annual_amort_rate = 1.0 / amort_years

    for i, rd in enumerate(rd_expenses):
        age_quarters = i  # 第 i 个季度前发生 (i=0 是最新季度)
        age_years = age_quarters / quarters_per_year
        if age_years >= amort_years:
            continue  # 已摊完
        remaining_pct = 1.0 - (age_years / amort_years)
        rd_asset += rd * remaining_pct

    # 当期摊销 = 研发资产 / 剩余平均年限
    rd_amortization = rd_asset / max(amort_years * 0.5, 1.0)

    # 报告利润 (最近4Q)
    reported_profit = sum(float(q.get("parent_profit", q.get("profit", 0)) or 0) for q in financials[:4])
    current_rd = sum(rd_expenses[:4])

    adjusted_profit = reported_profit + current_rd - rd_amortization

    # 调整后总资产
    reported_assets = float(financials[0].get("total_assets", 0) or 0)
    adjusted_assets = reported_assets + rd_asset

    profit_impact = ((adjusted_profit / reported_profit - 1) * 100) if reported_profit and reported_profit > 0 else 0

    adjusted_roe = (adjusted_profit / adjusted_assets * 100) if adjusted_assets else None

    return {
        "reported_profit_yi": round(reported_profit / 1e8, 2),
        "adjusted_profit_yi": round(adjusted_profit / 1e8, 2),
        "profit_impact_pct": round(profit_impact, 1),
        "rd_asset_yi": round(rd_asset / 1e8, 2),
        "rd_amortization_yi": round(rd_amortization / 1e8, 2),
        "adjusted_roe": round(adjusted_roe, 1) if adjusted_roe else None,
        "rd_intensity_pct": round(current_rd / max(reported_profit, 1) * 100, 1) if reported_profit > 0 else None,
        "note": _make_note(profit_impact, current_rd, rd_amortization),
        "material": profit_impact > 10,  # 调整影响超过10% → 值得关注
    }


def _no_rd_result(financials: List[Dict]) -> dict:
    reported_profit = sum(float(q.get("parent_profit", q.get("profit", 0)) or 0) for q in financials[:4])
    return {
        "reported_profit_yi": round(reported_profit / 1e8, 2),
        "adjusted_profit_yi": round(reported_profit / 1e8, 2),
        "profit_impact_pct": 0.0,
        "rd_asset_yi": 0.0,
        "rd_amortization_yi": 0.0,
        "adjusted_roe": None,
        "rd_intensity_pct": 0.0,
        "note": "无研发支出数据或研发支出为0, 无需调整",
        "material": False,
    }


def _make_note(impact: float, rd: float, amort: float) -> str:
    if impact > 20:
        return f"研发资本化后利润上调{impact:.0f}% — 该公司真实盈利能力远优于账面数据"
    if impact > 10:
        return f"研发资本化后利润上调{impact:.0f}%, 财报利润被研发投入显著压低"
    if impact > 5:
        return f"研发资本化后利润上调{impact:.0f}%, 略有影响"
    return "研发资本化调整影响不大"
