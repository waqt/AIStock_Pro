"""投研智能体基座 — 继承 BaseAgent, 注入数据加载 + 工具调用能力"""
import json
from typing import Dict, Any, List, Optional
from app.framework.agents.base import BaseAgent
from app.framework.logger import logger


# ═══ 工具注册表 ═══════════════════════════════════════

TOOL_REGISTRY: Dict[str, Any] = {}
"""工具名称 → 可调用函数 的映射, 通过 register_tool 注册"""


def register_tool(name: str):
    """装饰器: 注册工具到全局注册表"""
    def decorator(func):
        TOOL_REGISTRY[name] = func
        return func
    return decorator


# ═══ 工具定义 ═══════════════════════════════════════

QUERY_FINANCIAL_DATA_TOOL = {
    "type": "function",
    "function": {
        "name": "query_financial_data",
        "description": "查询股票的财务指标或原始财报数据。通过 indicators 参数获取已注册的计算指标（如 roic_pct, margin, ocf_health 等），通过 raw_fields 参数获取原始财报字段（如 revenue, op_cashflow, rd_expense 等）。两个参数可同时使用。",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "6位股票代码，如 '688012'",
                },
                "indicators": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "需要获取的财务指标名称列表（可选，不传则不获取指标）",
                },
                "raw_fields": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "需要获取的原始财报字段列表（可选，不传则不获取原始字段）",
                },
            },
            "required": ["code"],
        },
    },
}

WEB_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "搜索网络获取实时行业/公司/市场信息。每次搜索返回标题+摘要列表。"
                       "用于获取行业动态、竞争格局、技术路线、市场份额等无法从财务数据直接获取的信息。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词，建议包含公司名/股票代码+核心维度，"
                                   "如'中微公司 688012 刻蚀设备 市场份额 2026'",
                },
                "num": {
                    "type": "integer",
                    "description": "返回结果数量（1-10），默认5",
                },
            },
            "required": ["query"],
        },
    },
}

DEFAULT_TOOL_DEFINITIONS = [QUERY_FINANCIAL_DATA_TOOL]
# web_search 已在 TOOL_REGISTRY 注册, 但不加入默认工具列表。
# 只在特定环节（如 Step 6 Phase 3b 6维权力画像）显式传入使用。

# ═══ 技术指标工具定义 ═══════════════════════════════

TECHNICAL_INDICATORS_TOOL = {
    "type": "function",
    "function": {
        "name": "query_technical_indicators",
        "description": "查询股票的技术指标时序数据。支持 RSI(强弱), MACD(趋势), KDJ(超买超卖), CCI(动量), BB_WIDTH(波动率), MA5/MA10/MA20(均线), OBV(量能), crowding_ratio(拥挤度), chip_concentration(筹码集中度) 等。返回时间序列 + 最新快照。",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "6位股票代码，如 '688012'",
                },
                "fields": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "需要获取的技术指标列表（可选, 不传则返回全部可用字段）",
                },
                "days": {
                    "type": "integer",
                    "description": "返回最近 N 个交易日的数据, 默认 120, 最大 500",
                },
            },
            "required": ["code"],
        },
    },
}

FUNDAMENTALS_TOOL = {
    "type": "function",
    "function": {
        "name": "query_fundamentals",
        "description": "查询股票的基本面估值快照。返回 PE_TTM, PB, 市值, ROE, 股息率, 营收/利润增速(3年复合), 行业分类等。适合快速了解股票当前估值水平和基本面画像。",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "6位股票代码，如 '688012'",
                },
            },
            "required": ["code"],
        },
    },
}

HEALTH_CHECK_TOOLS = [QUERY_FINANCIAL_DATA_TOOL, WEB_SEARCH_TOOL, TECHNICAL_INDICATORS_TOOL, FUNDAMENTALS_TOOL]
"""StockHealthChecker 使用的完整工具集"""


# ═══ 注册内置工具 ═══════════════════════════════════


async def _tool_query_financial_data(
    code: str,
    indicators: Optional[List[str]] = None,
    raw_fields: Optional[List[str]] = None,
) -> dict:
    """query_financial_data 的实际执行函数 (含数据保鲜检查 + 自动同步)"""
    from app.domain.quant.engine import indicator_store as _ind_store

    # ── 保鲜度检查 ──
    fresh = _ind_store.check_financial_freshness(code)
    if not fresh["has_data"]:
        logger.info(f"[Tool:query_financial_data] {code}: no cached data, triggering compute...")
        try:
            from app.domain.quant.engine.financial_compute import compute_financial_for_codes
            sync_result = await compute_financial_for_codes([code], mode="local")
            if sync_result.get(code, {}).get("error"):
                logger.warning(f"[Tool:query_financial_data] {code}: compute reported error: {sync_result[code]['error']}")
        except Exception as e:
            logger.warning(f"[Tool:query_financial_data] {code}: auto-sync failed: {e}")
    elif not fresh["is_fresh"]:
        logger.info(f"[Tool:query_financial_data] {code}: stale ({fresh['quarters']}Q), triggering re-compute...")
        try:
            from app.domain.quant.engine.financial_compute import compute_financial_for_codes
            await compute_financial_for_codes([code], mode="local")
        except Exception as e:
            logger.warning(f"[Tool:query_financial_data] {code}: auto-recompute failed: {e}")

    # ── 查询 ──
    from app.domain.quant.engine.financial_query_service import FinancialQueryService
    svc = FinancialQueryService()
    data = await svc.query(code, indicators=indicators, raw_fields=raw_fields)
    data["_data_freshness"] = fresh
    return data


