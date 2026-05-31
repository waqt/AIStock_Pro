import json, asyncio
from typing import List, Dict, Optional, Literal
import httpx
from app.framework.ai.providers.base import AIProviderProtocol
from app.framework.config import settings
from app.framework.logger import logger

# ── LLM 超时默认值 (各 Agent 可按需传入 timeout 覆盖) ──
# flash: 简单任务, 通常 30-90s 内返回
# pro: 复杂推理, 通常 120-300s
TIMEOUT_FLASH = 90   # chat_flash 默认超时 (秒)
TIMEOUT_PRO = 240    # chat_pro 默认超时 (秒)
TIMEOUT_VISION = 90  # vision 超时 (秒)


class DeepSeekProvider(AIProviderProtocol):
    """DeepSeek API — Anthropic 兼容端点, 支持 flash/pro 模型路由 + 思考模式"""

    @property
    def name(self) -> str:
        return "DeepSeek"

    # ═══ 模型路由 ═══════════════════════════════

    @staticmethod
    def _resolve_model(model: Optional[str] = None, thinking: bool = False) -> tuple:
        """解析模型选择: model=None → flash; model='pro' → pro; 可开启thinking"""
        if model == "pro" or model == settings.DEEPSEEK_PRO_MODEL:
            return settings.DEEPSEEK_PRO_MODEL, thinking or settings.DEEPSEEK_THINKING
        if model == "flash" or model == settings.DEEPSEEK_FLASH_MODEL:
            return settings.DEEPSEEK_FLASH_MODEL, False
        if model:
            return model, thinking
        return settings.DEEPSEEK_FLASH_MODEL, False

    # ═══ 便捷方法 ═══════════════════════════════

    async def chat_pro(self, prompt: str, max_tokens: int = 4096,
                       thinking: bool = None, timeout: int = None) -> Optional[str]:
        """投研分析专用: Pro模型 + 思考模式"""
        if thinking is None:
            thinking = settings.DEEPSEEK_THINKING
        t = timeout if timeout is not None else TIMEOUT_PRO
        return await asyncio.wait_for(
            self.chat(prompt, max_tokens=max_tokens, model="pro", thinking=thinking),
            timeout=t)

    async def chat_flash(self, prompt: str, max_tokens: int = 2048,
                         timeout: int = None) -> Optional[str]:
        """轻量任务: Flash模型, 快速便宜"""
        t = timeout if timeout is not None else TIMEOUT_FLASH
        return await asyncio.wait_for(
            self.chat(prompt, max_tokens=max_tokens, model="flash", thinking=False),
            timeout=t)

    # ═══ 核心方法 ═══════════════════════════════

    async def chat(self, prompt: str, max_tokens: int = 4096,
                   model: str = None, thinking: bool = False) -> Optional[str]:
        if not settings.DEEPSEEK_API_KEY:
            return None

        resolved_model, do_thinking = self._resolve_model(model, thinking)
        base = settings.DEEPSEEK_BASE_URL.rstrip("/")
        is_anthropic = "anthropic" in base

        if is_anthropic:
            url = f"{base}/messages"
            body = {
                "model": resolved_model, "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}]
            }
            if do_thinking:
                body["thinking"] = {"type": "enabled"}
        else:
            url = f"{base}/chat/completions"
            body = {
                "model": resolved_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1, "max_tokens": max_tokens,
            }

        headers = {"Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json"}
        # HTTP 客户端超时设为足够大的安全网; 外层 asyncio.wait_for 是有效超时
        http_timeout = 300 if do_thinking else 120

        try:
            async with httpx.AsyncClient(proxy=None, timeout=http_timeout) as client:
                resp = await client.post(url, json=body, headers=headers)
                if resp.status_code != 200:
                    logger.warning(f"[DeepSeek] {resolved_model} HTTP {resp.status_code}: {resp.text[:200]}")
                    return None
                data = resp.json()
                if is_anthropic:
                    return "".join(b.get("text", "") for b in data["content"] if b["type"] == "text")
                return data["choices"][0]["message"]["content"]
        except httpx.TimeoutException:
            logger.warning(f"[DeepSeek] {resolved_model} timeout ({http_timeout}s) — outer asyncio.wait_for may fire first")
            return None
        except Exception as e:
            logger.error(f"[DeepSeek] {resolved_model} error: {type(e).__name__}: {e}")
            return None

    # ═══ Vision (固用 flash) ═══════════════════

    async def vision(self, image_b64: str, prompt: str) -> Optional[List[Dict]]:
        if not settings.DEEPSEEK_API_KEY:
            return None
        base = settings.DEEPSEEK_BASE_URL.rstrip("/")
        is_anthropic = "anthropic" in base
        if is_anthropic:
            url = f"{base}/messages"
            body = {
                "model": settings.DEEPSEEK_FLASH_MODEL, "max_tokens": 2048,
                "messages": [{"role": "user", "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64}},
                    {"type": "text", "text": prompt}
                ]}]
            }
        else:
            url = f"{base}/chat/completions"
            body = {
                "model": settings.DEEPSEEK_FLASH_MODEL,
                "messages": [{"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                    {"type": "text", "text": prompt}
                ]}],
                "temperature": 0.1, "max_tokens": 2048
            }
        headers = {"Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(proxy=None, timeout=TIMEOUT_VISION) as client:
            resp = await client.post(url, json=body, headers=headers)
            if resp.status_code != 200:
                logger.warning(f"[DeepSeek] Vision error {resp.status_code}: {resp.text[:150]}")
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
