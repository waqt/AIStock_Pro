"""投研协调器 — 调度多个分析师, 合成最终报告"""
from typing import Dict, Any, List, Optional
from app.domain.research.agents.base import ResearchAgent
from app.domain.research.services.data_loader import data_loader
from app.framework.logger import logger


class ResearchCoordinator(ResearchAgent):
    """投研协调器 — 综合各分析师结论, 生成最终投资建议"""

    def __init__(self, provider=None):
        super().__init__(provider=provider, data_loader=data_loader)
        self.name = "ResearchCoordinator"
        self._analysts: List[ResearchAgent] = []

    def register(self, analyst: ResearchAgent):
        """注册子分析师"""
        analyst.data_loader = self.data_loader
        analyst.provider = self.provider
        self._analysts.append(analyst)
        logger.info(f"[+] Registered analyst: {analyst.name}")

    async def analyze(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """协调分析: 逐个调用分析师 → 合成结论"""
        reports = {}
        for analyst in self._analysts:
            try:
                logger.info(f"[*] Running {analyst.name}...")
                reports[analyst.name] = await analyst.analyze(context)
            except Exception as e:
                logger.error(f"[{analyst.name}] Failed: {e}")
                reports[analyst.name] = {"error": str(e)}

        # 合成: 调用 LLM 汇总各分析师结论
        summary_prompt = self._build_summary_prompt(context, reports)
        if self.provider:
            try:
                summary_text = await self.provider.chat(summary_prompt)
            except Exception:
                summary_text = "AI 合成失败, 请查看各分析师独立报告"
        else:
            summary_text = "未配置 AI 提供者, 无法合成。请查看各分析师独立报告。"

        return {
            "agent": self.name,
            "summary": summary_text,
            "analyst_reports": reports,
            "context": {
                "stock_codes": context.get("stock_codes", []),
                "industry": context.get("industry"),
                "question": context.get("question"),
            }
        }

    def _build_summary_prompt(self, ctx: Dict[str, Any], reports: Dict[str, Any]) -> str:
        """合成最终报告"""
        return f"""你是一位资深投资研究主管。请综合分析以下团队报告, 给出最终投资建议。

## 用户问题
{ctx.get('question', '请基于当前持仓和市场情况给出投资建议')}

## 持仓概况
{ctx.get('positions', '未提供')}

## 各分析师报告
{reports}

## 输出要求
1. 核心结论 (1-2句话)
2. 具体推荐标的 (含代码、名称、推荐理由)
3. 资产配置建议 (仓位比例)
4. 风险提示
5. 操作建议 (与用户持仓和交易风格匹配)

请以结构化 markdown 格式输出。"""

    async def stream(self, context: Dict[str, Any]):
        yield "Research coordinator streaming not yet implemented"

    async def load_context(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """协调器加载全量数据"""
        ctx = await super().load_context(ctx)
        ctx["macro"] = await self.data_loader.load_macro()
        return ctx

    def build_prompt(self, ctx: Dict[str, Any]) -> str:
        return self._build_summary_prompt(ctx, {})


# 全局单例
coordinator = ResearchCoordinator()
