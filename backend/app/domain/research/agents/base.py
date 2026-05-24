"""投研智能体基座 — 继承 BaseAgent, 注入数据加载能力"""
from typing import Dict, Any, List, Optional
from app.framework.agents.base import BaseAgent
from app.framework.logger import logger


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
