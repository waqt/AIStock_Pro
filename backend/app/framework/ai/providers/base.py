from abc import ABC, abstractmethod
from typing import List, Dict, Optional


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

    @property
    @abstractmethod
    def name(self) -> str:
        """提供者名称"""
        ...
