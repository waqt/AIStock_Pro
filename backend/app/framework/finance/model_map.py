"""
估值模型匹配表 — 从 ValuationPricer 中抽出, 供所有 Agent 复用
"""
from typing import Optional

# ═══ 资产类型 → 估值模型映射 ═════════════════

VALUATION_MODEL_MAP = {
    "stable_consumer": {
        "keywords": ["食品","饮料","白酒","医药","消费","家电","乳业","调味品","日化"],
        "primary": "pe_peg",
        "key_metrics": "ROE>15%, 盈利稳定, 股息率>2%",
        "rationale": "稳定消费/医药企业盈利可预测, PE是核心锚, PEG匹配增速溢价",
    },
    "cyclical": {
        "keywords": ["钢铁","有色","化工","煤炭","石油","航运","造船","水泥","玻璃"],
        "primary": "pb_ev_ebitda",
        "key_metrics": "市净率低位, EV/EBITDA<8",
        "rationale": "强周期行业利润波动剧烈, PE顶部/底部严重失真, PB锚定重置成本更可靠",
    },
    "heavy_manufacturing": {
        "keywords": ["半导体","芯片","设备","装备","重工","机床","轨道交通","航空","军工"],
        "primary": "ev_ebitda_peg",
        "key_metrics": "折旧高, 资本结构差异大",
        "rationale": "重资产制造折旧摊销高且差异大, EV/EBITDA剔除折旧/税率/资本结构干扰",
    },
    "saas_startup": {
        "keywords": ["SaaS","云计算","软件","互联网","平台","AI应用","IT服务"],
        "primary": "ps_unit_econ",
        "key_metrics": "营收增速>30%, 毛利率>60%, 尚处亏损",
        "rationale": "高成长SaaS/互联网企业利润后置, PS衡量市场份额扩张质量",
    },
    "financial": {
        "keywords": ["银行","保险","证券","券商","信托","AMC"],
        "primary": "pb_roe",
        "key_metrics": "ROE>10%, PB<1.5",
        "rationale": "金融业杠杆经营, PB衡量资产质量, ROE衡量盈利能力",
    },
    "cash_cow": {
        "keywords": ["水电","核电","高速","公路","港口","机场","燃气","水务","环保运营"],
        "primary": "fcf_dividend",
        "key_metrics": "FCF/市值>3%, 股息率>3%",
        "rationale": "现金牛资产折旧高导致账面利润低估, 真实自由现金流远超净利润",
    },
}

# ═══ cycle_position → 估值方法建议 ═══════════

CYCLE_VALUATION_GUIDE = {
    "theme_emergence":     {"method": "ps_valuation",    "note": "无利润, 看收入倍数 + 技术壁垒溢价"},
    "demand_explosion":    {"method": "peg_valuation",   "note": "有利润增速, PEG 衡量成长性价比"},
    "bottleneck_formation":{"method": "ev_ebitda_valuation", "note": "重资产扩张期, 叠加定价权溢价"},
    "capital_frenzy":      {"method": "pb_valuation",    "note": "全行业扩产, 资产堆积, 看 PB"},
    "capacity_release":    {"method": "pe_valuation",    "note": "利润释放期, PE 回归正常"},
    "commoditization":     {"method": "fcf_yield_valuation", "note": "成熟期, 看现金流回报"},
}


# ═══ 匹配函数 ═══════════════════════════

def match_asset_type(industry: str, keywords_map: dict = None) -> Optional[str]:
    """根据行业名匹配资产类型 (关键词匹配)"""
    kmap = keywords_map or VALUATION_MODEL_MAP
    industry_lower = industry.lower()
    for asset_type, config in kmap.items():
        for kw in config.get("keywords", []):
            if kw in industry or kw in industry_lower:
                return asset_type
    return None


def get_valuation_method(asset_type: str, cycle_phase: str = None) -> str:
    """获取推荐的估值方法
    优先用 cycle_phase 映射, 降级到 asset_type 映射
    """
    if cycle_phase and cycle_phase in CYCLE_VALUATION_GUIDE:
        return CYCLE_VALUATION_GUIDE[cycle_phase]["method"]
    if asset_type and asset_type in VALUATION_MODEL_MAP:
        return VALUATION_MODEL_MAP[asset_type]["primary"]
    return "pe_valuation"  # 默认
