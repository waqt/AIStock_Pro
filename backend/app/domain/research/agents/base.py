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


# ═══ 注册内置工具 ═══════════════════════════════════


async def _tool_query_financial_data(
    code: str,
    indicators: Optional[List[str]] = None,
    raw_fields: Optional[List[str]] = None,
) -> dict:
    """query_financial_data 的实际执行函数"""
    from app.domain.quant.engine.financial_query_service import FinancialQueryService
    svc = FinancialQueryService()
    return await svc.query(code, indicators=indicators, raw_fields=raw_fields)


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
