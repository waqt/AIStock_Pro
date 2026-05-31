"""
ValuationPricer V5.7 — 资产特性匹配估值模型 + 护城河时间窗 + 三情景分析
输入: stock + financial_audit + human_capital + global_peer + fundamentals
输出: target_mcap, moat_window_years, scenarios, quality_check
"""
import asyncio
import json as _json
from decimal import Decimal
from typing import Dict, Any, List
from app.domain.research.agents.base import ResearchAgent
from app.domain.research.services.data_loader import data_loader
from app.framework.logger import logger


class _SafeEncoder(_json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return float(o)
        return super().default(o)


def _j(obj, **kw):
    kw.setdefault("ensure_ascii", False)
    kw.setdefault("cls", _SafeEncoder)
    return _json.dumps(obj, **kw)


class ValuationPricer(ResearchAgent):
    """估值定价师 V5.7 — 资产特性匹配估值模型 + 护城河时间窗 + 三情景分析"""

    VALUATION_MODEL_MAP = {
        "stable_consumer": {
            "keywords": ["食品","饮料","白酒","医药","消费","家电","乳业","调味品","日化"],
            "primary": "PE + PEG",
            "key_metrics": "ROE>15%, 盈利稳定, 股息率>2%",
            "rationale": "稳定消费/医药企业盈利可预测, PE是核心锚, PEG匹配增速溢价",
        },
        "cyclical": {
            "keywords": ["钢铁","有色","化工","煤炭","石油","航运","造船","水泥","玻璃"],
            "primary": "PB + EV/EBITDA",
            "key_metrics": "市净率低位, EV/EBITDA<8",
            "rationale": "强周期行业利润波动剧烈, PE顶部/底部严重失真, PB锚定重置成本更可靠",
        },
        "heavy_manufacturing": {
            "keywords": ["半导体","芯片","设备","装备","重工","机床","轨道交通","航空","军工"],
            "primary": "EV/EBITDA + PEG",
            "key_metrics": "折旧高, 资本结构差异大",
            "rationale": "重资产制造折旧摊销高且差异大, EV/EBITDA剔除折旧/税率/资本结构干扰",
        },
        "saas_startup": {
            "keywords": ["SaaS","云计算","软件","互联网","平台","AI应用","IT服务"],
            "primary": "PS + 单位经济效益",
            "key_metrics": "营收增速>30%, 毛利率>60%, 尚处亏损",
            "rationale": "高成长SaaS/互联网企业利润后置, PS衡量市场份额扩张质量, 需加单位经济验证",
        },
        "financial": {
            "keywords": ["银行","保险","证券","券商","信托","AMC"],
            "primary": "PB + ROE",
            "key_metrics": "ROE>10%, PB<1.5",
            "rationale": "金融业杠杆经营, PB衡资产质量, ROE衡盈利能力, 两者联动决定估值",
        },
        "cash_cow": {
            "keywords": ["水电","核电","高速","公路","港口","机场","燃气","水务","环保运营"],
            "primary": "市值/自由现金流 + 股息率",
            "key_metrics": "FCF/市值>3%, 股息率>3%, 折旧拖累账面利润",
            "rationale": "现金牛资产折旧高导致账面利润低估, 真实自由现金流远超净利润",
        },
    }

    def __init__(self, provider=None):
        super().__init__(provider=provider, data_loader=data_loader)
        self.name = "ValuationPricer"

    async def analyze(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        stock = ctx.get("stock", {})
        financial = ctx.get("financial", {})
        human = ctx.get("human_capital", {})

        code = stock.get("code", ctx.get("stock_code", ""))
        name = stock.get("name", ctx.get("stock_name", ""))

        if not code:
            return {"agent": self.name, "error": "No stock_code"}

        logger.info(f"[{self.name}] Pricing {code} {name}")

        peers_data = await self._search_global_peers(name, code)

        fundamentals = await self.data_loader.load_fundamentals([code])
        db_metrics = fundamentals.get(code, {})
        hard_anchor = {
            "pe_ttm": db_metrics.get("pe_ttm"),
            "pb": db_metrics.get("pb"),
            "mcap_yi": db_metrics.get("mcap_yi"),
            "roe": db_metrics.get("roe"),
            "dividend_yield": db_metrics.get("dividend_yield"),
            "eps_growth_3y": db_metrics.get("eps_growth_3y"),
        }

        if not self.provider:
            return {"agent": self.name, "error": "No AI provider", "code": code}

        result = await self._price_target(stock, financial, human, peers_data, hard_anchor)
        result["agent"] = self.name
        result["code"] = code
        result["name"] = name
        return result

    async def _search_global_peers(self, name: str, code: str) -> List:
        query = f"{name} global peer competitor market cap PE PS valuation 2026"
        items = []
        for r in await self.data_loader.search_web(query, num=4):
            items.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("snippet", "")[:300],
            })
        return items

    async def _price_target(self, stock: Dict, financial: Dict,
                            human: Dict, peers: List, hard_anchor: Dict) -> Dict:
        # 构建估值模型匹配指南
        guide = "## 估值模型匹配规则 (必须遵守)\n\n"
        guide += "先判定标的资产类型, 再选择主估值模型:\n\n"
        guide += "| 资产类型 | 主估值模型 | 关键指标 | 适用逻辑 |\n"
        guide += "|---------|-----------|---------|--------|\n"
        for k, v in self.VALUATION_MODEL_MAP.items():
            kw = "/".join(v["keywords"][:3])
            guide += f"| {k} ({kw}...) | {v['primary']} | {v['key_metrics']} | {v['rationale']} |\n"
        guide += "\n步骤: ① 根据标的行业+财务特征判定 asset_type → ② 选对应的 model_primary → ③ 用该模型核心指标定价\n"

        prompt = f"""你是买方首席估值分析师。基于多维度数据, 对标的进行综合估值定价。

{guide}

## 标的基本信息
{_j(stock)}

## 实时估值锚 (DB硬数据, 必须优先使用)
{_j(hard_anchor)}

## 财务审计结果 (FinancialAuditor)
{_j(financial)}

## 人力资本审计 (HumanCapitalDetective)
{_j(human)}

## 全球对标搜索
{_j(peers)}

## 关键规则
- pe_current/ps_current/pb_current 必须使用上述估值锚中的值
- market_cap 必须使用 mcap_yi 值 (单位: 亿元)
- ROE/股息率/eps_growth 必须使用硬数据, null则标注"未覆盖"并用对标估算
- 必须先判定 asset_type, 再选 model_primary
- 如果硬数据与匹配模型冲突 (如消费股ROE极低), 在 model_reasoning 中解释

## 输出: 纯 JSON
{{
  "valuation_summary": "估值核心结论 (1-2句中文)",
  "asset_type": "stable_consumer/cyclical/heavy_manufacturing/saas_startup/financial/cash_cow",
  "asset_type_reasoning": "判定依据 (行业+财务特征)",
  "moat_window": {{
    "years": 5,
    "barrier_type": "技术专利/客户认证/产能规模/政策壁垒",
    "threat_level": "LOW/MEDIUM/HIGH",
    "reasoning": "时间窗量化依据"
  }},
  "target_valuation": {{
    "base_case_mcap": 500, "unit": "亿元",
    "bull_case_mcap": 700, "bear_case_mcap": 350,
    "upside_pct": 30, "downside_pct": -15
  }},
  "valuation_method": {{
    "primary": "PE+PEG/PB+EV-EBITDA/PS+单位经济/EV-EBITDA+PEG/PB+ROE/FCF+股息率",
    "pe_current": 45.0, "pe_target": 55.0,
    "pb_current": 5.0, "pb_target": 6.5,
    "peg_ratio": 0.8,
    "ps_current": 8.0, "ps_target": 10.0,
    "ev_ebitda_current": 15.0, "ev_ebitda_target": 18.0,
    "fcf_yield_pct": 3.5, "dividend_yield_pct": 2.1,
    "growth_rate_est": "未来3年利润CAGR%",
    "reasoning": "为什么选这个模型及其估值逻辑"
  }},
  "scenarios": {{
    "bull": {{ "target_price": 120.0, "upside_pct": 50, "assumptions": "市占率达15%, 毛利率升至45%, 新产线满产" }},
    "base": {{ "target_price": 90.0, "upside_pct": 12, "assumptions": "行业增速维持, 份额稳定, 估值回归中位数" }},
    "bear": {{ "target_price": 55.0, "downside_pct": -30, "assumptions": "竞争加剧毛利率降10%, 下游需求萎缩15%" }}
  }},
  "quality_check": {{
    "roe_pct": 18.5, "dividend_yield_pct": 1.8, "eps_growth_3y_pct": 15.2,
    "quality_verdict": "高质/一般/低质 — ROE>15%+股息>2%+增速>10%为高质"
  }},
  "global_peer_comparison": [
    {{ "name": "对标公司", "code": "NVDA.US", "pe": 55, "ps": 20, "ev_ebitda": 25, "premium_discount": "溢价/折价原因" }}
  ],
  "position_suggest": {{
    "allocation_pct": 10,
    "time_horizon": "6-12个月/1-3年",
    "entry_strategy": "现价建仓/等回调/分步建仓",
    "exit_trigger": "什么情况下该卖出"
  }},
  "verdict": "BUY/HOLD/SELL",
  "risk_reward_ratio": "1:3 — 解释"
}}

定价规则:
- moat_window: 护城河能量化到多少年
- peg_ratio: PE/利润增速%, <1=低估, >2=泡沫
- fcf_yield: 自由现金流/市值, >5%为高现金回报
- 综合 FinancialAuditor 的 verdict 调整风险溢价 (FAIL加30%, CAUTION加15%)
- 综合 HumanCapitalDetective 的 score 调整管理层折价/溢价"""

        try:
            text = await self.provider.chat_pro(prompt, max_tokens=4096, timeout=240)
            result = self.parse_json(text)
            if isinstance(result, dict):
                logger.info(
                    f"[{self.name}] {stock.get('code', '?')} "
                    f"verdict: {result.get('verdict')}, "
                    f"asset_type: {result.get('asset_type', '?')}, "
                    f"model: {result.get('valuation_method', {}).get('primary', '?')}, "
                    f"upside: {result.get('target_valuation', {}).get('upside_pct', '?')}%")
                return result
        except asyncio.TimeoutError:
            logger.warning(f"[{self.name}] Pricing timeout")
        except Exception as e:
            logger.warning(f"[{self.name}] Pricing failed: {e}")

        return {"error": "LLM pricing failed", "verdict": "UNKNOWN"}

    async def load_context(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        return await super().load_context(ctx)

    @staticmethod
    def build_prompt(ctx):
        return "ValuationPricer V5.7"

    @staticmethod
    async def stream(ctx):
        yield "streaming not implemented"
