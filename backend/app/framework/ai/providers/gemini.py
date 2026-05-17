import json
from typing import List, Dict, Optional
import httpx
from app.framework.ai.providers.base import AIProviderProtocol
from app.framework.config import settings
from app.framework.logger import logger


class GeminiProvider(AIProviderProtocol):
    """Gemini Vision API — 需 VPN"""

    @property
    def name(self) -> str:
        return "Gemini"

    async def vision(self, image_b64: str, prompt: str) -> Optional[List[Dict]]:
        if not settings.GEMINI_API_KEY:
            return None
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{settings.GEMINI_MODEL}:generateContent?key={settings.GEMINI_API_KEY}"
        )
        body = {
            "contents": [{"parts": [
                {"text": prompt},
                {"inlineData": {"mimeType": "image/jpeg", "data": image_b64}}
            ]}],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 2048}
        }
        proxy = settings.HTTPS_PROXY or settings.HTTP_PROXY or None
        async with httpx.AsyncClient(proxy=proxy, timeout=60.0) as client:
            resp = await client.post(url, json=body)
            if resp.status_code != 200:
                logger.error(f"[❌] Gemini error {resp.status_code}: {resp.text[:200]}")
                return None
            data = resp.json()
            try:
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                return self._parse_json(text)
            except (KeyError, IndexError):
                return None

    async def chat(self, prompt: str) -> Optional[str]:
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