register_tool("query_financial_data")(_tool_query_financial_data)


async def _tool_web_search(query: str, num: int = 5) -> list:
    """web_search 的实际执行函数"""
    from app.domain.research.services.data_loader import data_loader
    try:
        results = await data_loader.search_web(query, num=num)
        items = []
        for r in results:
            snippet = (r.get("snippet", "") or "")[:500]
            if "%PDF" in snippet or "endstream" in snippet:
                continue
            items.append({
                "title": r.get("title", ""),
                "snippet": snippet,
            })
        return items
    except Exception as e:
        return [{"error": str(e)}]


register_tool("web_search")(_tool_web_search)


async def _tool_query_technical_indicators(
    code: str,
    fields: list = None,
    days: int = 120,
) -> dict:
    """query_technical_indicators 的实际执行函数 (含数据保鲜检查 + 自动同步)"""
    from app.domain.quant.engine import indicator_store as _ind_store

    # ── 保鲜度检查 ──
    fresh = _ind_store.check_technical_freshness(code)
    if not fresh["has_data"]:
        logger.info(f"[Tool:query_technical_indicators] {code}: no cached data, triggering compute...")
        try:
            from app.domain.quant.engine.indicator_runner import IndicatorRunner
            await IndicatorRunner.compute_historical(code)
        except Exception as e:
            logger.warning(f"[Tool:query_technical_indicators] {code}: auto-sync failed: {e}")
    elif not fresh["is_fresh"] and fresh["days"] < 60:
        logger.info(f"[Tool:query_technical_indicators] {code}: stale ({fresh['days']}d), triggering increment...")
        try:
            from app.domain.quant.engine.indicator_runner import IndicatorRunner
            await IndicatorRunner.compute_incremental(code)
        except Exception as e:
            logger.warning(f"[Tool:query_technical_indicators] {code}: auto-increment failed: {e}")

    # ── 查询 ──
    try:
        latest = _ind_store.get_latest(code)
        if fields and len(fields) > 0:
            fields_clean = [f for f in fields if f not in ('trade_date', 'stock_code')]
            hist = _ind_store.get_history(code, fields=fields_clean, days=min(days, 500))
        else:
            default_fields = ["price","rsi","macd","macd_signal","macd_hist",
                              "k","d","j","cci","bb_width","obv",
                              "ma5","ma20","ma60","crowding_ratio","sharpe_60d",
                              "chip_concentration","chip_pattern"]
            hist = _ind_store.get_history(code, fields=default_fields, days=min(days, 500))
        result = {
            "stock_code": code,
            "latest": {k: v for k, v in (latest or {}).items() if not k.startswith('_')},
            "history": hist,
            "_data_freshness": fresh,
        }
        return result
    except Exception as e:
        return {"stock_code": code, "error": str(e), "_data_freshness": fresh}


register_tool("query_technical_indicators")(_tool_query_technical_indicators)


async def _tool_query_fundamentals(code: str) -> dict:
    """query_fundamentals 的实际执行函数 (含数据保鲜检查 + 自动同步)"""
    # ── 保鲜度检查 ──
    from app.domain.market_data.services.valuation import check_fundamentals_freshness, sync_valuation, sync_stock_info
    fresh = await check_fundamentals_freshness(code)
    if not fresh["has_data"] or not fresh["has_name"]:
        logger.info(f"[Tool:query_fundamentals] {code}: missing data (data={fresh['has_data']}, name={fresh['has_name']}), syncing...")
        try:
            if not fresh["has_name"]:
                await sync_stock_info(code)
            await sync_valuation(target_codes=[code])
        except Exception as e:
            logger.warning(f"[Tool:query_fundamentals] {code}: auto-sync failed: {e}")

    # ── 查询 (通过 research domain data_loader, 这是 research 工具的合法入口) ──
    from app.domain.research.services.data_loader import data_loader
    try:
        result = await data_loader.load_fundamentals([code])
        data = result.get(code, {})
        data["_data_freshness"] = fresh
        return data
    except Exception as e:
        return {"code": code, "error": str(e), "_data_freshness": fresh}


