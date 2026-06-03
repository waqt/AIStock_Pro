import json, asyncio
from typing import List, Dict, Optional, Literal
import httpx
from app.framework.ai.providers.base import AIProviderProtocol, ChatResult, ToolCall
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
                    text = "".join(b.get("text", "") for b in data["content"] if b["type"] == "text")
                else:
                    text = data["choices"][0]["message"]["content"]
                # ★ 修复 charset 探测错误导致的 mojibake (UTF-8 bytes→Latin-1 解码)
                if text:
                    try:
                        fixed = text.encode('latin-1').decode('utf-8')
                        if any('一' <= c <= '鿿' for c in fixed[:100]):
                            text = fixed
                    except (UnicodeEncodeError, UnicodeDecodeError):
                        pass
                return text
        except httpx.TimeoutException:
            logger.warning(f"[DeepSeek] {resolved_model} timeout ({http_timeout}s) — outer asyncio.wait_for may fire first")
            return None
        except Exception as e:
            logger.error(f"[DeepSeek] {resolved_model} error: {type(e).__name__}: {e}")
            return None

    # ═══ Tool Calling ════════════════════════════

    async def chat_with_tools(
        self,
        prompt: str,
        tools: List[Dict],
        messages: Optional[List[Dict]] = None,
        max_tokens: int = 4096,
        model: Optional[str] = None,
        timeout: int = 240,
    ) -> ChatResult:
        """支持工具调用的对话。

        Args:
            prompt: 用户提示（当 messages=None 时作为单条 user 消息）
            tools: OpenAI/Anthropic 格式的工具定义列表
            messages: 多轮对话历史（含 tool_result 消息）
            max_tokens: 最大输出 token
            model: 模型名（None→flash, 'pro'→pro）

        Returns:
            ChatResult — 包含 content（文本回复）和/或 tool_calls（工具调用请求）
        """
        if not settings.DEEPSEEK_API_KEY:
            return ChatResult(content=None)

        resolved_model, do_thinking = self._resolve_model(model, False)
        base = settings.DEEPSEEK_BASE_URL.rstrip("/")
        is_anthropic = "anthropic" in base
        msgs = messages or [{"role": "user", "content": prompt}]

        if is_anthropic:
            url = f"{base}/messages"
            body = {
                "model": resolved_model,
                "max_tokens": max_tokens,
                "messages": msgs,
                "tools": tools,  # Anthropic tools 格式直接传递
            }
        else:
            url = f"{base}/chat/completions"
            body = {
                "model": resolved_model,
                "messages": msgs,
                "tools": tools,
                "temperature": 0.1,
                "max_tokens": max_tokens,
            }

        headers = {
            "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(proxy=None, timeout=timeout) as client:
                resp = await client.post(url, json=body, headers=headers)
                if resp.status_code != 200:
                    logger.warning(f"[DeepSeek] chat_with_tools HTTP {resp.status_code}: {resp.text[:300]}")
                    return ChatResult(content=None)
                data = resp.json()

                if is_anthropic:
                    return self._parse_anthropic_tools(data)
                else:
                    return self._parse_openai_tools(data)

        except httpx.TimeoutException:
            logger.warning(f"[DeepSeek] chat_with_tools timeout ({timeout}s)")
            return ChatResult(content=None)
        except Exception as e:
            logger.error(f"[DeepSeek] chat_with_tools error: {type(e).__name__}: {e}")
            return ChatResult(content=None)

    @staticmethod
    def _parse_openai_tools(data: dict) -> ChatResult:
        """解析 OpenAI 格式的 tool_calls 响应"""
        try:
            msg = data["choices"][0]["message"]

            # 处理 tool_calls
            tcs_raw = msg.get("tool_calls")
            if tcs_raw:
                tcs = []
                for tc in tcs_raw:
                    args_str = tc["function"]["arguments"]
                    # 尝试修复 mojibake
                    try:
                        fixed = args_str.encode('latin-1').decode('utf-8')
                        if any('一' <= c <= '鿿' for c in fixed[:100]):
                            args_str = fixed
                    except (UnicodeEncodeError, UnicodeDecodeError):
                        pass
                    tcs.append(ToolCall(
                        id=tc["id"],
                        name=tc["function"]["name"],
                        arguments=json.loads(args_str),
                    ))
                return ChatResult(tool_calls=tcs)

            # 纯文本回复
            text = msg.get("content", "")
            if text:
                try:
                    fixed = text.encode('latin-1').decode('utf-8')
                    if any('一' <= c <= '鿿' for c in fixed[:100]):
                        text = fixed
                except (UnicodeEncodeError, UnicodeDecodeError):
                    pass
            return ChatResult(content=text)

        except (KeyError, IndexError, json.JSONDecodeError) as e:
            logger.warning(f"[DeepSeek] parse_openai_tools error: {e}")
            return ChatResult(content=None)

    @staticmethod
    def _parse_anthropic_tools(data: dict) -> ChatResult:
        """解析 Anthropic 格式的 tool_use 响应"""
        try:
            content_blocks = data.get("content", [])
            text_parts = []
            tcs = []

            for block in content_blocks:
                if block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                elif block.get("type") == "tool_use":
                    tcs.append(ToolCall(
                        id=block.get("id", ""),
                        name=block.get("name", ""),
                        arguments=block.get("input", {}),
                    ))

            text = "".join(text_parts)
            if text:
                try:
                    fixed = text.encode('latin-1').decode('utf-8')
                    if any('一' <= c <= '鿿' for c in fixed[:100]):
                        text = fixed
                except (UnicodeEncodeError, UnicodeDecodeError):
                    pass

            return ChatResult(content=text or None, tool_calls=tcs or None)

        except (KeyError, TypeError) as e:
            logger.warning(f"[DeepSeek] parse_anthropic_tools error: {e}")
            return ChatResult(content=None)

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
