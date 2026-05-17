from abc import ABC, abstractmethod
from typing import AsyncIterator, Dict, Any, Optional


class BaseAgent(ABC):
    """所有领域智能体的抽象基类

    子类示例:
      - QuantAgent: 输入 OHLCV+指标 → 输出多空判断+置信度
      - ResearchAgent: 输入股票/行业 → 输出结构化研报
      - StrategyAgent: 输入信号列表 → 输出调仓方案
    """

    def __init__(self, provider=None):
        """provider: AIProviderProtocol 实例 (豆包/Gemini/DeepSeek)"""
        self.provider = provider

    @abstractmethod
    async def analyze(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """同步分析, 返回结构化结论"""
        ...

    @abstractmethod
    async def stream(self, context: Dict[str, Any]) -> AsyncIterator[str]:
        """流式输出 (研报/长篇分析)"""
        ...

    def build_prompt(self, context: Dict[str, Any]) -> str:
        """子类可重写, 将上下文组装为 LLM prompt"""
        raise NotImplementedError
