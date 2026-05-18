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
                text = await self.provider.chat(prompt)
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
    def parse_json(text: str) -> Any:
        """共享 JSON 解析器 — 处理 markdown 代码块 + 括号计数截断"""
        import json, re
        text = text.strip()
        if "```" in text:
            m = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
            if m:
                text = m.group(1).strip()
        if text.startswith('{'):
            depth = 0
            end = 0
            for i, ch in enumerate(text):
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            if end > 0:
                text = text[:end]
        elif text.startswith('['):
            depth = 0
            end = 0
            for i, ch in enumerate(text):
                if ch == '[':
                    depth += 1
                elif ch == ']':
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            if end > 0:
                text = text[:end]
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"raw_text": text[:800]}
