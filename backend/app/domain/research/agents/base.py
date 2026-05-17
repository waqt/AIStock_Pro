from app.framework.agents.base import BaseAgent
from typing import Dict, Any, AsyncIterator


class ResearchAgent(BaseAgent):
    """投研智能体基类 — 输入股票/行业, 输出结构化研报"""

    async def analyze(self, context: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

    async def stream(self, context: Dict[str, Any]) -> AsyncIterator[str]:
        raise NotImplementedError