register_tool("query_fundamentals")(_tool_query_fundamentals)


class ResearchAgent(BaseAgent):
    """投研分析智能体 — 公共基础: 数据加载 + 搜索 + LLM分析"""

    def __init__(self, provider=None, data_loader=None):
        super().__init__(provider)
        self.data_loader = data_loader  # ResearchDataLoader 实例
        self.name = self.__class__.__name__

    async def analyze(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """默认: 加载上下文数据 → 构建prompt → 调用LLM → 解析结论"""
        try:
            # 1. 加载数据
            enriched = await self.load_context(context)
            # 2. 构建 prompt
            prompt = self.build_prompt(enriched)
            # 3. 调用 LLM
            if self.provider:
                text = await self.provider.chat_pro(prompt)
                return self.parse_result(text, enriched)
            return {"error": "No AI provider configured", "agent": self.name}
        except Exception as e:
            logger.error(f"[{self.name}] Analysis failed: {e}")
            return {"error": str(e), "agent": self.name}

    # ═══ 工具调用增强 ═══════════════════════════════

    async def analyze_with_tools(
        self,
        context: Dict[str, Any],
        tool_defs: Optional[List[Dict]] = None,
        max_rounds: int = 5,
    ) -> Dict[str, Any]:
        """工具增强版分析: 注入动态数据字典 → 工具调用循环 → 解析结论

        Agent 在 prompt 中通过 {{FINANCIAL_CATALOG}} 占位符使用数据字典。
        子类重写 build_prompt() 时在 prompt 中包含此占位符即可自动注入。
        """
        try:
            enriched = await self.load_context(context)
            prompt = self.build_prompt(enriched)

            # 注入动态财务数据字典
            try:
                from app.domain.quant.engine.financial_query_service import (
                    FinancialQueryService,
                )
                catalog = FinancialQueryService.format_catalog_for_prompt()
                prompt = prompt.replace("{{FINANCIAL_CATALOG}}", catalog)
            except ImportError:
                logger.warning(f"[{self.name}] FinancialQueryService not available, skipping catalog injection")
            except Exception as e:
                logger.warning(f"[{self.name}] Catalog injection failed: {e}")

            if not self.provider:
                return {"error": "No AI provider configured", "agent": self.name}

            tools = tool_defs or DEFAULT_TOOL_DEFINITIONS
            msgs = [{"role": "user", "content": prompt}]

            for _round in range(max_rounds):
                result = await self.provider.chat_with_tools(
                    prompt="", tools=tools, messages=msgs
                )

                if result.tool_calls:
                    # ★ 先添加 assistant tool_calls 消息 (Anthropic 需要 tool_use → tool_result 配对)
                    msgs.append({
                        "role": "assistant",
                        "content": result.content or "",
                        "tool_calls": [
                            {"id": tc.id, "type": "function",
                             "function": {"name": tc.name, "arguments": json.dumps(tc.arguments, ensure_ascii=False)}}
                            for tc in result.tool_calls
                        ],
                    })
                    for tc in result.tool_calls:
                        fn = TOOL_REGISTRY.get(tc.name)
                        if fn:
                            logger.info(
                                f"[{self.name}] Tool call: {tc.name}({json.dumps(tc.arguments, ensure_ascii=False)})"
                            )
                            try:
                                data = await fn(**tc.arguments)
                                content = json.dumps(data, ensure_ascii=False, default=str)
                            except Exception as e:
                                logger.warning(f"[{self.name}] Tool {tc.name} failed: {e}")
                                content = json.dumps({"error": str(e)})
                        else:
                            content = json.dumps({"error": f"Unknown tool: {tc.name}"})

                        msgs.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": content,
                        })
                else:
                    return self.parse_result(result.content or "", enriched)

            logger.warning(f"[{self.name}] Max tool rounds ({max_rounds}) reached")
            return {"error": f"Max tool call rounds ({max_rounds}) reached", "agent": self.name}

        except Exception as e:
            logger.error(f"[{self.name}] analyze_with_tools failed: {e}")
            return {"error": str(e), "agent": self.name}

    async def call_with_tools(
        self,
        prompt: str,
        tool_defs: Optional[List[Dict]] = None,
        max_rounds: int = 5,
    ) -> str:
        """低级别工具调用循环 — 供子类硬编码步骤使用

        不经过 load_context/build_prompt/parse_result 生命周期,
        直接发送 prompt → 自动执行工具调用 → 返回最终文本。
        """
        if not self.provider:
            return ""

        tools = tool_defs or DEFAULT_TOOL_DEFINITIONS
        msgs = [{"role": "user", "content": prompt}]

        for _round in range(max_rounds):
            result = await self.provider.chat_with_tools(
                prompt="", tools=tools, messages=msgs
            )

            if result.tool_calls:
                # ★ 先添加 assistant tool_calls 消息 (Anthropic 需要 tool_use → tool_result 配对)
                msgs.append({
                    "role": "assistant",
                    "content": result.content or "",
                    "tool_calls": [
                        {"id": tc.id, "type": "function",
                         "function": {"name": tc.name, "arguments": json.dumps(tc.arguments, ensure_ascii=False)}}
                        for tc in result.tool_calls
                    ],
                })
                for tc in result.tool_calls:
                    fn = TOOL_REGISTRY.get(tc.name)
                    if fn:
                        try:
                            data = await fn(**tc.arguments)
                            content = json.dumps(data, ensure_ascii=False, default=str)
                        except Exception as e:
                            content = json.dumps({"error": str(e)})
                    else:
                        content = json.dumps({"error": f"Unknown tool: {tc.name}"})

                    msgs.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": content,
                    })
            else:
                return result.content or ""

        return ""

    async def load_context(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """加载分析所需的全部数据 (子类可重写以加载特定数据)"""
        if not self.data_loader:
            return ctx
        result = dict(ctx)

        # 如果有股票代码列表, 加载行情和基本面
        codes = ctx.get("stock_codes", [])
        if codes:
            result["market_data"] = await self.data_loader.load_market_data(codes)
            result["fundamentals"] = await self.data_loader.load_fundamentals(codes)
            result["indicators"] = await self.data_loader.load_indicators(codes)

        # 如果有行业关键词
        industry = ctx.get("industry")
        if industry:
            result["sector_overview"] = await self.data_loader.load_sector_overview(industry)

        # 如果有持仓分析需求
        if ctx.get("include_portfolio"):
            result["positions"] = await self.data_loader.load_positions()

        return result

    def build_prompt(self, ctx: Dict[str, Any]) -> str:
        """子类必须重写 — 将上下文组装为 LLM prompt"""
        raise NotImplementedError

    def parse_result(self, text: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """解析 LLM 输出为结构化结论 (子类可重写)"""
        return {"raw_text": text, "agent": self.name}

    async def stream(self, context: Dict[str, Any]):
        raise NotImplementedError

    @staticmethod
    def freshness_stamp() -> Dict[str, Any]:
        """返回数据新鲜度戳 — 每个 Agent 输出时附带, 防止用到过期数据"""
        from datetime import datetime
        return {
            "generated_at": datetime.now().isoformat(),
            "data_sources": {
                "web_search": "实时 (DDG/Brave via Clash)",
                "market_data": "持仓同步时的最新日线 (AkShare/EastMoney)",
                "financials": "最近8个季度财报 (akshare)",
                "valuation": "腾讯行情实时 PE/PB/市值",
                "macro": "新浪实时汇率/黄金/原油",
            }
        }

    @staticmethod
    def parse_json(text: str) -> Any:
        """共享 JSON 解析器 — 处理 markdown 代码块 + 括号计数截断"""
        import json, re
        text = text.strip()
        if "```" in text:
            m = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
            if m:
                text = m.group(1).strip()
        # 括号计数截断 + 自动补全
        if text.startswith('{') or text.startswith('['):
            brace_depth = 0
            bracket_depth = 0
            in_string = False
            end = 0
            for i, ch in enumerate(text):
                if ch == '"' and (i == 0 or text[i-1] != '\\'):
                    in_string = not in_string
                if not in_string:
                    if ch == '{': brace_depth += 1
                    elif ch == '}': brace_depth -= 1
                    elif ch == '[': bracket_depth += 1
                    elif ch == ']': bracket_depth -= 1
                if brace_depth == 0 and bracket_depth == 0:
                    end = i + 1
            if end > 0:
                text = text[:end]
            elif brace_depth > 0 or bracket_depth > 0:
                # 截断了: 自动补闭合括号
                text = text.rstrip(',\n')
                if bracket_depth > 0:
                    text += ']' * bracket_depth
                if brace_depth > 0:
                    text += '}' * brace_depth
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # 常见 LLM JSON 错误修复
            fixed = text
            # 1. 去除尾部逗号
            fixed = re.sub(r',\s*([}\]])', r'\1', fixed)
            # 2. 修复字符串值内的换行 (LLM 常在长文本中换行)
            fixed = re.sub(r'(?<=": )"([^"]*\n[^"]*)"', lambda m: '"' + m.group(1).replace('\n', '\\n') + '"', fixed)
            # 3. 去除控制字符 (除了 \n \t)
            fixed = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', fixed)
            # 4. 尾部清理
            fixed = fixed.strip().rstrip(',')
            try:
                return json.loads(fixed)
            except json.JSONDecodeError:
                return {"raw_text": text[:800], "parse_error": True}
