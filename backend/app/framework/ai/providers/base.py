from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Optional


# ═══ Tool Calling 数据结构 ═══════════════════════════════


@dataclass
class ToolCall:
    """模型发起的工具调用请求"""
    id: str
    name: str
    arguments: dict


@dataclass
class ChatResult:
    """支持工具的对话响应"""
    content: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None
    role: str = "assistant"


# ═══ 统一接口 ═══════════════════════════════════════════


class AIProviderProtocol(ABC):
    """AI 提供者统一接口"""

    @abstractmethod
    async def vision(self, image_b64: str, prompt: str) -> Optional[List[Dict]]:
        """图片识别 → 结构化 JSON 列表"""
        ...

    @abstractmethod
    async def chat(self, prompt: str, max_tokens: int = 4096) -> Optional[str]:
        """纯文本对话"""
        ...

    async def chat_with_tools(
        self,
        prompt: str,
        tools: List[Dict],
        messages: Optional[List[Dict]] = None,
        max_tokens: int = 4096,
    ) -> ChatResult:
        """支持工具调用的对话（默认不支持，由各 Provider 按需覆写）"""
        raise NotImplementedError(f"{type(self).__name__} does not support tool calling")

    @property
    @abstractmethod
    def name(self) -> str:
        """提供者名称"""
        ...
