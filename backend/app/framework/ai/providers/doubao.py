import json
from typing import List, Dict, Optional
import httpx
from app.framework.ai.providers.base import AIProviderProtocol
from app.framework.config import settings
from app.framework.logger import logger


class DoubaoProvider(AIProviderProtocol):
    """豆包 Seed API — 国内直连"""

    @property
    def name(self) -> str:
        return "Doubao"

    async def vision(self, image_b64: str, prompt: str) -> Optional[List[Dict]]:
        if not settings.DOUBAO_API_KEY:
            return None
        logger.info(f"[+] Calling Doubao (image: {len(image_b64)//1024}KB, model: {settings.DOUBAO_MODEL})...")
        url = f"{settings.DOUBAO_BASE_URL.rstrip('/')}/responses"
        body = {
            "model": settings.DOUBAO_MODEL,
            "input": [{
                "role": "user",
                "content": [
                    {"type": "input_image", "image_url": f"data:image/jpeg;base64,{image_b64}"},
                    {"type": "input_text", "text": prompt}
                ]
            }]
        }
        headers = {"Authorization": f"Bearer {settings.DOUBAO_API_KEY}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(proxy=None, timeout=90.0) as client:
            resp = await client.post(url, json=body, headers=headers)
            if resp.status_code != 200:
                logger.warning(f"[⚠️] Doubao error {resp.status_code}: {resp.text[:200]}")
                return None
            text = self._extract_text(resp.json())
            return self._parse_json(text) if text else None

    async def chat(self, prompt: str) -> Optional[str]:
        return None  # 豆包 chat 待实现

    @staticmethod
    def _extract_text(data: dict) -> str:
        if "output" in data:
            output = data["output"]
            if isinstance(output, list):
                for item in output:
                    if isinstance(item, dict):
                        content = item.get("content", [])
                        if isinstance(content, list):
                            for block in content:
                                if isinstance(block, dict) and block.get("type") == "output_text":
                                    return block.get("text", "")
                        elif isinstance(content, str):
                            return content
                        if "text" in item:
                            return item["text"]
            elif isinstance(output, str):
                return output
        if "choices" in data:
            try:
                return data["choices"][0]["message"].get("content", "")
            except (IndexError, KeyError):
                pass
        if "output_text" in data:
            return data["output_text"]
        return ""

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
