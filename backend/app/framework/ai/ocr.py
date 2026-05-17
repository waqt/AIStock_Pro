"""图像处理工具 — base64 清理 + Pillow 压缩"""
import re, io, base64 as b64
from typing import List, Dict
from PIL import Image
from app.framework.logger import logger


def clean_base64(raw: str) -> str:
    """去除 data URI 前缀和非 base64 字符"""
    if "," in raw and "base64" in raw:
        raw = raw.split(",", 1)[1]
    return re.sub(r"[^A-Za-z0-9+/=]", "", raw)


def compress_image(raw_b64: str, max_size: int = 1024, quality: int = 70) -> str:
    """Pillow 压缩图片, 减少 token 消耗"""
    try:
        img_bytes = b64.b64decode(raw_b64)
        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        img.thumbnail((max_size, max_size), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        return b64.b64encode(buf.getvalue()).decode()
    except Exception as e:
        logger.warning(f"[⚠️] Image compression failed: {e}, using original")
        return raw_b64


def extract_json_from_response(content: str) -> List[Dict]:
    """从 AI 响应中提取 JSON 数组 (去除 Markdown 代码块)"""
    content = content.strip()
    content = re.sub(r"```json\s*|```\s*", "", content).strip()
    try:
        import json
        return json.loads(content)
    except json.JSONDecodeError:
        m = re.search(r"\[.*\]", content, re.DOTALL)
        if m:
            try:
                import json
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        logger.warning(f"[⚠️] Failed to parse AI JSON response: {content[:200]}")
        return []
