"""
MarketScanner V4.0 — AI 主动发现引擎 (Web 实时版)
零参数, 纯新鲜数据: Web搜索→LLM识别热门赛道→生成每日简报
"""
import asyncio, json
from decimal import Decimal
from typing import Dict, Any, List
from app.domain.research.agents.base import ResearchAgent
from app.domain.research.services.data_loader import data_loader
from app.framework.logger import logger


class _SafeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal): return float(obj)
        return super().default(obj)

def _j(obj): return json.dumps(obj, ensure_ascii=False, cls=_SafeEncoder)


class MarketScanner(ResearchAgent):
    """主动发现智能体 V4.0 — 实时扫描市场, 纯新鲜数据"""

    def __init__(self, provider=None):
        super().__init__(provider=provider, data_loader=data_loader)
        self.name = "MarketScanner"

    async def analyze(self, context: Dict[str, Any]) -> Dict[str, Any]:
        ctx = await self.load_context({})
        if not self.provider:
            return {"error": "No AI provider"}

        # Step 1: Web 搜索收集实时市场信号
        signals = await self._collect_signals(ctx)

        # Step 2: LLM 识别热门赛道
        industries = await self._identify_hot_industries(signals)

        # Step 3: LLM 生成每日简报
        briefing = await self._generate_briefing(signals, industries)

        return {
            "agent": self.name,
            "macro": signals["macro"],
            "market_pulse": signals["market_pulse"],
            "search_sources": signals["search_sources"],
            "hot_industries": industries,
            "briefing": briefing,
        }

    # ═══ Step 1: 实时信号收集 (Web搜索) ═══════════

    async def _collect_signals(self, ctx: Dict) -> Dict:
        """4 角度并行搜索实时市场数据"""
        queries = {
            "market": "A股 今日热点板块 资金流向 领涨概念 龙虎榜 2026",
            "macro": "中国央行货币政策 美联储 汇率 宏观要闻 今日 2026",
            "flow": "北向资金 主力资金净流入 行业板块 成交量异动 2026",
            "global": "全球股市 美股 港股 大宗商品 黄金 原油 今日 2026",
        }

        search_results = {}
        for key, query in queries.items():
            items = []
            for r in await self.data_loader.search_web(query, num=4):
                items.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("snippet", "")[:250],
                })
            search_results[key] = items

        # 本地宏观数据作为补充
        macro = ctx.get("macro", {})

        return {
            "macro": macro,
            "market_pulse": {
                "market_news": search_results.get("market", []),
                "flow_news": search_results.get("flow", []),
                "global_news": search_results.get("global", []),
            },
            "macro_news": search_results.get("macro", []),
            "search_sources": sum(len(v) for v in search_results.values()),
        }

    # ═══ Step 2: LLM 识别热门赛道 ═══════════════

    async def _identify_hot_industries(self, signals: Dict) -> List[Dict]:
        prompt = f"""你是 A 股市场策略师。基于以下实时市场数据, 识别当前最值得关注的 3-5 个行业/主题。

## 市场热点与资金流
{_j(signals['market_pulse']['market_news'])}

## 资金流向
{_j(signals['market_pulse']['flow_news'])}

## 全球市场
{_j(signals['market_pulse']['global_news'])}

## 汇率/大宗
{_j(signals['macro'])}

## 要求
1. 每个行业: name(行业名称), score(1-10 景气评分), reason(核心逻辑, 引用搜索结果中的具体数据), global_drivers(全球驱动因素), a_stock_codes(A股映射代码列表)
2. 优先关注有资金流入支撑的行业
3. 区分短期热点(事件驱动) vs 中期趋势(产业逻辑)
4. 如果搜索结果中提到具体股票代码, 必须包含在 a_stock_codes 中

请输出纯 JSON 数组:
[{{"name":"AI算力","score":9,"type":"中期趋势","reason":"英伟达B200量产+...","global_drivers":"MAG7 capex +40%","a_stock_codes":["688256","300308"]}}]"""

        text = await self._safe_call(prompt)
        return self.parse_json(text)

    # ═══ Step 3: 每日简报 ═══════════════════════

    async def _generate_briefing(self, signals: Dict, industries: List) -> str:
        prompt = f"""你是资深投资顾问。基于实时数据生成今日 A 股投资简报。

## 宏观要闻
{_j(signals['macro_news'][:4])}

## 全球市场
{_j(signals['market_pulse']['global_news'][:3])}

## 热门赛道
{_j(industries)}

## 资金流
{_j(signals['market_pulse']['flow_news'][:3])}

## 输出格式 (Markdown)
### 今日市场环境
(2-3句宏观定调 + 全球联动)

### 热门赛道 TOP 3
| 排名 | 行业 | 类型 | 景气评分 | 核心逻辑 | 关注标的 |
|------|------|------|---------|---------|---------|

### 资金面信号
(北向/主力资金动向, 1-2句)

### 操作建议
(基于当前市场环境的策略建议, 1-2句)

### 风险提示
(今日需要关注的宏观/政策/地缘风险, 1-2句)"""

        return await self._safe_call(prompt)

    # ═══ 工具 ═══════════════════════════════════

    async def _safe_call(self, prompt: str) -> str:
        try:
            return await asyncio.wait_for(
                self.provider.chat(prompt, max_tokens=2048), timeout=45) or ""
        except asyncio.TimeoutError:
            logger.warning("[MarketScanner] LLM call timed out")
            return "分析超时, 请重试"
        except Exception as e:
            logger.warning(f"[MarketScanner] LLM call failed: {e}")
            return f"分析异常: {e}"

    # ═══ 基类实现 ═══════════════════════════════

    async def load_context(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        ctx = await super().load_context(ctx)
        ctx["macro"] = await self.data_loader.load_macro()
        return ctx

    @staticmethod
    def build_prompt(ctx):
        return "MarketScanner V4.0"

    @staticmethod
    async def stream(ctx):
        yield "streaming not implemented"
