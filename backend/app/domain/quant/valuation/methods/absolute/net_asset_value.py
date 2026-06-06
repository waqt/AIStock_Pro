"""NAV 净资产价值法 — (总资产 - 总负债) / 总股本

适用于金融(银行/保险/证券)、房地产、控股型公司等资产驱动型企业。
"""
from app.domain.quant.valuation.base import ValuationMethod, register_valuation


@register_valuation
class NetAssetValueMethod(ValuationMethod):
    name = "net_asset_value"
    label = "NAV 净资产价值"
    category = "absolute"
    description = "NAV = (总资产 - 总负债) / 总股本。测算每股清算价值, 适用于金融/地产/控股公司"
    output = ["nav_per_share", "nav_vs_price_pct"]
    requires = ["total_assets", "total_liabilities", "total_shares", "mcap_yi"]
    requires_financial_data = True
    judgment = "nav_vs_price_pct>0%→股价低于清算价值(低估)。nav_per_share可作为安全边际参考线。对于控股型公司, NAV折价>30%可能意味着市场过度悲观"
    applicable_scenarios = "适用于控股型公司/综合性企业集团; 地产/基金/资源类公司(资产价值可明确衡量); 极端熊市后寻找破净机会"
    limitations = "账面价值不等于市场价值(资产可能被低估或高估); 无形资产和商誉未计入; 不适用于轻资产和科技公司"

    @classmethod
    def compute(cls, total_assets: float = None, total_liabilities: float = None,
                total_shares: float = None, mcap_yi: float = None, **kwargs) -> dict:
        if not all([total_assets, total_liabilities, total_shares]) or total_shares <= 0:
            return {k: None for k in cls.output}

        nav = (total_assets - total_liabilities) / total_shares
        if nav <= 0:
            nav = (total_equity or 0) / total_shares  # 兜底用股东权益

        price = (mcap_yi * 1e8) / total_shares if mcap_yi and total_shares > 0 else None
        vs_price = round((nav - price) / price * 100, 1) if price and price > 0 else None

        return {
            "nav_per_share": round(nav, 2),
            "nav_vs_price_pct": vs_price,
        }
