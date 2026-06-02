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
        # ★ 关键修复: 显式从 ctx 构建 stock 字典, 不再依赖调用方传 "stock" 键
        code = ctx.get("stock_code", "")
        name = ctx.get("stock_name", "")
        industry = ctx.get("industry", "")
        stage = ctx.get("stage", "")

        stock = {
            "code": code,
            "name": name,
            "industry": industry,
            "stage": stage,
        }
        financial = ctx.get("financial", ctx.get("financial_data", {}))
        human = ctx.get("human_capital", {})

        if not code:
            return {"agent": self.name, "error": "No stock_code"}

        logger.info(f"[{self.name}] Pricing {code} {name} industry={industry}")

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
            # ★ 新增: industry 为 LLM 提供明确的行业上下文
            "industry": db_metrics.get("industry", industry),
        }

        if not self.provider:
            return {"agent": self.name, "error": "No AI provider", "code": code}

        # ★ 新增: 使用 framework/finance/model_map 预判 asset_type, 作为 LLM 的参考建议
        suggested_type = None
        try:
            from app.framework.finance.model_map import match_asset_type
            suggested_type = match_asset_type(code, name, industry or hard_anchor.get("industry", ""))
        except Exception:
            pass

        result = await self._price_target(
            stock, financial, human, peers_data, hard_anchor,
            suggested_asset_type=suggested_type)
        result["agent"] = self.name
        result["code"] = code
        result["name"] = name

        # ★ 校验必填字段, 缺失时标记 parse_error
        if not result.get("parse_error"):
            required_fields = ["valuation_summary", "asset_type", "target_valuation", "verdict"]
            missing = [f for f in required_fields if not result.get(f) and
                       f not in result.get("target_valuation", {}) and
                       f not in result.get("valuation_method", {})]
            if missing:
                result["parse_error"] = True
                result["_patch_required"] = ["valuation"]
                result["_missing_fields"] = missing

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
                            human: Dict, peers: List, hard_anchor: Dict,
                            suggested_asset_type: str = None) -> Dict:
        # ★ 精简版估值模型匹配指南 (原版40行→10行, 减少tokens)
        guide = "## 估值模型匹配指南\n\n"
        guide += "根据标的行业判定 asset_type, 选择主估值模型:\n"
        for k, v in self.VALUATION_MODEL_MAP.items():
            kw = ", ".join(v["keywords"][:4])
            guide += f"- {k}({kw}...) → {v['primary']}\n"

        # ★ 注入 model_map 预判建议
        type_hint = ""
        if suggested_asset_type:
            type_hint = (
                f"\n【系统预判】根据金融工具包 model_map 自动判定, 建议 asset_type = "
                f"「{suggested_asset_type}」"
                f"\n若无明显相反证据(行业/财务特征明显不匹配), 优先采用此判定。\n"
            )

        prompt = f"""你是买方首席估值分析师。基于多维度数据, 对标的进行综合估值定价。

{guide}
{type_hint}

## 标的基本信息
{_j(stock)}

## 实时估值锚 (DB硬数据, 必须优先使用)
{_j(hard_anchor)}

## 财务审计结果 (FinancialAuditor)
{_j(financial)}

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
  "moat_window": {{ "years": 5, "barrier_type": "...", "threat_level": "LOW/MEDIUM/HIGH", "reasoning": "..." }},
  "target_valuation": {{
    "base_case_mcap": 500, "unit": "亿元",
    "bull_case_mcap": 700, "bear_case_mcap": 350,
    "upside_pct": 30, "downside_pct": -15
  }},
  "valuation_method": {{
    "primary": "PE+PEG/PB+EV-EBITDA/EV-EBITDA+PEG/PS+FCF/PB+ROE/FCF+股息率",
    "pe_current": null, "pe_target": null,
    "pb_current": null, "pb_target": null,
    "peg_ratio": null,
    "ps_current": null, "ps_target": null,
    "ev_ebitda_current": null, "ev_ebitda_target": null,
    "fcf_yield_pct": null, "dividend_yield_pct": null,
    "growth_rate_est": "未来3年利润CAGR%",
    "reasoning": "为什么选这个模型及其估值逻辑"
  }},
  "scenarios": {{
    "bull": {{ "target_price": null, "upside_pct": null, "assumptions": "..." }},
    "base": {{ "target_price": null, "upside_pct": null, "assumptions": "..." }},
    "bear": {{ "target_price": null, "downside_pct": null, "assumptions": "..." }}
  }},
  "quality_check": {{
    "roe_pct": null, "dividend_yield_pct": null, "eps_growth_3y_pct": null,
    "quality_verdict": "高质/一般/低质"
  }},
  "global_peer_comparison": [
    {{ "name": "对标公司", "code": "NVDA.US", "pe": null, "ps": null, "ev_ebitda": null, "premium_discount": "溢价/折价原因" }}
  ],
  "position_suggest": {{
    "allocation_pct": null, "time_horizon": "...", "entry_strategy": "...", "exit_trigger": "..."
  }},
  "verdict": "BUY/HOLD/SELL",
  "risk_reward_ratio": "1:3 — 解释"
}}

定价规则:
- 综合 FinancialAuditor 的 verdict 调整风险溢价 (FAIL加30%, CAUTION加15%)
- 尽量复用 framework/finance/valuation.py 中的纯函数估值逻辑 (如有)
- moat_window 描述护城河能维持的年限"""
        try:
            text = await self.provider.chat_pro(prompt, max_tokens=16384, timeout=240)
            result = self.parse_json(text)
            if isinstance(result, dict):
                # parse_json 返回 {raw_text, parse_error} 时标记补跑
                if result.get("parse_error"):
                    result["_patch_required"] = ["valuation"]
                    result["agent"] = self.name
                    result["code"] = stock.get("code", "?")
                    result["name"] = stock.get("name", "?")
                    logger.warning(
                        f"[{self.name}] {stock.get('code','?')} "
                        f"parse_error saved, raw_text length={len(result.get('raw_text',''))}")
                    return result

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

        return {"error": "LLM pricing failed", "verdict": "UNKNOWN",
                "_patch_required": ["valuation"]}

    async def load_context(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        return await super().load_context(ctx)

    @staticmethod
    def build_prompt(ctx):
        return "ValuationPricer V5.7"

    @staticmethod
    async def stream(ctx):
        yield "streaming not implemented"
