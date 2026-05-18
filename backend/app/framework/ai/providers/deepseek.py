import json
from typing import List, Dict, Optional
import httpx
from app.framework.ai.providers.base import AIProviderProtocol
from app.framework.config import settings
from app.framework.logger import logger


class DeepSeekProvider(AIProviderProtocol):
    """DeepSeek API — Anthropic 兼容端点"""

    @property
    def name(self) -> str:
        return "DeepSeek"

    async def vision(self, image_b64: str, prompt: str) -> Optional[List[Dict]]:
        if not settings.DEEPSEEK_API_KEY:
            return None
        base = settings.DEEPSEEK_BASE_URL.rstrip("/")
        is_anthropic = "anthropic" in base
        if is_anthropic:
            url = f"{base}/messages"
            body = {
                "model": settings.DEEPSEEK_MODEL, "max_tokens": 2048,
                "messages": [{"role": "user", "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64}},
                    {"type": "text", "text": prompt}
                ]}]
            }
        else:
            url = f"{base}/chat/completions"
            body = {
                "model": settings.DEEPSEEK_MODEL,
                "messages": [{"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                    {"type": "text", "text": prompt}
                ]}],
                "temperature": 0.1, "max_tokens": 2048
            }
        headers = {"Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(proxy=None, timeout=60.0) as client:
            resp = await client.post(url, json=body, headers=headers)
            if resp.status_code != 200:
                logger.warning(f"[⚠️] DeepSeek error {resp.status_code}: {resp.text[:150]}")
                return None
            data = resp.json()
            try:
                if is_anthropic:
                    text = "".join(b.get("text", "") for b in data["content"] if b["type"] == "text")
                else:
                    text = data["choices"][0]["message"]["content"]
                return self._parse_json(text)
            except (KeyError, IndexError, TypeError):
                return None

    async def chat(self, prompt: str, max_tokens: int = 4096) -> Optional[str]:
        if not settings.DEEPSEEK_API_KEY:
            return None
        base = settings.DEEPSEEK_BASE_URL.rstrip("/")
        is_anthropic = "anthropic" in base
        if is_anthropic:
            url = f"{base}/messages"
            body = {"model": settings.DEEPSEEK_MODEL, "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]}
        else:
            url = f"{base}/chat/completions"
            body = {"model": settings.DEEPSEEK_MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.1, "max_tokens": max_tokens}
        headers = {"Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(proxy=None, timeout=90.0) as client:
            resp = await client.post(url, json=body, headers=headers)
            if resp.status_code != 200:
                logger.warning(f"[⚠️] DeepSeek chat error {resp.status_code}: {resp.text[:200]}")
                return None
            data = resp.json()
            try:
                if is_anthropic:
                    return "".join(b.get("text", "") for b in data["content"] if b["type"] == "text")
                return data["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError) as e:
                logger.warning(f"[⚠️] DeepSeek parse error: {e}")
                return None

    @staticmethod
    def _parse_json(content: str) -> List[Dict]:
        import re
        content = content.strip()
        content = re.sub(r"```json\s*|```\s*", "", content).strip()
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            m = re.search(r"\[.*\]", content, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(0))
                except json.JSONDecodeError:
                    pass
            return []
