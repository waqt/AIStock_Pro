"""高景气行业分析师 — 识别高景气赛道 + 推荐龙头"""
from typing import Dict, Any
from app.domain.research.agents.base import ResearchAgent
from app.domain.research.services.data_loader import data_loader


class IndustryAnalyst(ResearchAgent):
    """行业景气度分析智能体"""

    def __init__(self, provider=None):
        super().__init__(provider=provider, data_loader=data_loader)
        self.name = "IndustryAnalyst"

    async def analyze(self, context: Dict[str, Any]) -> Dict[str, Any]:
        ctx = await self.load_context(context)
        prompt = self.build_prompt(ctx)

        if not self.provider:
            return {"agent": self.name, "error": "No AI provider", "data": ctx}

        text = await self.provider.chat(prompt)
        return self.parse_result(text, ctx)

    async def load_context(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        ctx = await super().load_context(ctx)
        # 额外加载宏观数据 (用于行业判断)
        ctx["macro"] = await self.data_loader.load_macro()
        return ctx

    def build_prompt(self, ctx: Dict[str, Any]) -> str:
        industry = ctx.get("industry", "未指定")
        codes = ctx.get("stock_codes", [])
        sector = ctx.get("sector_overview", {})
        positions = ctx.get("positions", [])
        macro = ctx.get("macro", {})

        # 汇总持仓行业分布
        pos_industries = {}
        fund_data = ctx.get("fundamentals", {})
        for code, info in fund_data.items():
            ind = info.get("industry", "未知")
            if ind not in pos_industries:
                pos_industries[ind] = []
            pos_industries[ind].append(f"{code} {info.get('name','')} PE={info.get('pe_ttm','?')}")

        return f"""你是一位专注于 A 股市场行业景气度分析的研究员。请分析以下数据并给出结论。

## 宏观环境
{macro}

## 聚焦行业
{industry}

## 行业估值概览
{json.dumps(sector, ensure_ascii=False) if sector else '数据未加载'}

## 用户当前持仓行业分布
{json.dumps(pos_industries, ensure_ascii=False)}

## 用户持仓明细
{json.dumps(positions, ensure_ascii=False, indent=2) if positions else '无持仓数据'}

## 分析任务
1. 判断 {industry} 行业当前景气度 (高/中/低)
2. 给出该行业 3-5 个最值得关注的标的 (含代码和理由)
3. 用户现有持仓中该行业的配置是否合理
4. 是否建议增配/减配该行业
5. 风险点提示

请以结构化 markdown 返回。"""

    def parse_result(self, text: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "agent": self.name,
            "industry": ctx.get("industry"),
            "report": text,
            "sector_data": ctx.get("sector_overview"),
        }


import json
