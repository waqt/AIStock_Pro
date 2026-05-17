"""
AI 持仓/交易识别与导入服务 V2.0
支持: 截图 OCR (Gemini Vision → 豆包 → DeepSeek) + 文本解析 + Excel 导入
"""
import json, re, io, os, base64 as b64
from typing import List, Dict, Any, Optional
from datetime import date, datetime
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import httpx
from PIL import Image
from app.core.logger import logger
from app.core.config import settings, BASE_DIR

CACHE_FILE = os.path.join(BASE_DIR, "import_cache.json")


class AIImportService:
    """AI 导入服务 — 截图识别 + 文本解析 + Excel 解析 + 批量写库"""

    # ── Prompts ──────────────────────────────────

    POSITION_PROMPT = """你是一个股票持仓数据提取助手。请从截图中提取所有持仓明细。
注意区分：成本价（买入均价/持仓成本）和 现价（当前价格/最新价）。
返回纯 JSON 数组（不要 Markdown 代码块），每条记录包含：
- stock_code: 股票代码（纯数字字符串，如"600519"）
- stock_name: 股票名称
- shares: 持仓数量（整数）
- cost_price: 成本价/持仓成本/买入均价（浮点数，如果截图中无此字段则填0）
- current_price: 现价/最新价/当前价格（浮点数）
示例：[{"stock_code":"600519","stock_name":"贵州茅台","shares":100,"cost_price":1750.00,"current_price":1820.50}]"""

    TRADE_PROMPT = """你是一个股票交易记录提取助手。请从截图中提取所有交易明细。
返回纯 JSON 数组（不要 Markdown 代码块），每条记录包含：
- stock_code: 股票代码（纯数字字符串）
- stock_name: 股票名称
- trade_type: 交易类型（"BUY"=买入, "SELL"=卖出）
- shares: 交易数量（整数）
- price: 成交价格（浮点数）
- trade_date: 交易日期（格式 YYYY-MM-DD）
示例：[{"stock_code":"600519","stock_name":"贵州茅台","trade_type":"BUY","shares":100,"price":1800.00,"trade_date":"2026-03-15"}]"""

    # ── Cache ────────────────────────────────────

    @classmethod
    def clear_cache(cls):
        if os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)
            logger.info("[🧹] Import cache cleared")

    @classmethod
    def get_cache(cls) -> Optional[Dict]:
        if not os.path.exists(CACHE_FILE):
            return None
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    @classmethod
    def _save_cache(cls, data: List[Dict], cache_type: str):
        try:
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump({"type": cache_type, "data": data}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"[⚠️] Failed to save import cache: {e}")

    # ── Image Processing ─────────────────────────

    @staticmethod
    def _clean_base64(raw: str) -> str:
        """去除 data URI 前缀和非 base64 字符"""
        if "," in raw and "base64" in raw:
            raw = raw.split(",", 1)[1]
        return re.sub(r"[^A-Za-z0-9+/=]", "", raw)

    @staticmethod
    def _compress_image(raw_b64: str, max_size: int = 1024, quality: int = 70) -> str:
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

    @staticmethod
    def _extract_json(content: str) -> List[Dict]:
        """从 AI 响应中提取 JSON 数组"""
        content = content.strip()
        # 去除 Markdown 代码块
        content = re.sub(r"```json\s*|```\s*", "", content)
        content = content.strip()
        # 尝试提取第一个 JSON 数组
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            m = re.search(r"\[.*\]", content, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(0))
                except json.JSONDecodeError:
                    pass
            logger.warning(f"[⚠️] Failed to parse AI JSON response: {content[:200]}")
            return []

    # ── AI Provider Calls (async) ────────────────

    @classmethod
    async def _call_gemini_vision(cls, image_b64: str, prompt: str) -> Optional[List[Dict]]:
        """Gemini Vision API — 主 OCR 引擎"""
        if not settings.GEMINI_API_KEY:
            return None
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{settings.GEMINI_MODEL}:generateContent?key={settings.GEMINI_API_KEY}"
        )
        body = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {"inlineData": {"mimeType": "image/jpeg", "data": image_b64}}
                ]
            }],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 2048}
        }
        # 代理支持
        proxy = settings.HTTPS_PROXY or settings.HTTP_PROXY or None
        async with httpx.AsyncClient(proxy=proxy, timeout=60.0) as client:
            resp = await client.post(url, json=body)
            if resp.status_code != 200:
                logger.error(f"[❌] Gemini API error {resp.status_code}: {resp.text[:200]}")
                return None
            data = resp.json()
            try:
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                return cls._extract_json(text)
            except (KeyError, IndexError):
                logger.error(f"[❌] Unexpected Gemini response: {json.dumps(data)[:300]}")
                return None

    @classmethod
    async def _call_doubao_vision(cls, image_b64: str, prompt: str) -> Optional[List[Dict]]:
        """豆包 Seed API — 主 OCR 引擎 (国内直连)"""
        if not settings.DOUBAO_API_KEY:
            return None
        logger.info(f"[+] Calling Doubao API (image: {len(image_b64)//1024}KB, model: {settings.DOUBAO_MODEL})...")
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
        headers = {
            "Authorization": f"Bearer {settings.DOUBAO_API_KEY}",
            "Content-Type": "application/json"
        }
        async with httpx.AsyncClient(proxy=None, timeout=90.0) as client:
            resp = await client.post(url, json=body, headers=headers)
            if resp.status_code != 200:
                logger.warning(f"[⚠️] Doubao API error {resp.status_code}: {resp.text[:200]}")
                return None
            data = resp.json()
            text = cls._extract_doubao_text(data)
            if not text:
                logger.warning("[⚠️] Doubao returned empty text content")
                return None
            return cls._extract_json(text)

    @staticmethod
    def _extract_doubao_text(data: dict) -> str:
        """从豆包 Responses API 返回中提取文本 (级联回退)"""
        # 1. Responses API 格式: output[] -> content[] -> type=output_text
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
        # 2. 兼容 OpenAI Chat 格式
        if "choices" in data:
            try:
                return data["choices"][0]["message"].get("content", "")
            except (IndexError, KeyError):
                pass
        # 3. 顶层 output_text 兜底
        if "output_text" in data:
            return data["output_text"]
        return ""

    @classmethod
    async def _call_deepseek_vision(cls, image_b64: str, prompt: str) -> Optional[List[Dict]]:
        """DeepSeek Vision — Anthropic 兼容端点, 支持图片输入"""
        if not settings.DEEPSEEK_API_KEY:
            return None
        base = settings.DEEPSEEK_BASE_URL.rstrip("/")
        if "anthropic" in base:
            # Anthropic Messages 格式
            url = f"{base}/messages"
            body = {
                "model": settings.DEEPSEEK_MODEL,
                "max_tokens": 2048,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64}},
                        {"type": "text", "text": prompt}
                    ]
                }]
            }
        else:
            # OpenAI Chat 格式 (fallback)
            url = f"{base}/chat/completions"
            body = {
                "model": settings.DEEPSEEK_MODEL,
                "messages": [{"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                    {"type": "text", "text": prompt}
                ]}],
                "temperature": 0.1,
                "max_tokens": 2048
            }
        headers = {
            "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }
        async with httpx.AsyncClient(proxy=None, timeout=60.0) as client:
            resp = await client.post(url, json=body, headers=headers)
            if resp.status_code != 200:
                logger.warning(f"[⚠️] DeepSeek Vision error {resp.status_code}: {resp.text[:150]}")
                return None
            data = resp.json()
            try:
                if "anthropic" in base:
                    text = "".join(b.get("text", "") for b in data["content"] if b["type"] == "text")
                else:
                    text = data["choices"][0]["message"]["content"]
                return cls._extract_json(text)
            except (KeyError, IndexError, TypeError) as e:
                logger.warning(f"[⚠️] DeepSeek Vision parse error: {e}")
                return None

    @classmethod
    async def _call_deepseek_text(cls, prompt: str) -> Optional[List[Dict]]:
        """DeepSeek 文本模式 — 用于文本提示的结构化提取"""
        if not settings.DEEPSEEK_API_KEY:
            return None
        base = settings.DEEPSEEK_BASE_URL.rstrip("/")
        if "anthropic" in base:
            url = f"{base}/messages"
            body = {
                "model": settings.DEEPSEEK_MODEL,
                "max_tokens": 2048,
                "messages": [{"role": "user", "content": prompt}]
            }
        else:
            url = f"{base}/chat/completions"
            body = {
                "model": settings.DEEPSEEK_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 2048
            }
        headers = {
            "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }
        async with httpx.AsyncClient(proxy=None, timeout=60.0) as client:
            resp = await client.post(url, json=body, headers=headers)
            if resp.status_code != 200:
                logger.warning(f"[⚠️] DeepSeek API error {resp.status_code}: {resp.text[:150]}")
                return None
            data = resp.json()
            try:
                if "anthropic" in base:
                    text = "".join(b.get("text", "") for b in data["content"] if b["type"] == "text")
                else:
                    text = data["choices"][0]["message"]["content"]
                return cls._extract_json(text)
            except (KeyError, IndexError, TypeError):
                return None

    # ── Public Recognition Methods ───────────────

    @classmethod
    async def recognize_stock_image(cls, image_base64: str) -> List[Dict]:
        """识别持仓截图: 豆包 → DeepSeek → Gemini"""
        b64_clean = cls._clean_base64(image_base64)
        logger.info(f"[+] Image cleaned, size: {len(b64_clean)//1024}KB")
        b64_compressed = cls._compress_image(b64_clean)
        logger.info(f"[+] Image compressed: {len(b64_compressed)//1024}KB")

        # 1. 豆包 (primary, 国内直连)
        import time; t0 = time.time()
        result = await cls._call_doubao_vision(b64_compressed, cls.POSITION_PROMPT)
        if result:
            cls._save_cache(result, "position")
            logger.info(f"[✅] Doubao recognized {len(result)} positions in {time.time()-t0:.1f}s")
            return result
        logger.warning(f"[⚠️] Doubao failed ({time.time()-t0:.1f}s), trying DeepSeek...")

        # 2. DeepSeek Vision (fallback)
        t0 = time.time()
        result = await cls._call_deepseek_vision(b64_compressed, cls.POSITION_PROMPT)
        if result:
            cls._save_cache(result, "position")
            logger.info(f"[✅] DeepSeek recognized {len(result)} positions in {time.time()-t0:.1f}s")
            return result
        logger.warning(f"[⚠️] DeepSeek failed ({time.time()-t0:.1f}s), trying Gemini...")

        # 3. Gemini (需 VPN, 最后兜底)
        result = await cls._call_gemini_vision(b64_compressed, cls.POSITION_PROMPT)
        if result:
            cls._save_cache(result, "position")
            logger.info(f"[✅] Gemini recognized {len(result)} positions")
            return result

        logger.error("[❌] All AI providers failed for position recognition")
        return []

    @classmethod
    async def recognize_trade_image(cls, image_base64: str) -> List[Dict]:
        """识别交易截图: 豆包 → DeepSeek → Gemini"""
        b64_clean = cls._clean_base64(image_base64)
        b64_compressed = cls._compress_image(b64_clean)

        result = await cls._call_doubao_vision(b64_compressed, cls.TRADE_PROMPT)
        if result:
            cls._save_cache(result, "trade")
            logger.info(f"[✅] Doubao recognized {len(result)} trades")
            return result

        logger.warning("[⚠️] Doubao failed, trying DeepSeek...")
        result = await cls._call_deepseek_vision(b64_compressed, cls.TRADE_PROMPT)
        if result:
            cls._save_cache(result, "trade")
            logger.info(f"[✅] DeepSeek recognized {len(result)} trades")
            return result

        logger.warning("[⚠️] DeepSeek failed, trying Gemini...")
        result = await cls._call_gemini_vision(b64_compressed, cls.TRADE_PROMPT)
        if result:
            cls._save_cache(result, "trade")
            return result

        logger.error("[❌] All AI providers failed for trade recognition")
        return []

    # ── Text Parsing ─────────────────────────────

    @staticmethod
    def parse_raw_text(text: str) -> List[Dict]:
        """规则解析文本: code stock_name shares [price]"""
        results = []
        for line in text.strip().split("\n"):
            line = line.strip()
            if not line or "代码" in line or "股票" in line:
                continue
            # 支持 tab / 逗号(中英) / 空格分割
            parts = re.split(r"[\t,，\s]+", line)
            parts = [p.strip() for p in parts if p.strip()]
            if len(parts) < 3:
                continue
            item = {
                "stock_code": parts[0].replace("\"", "").replace("'", ""),
                "stock_name": parts[1],
                "shares": int(float(parts[2].replace(",", ""))) if parts[2] else 0,
            }
            if len(parts) >= 4:
                item["cost_price"] = float(parts[3].replace(",", "").replace("¥", ""))
            else:
                item["cost_price"] = 0.0
            item["current_price"] = item.get("cost_price", 0.0)
            results.append(item)
        return results

    # ── Excel Parsing ────────────────────────────

    _COLUMN_MAP_POSITION = {
        "stock_code": ["股票代码", "代码", "code", "stock_code", "symbol"],
        "stock_name": ["股票名称", "名称", "name", "stock_name", "证券名称"],
        "shares": ["持仓数量", "数量", "shares", "volume", "股数", "持仓"],
        "cost_price": ["成本价", "持仓成本", "买入均价", "cost_price", "avg_cost", "成本"],
        "current_price": ["现价", "最新价", "当前价", "current_price", "price", "市价"],
    }

    _COLUMN_MAP_TRADE = {
        "stock_code": ["股票代码", "代码", "code", "stock_code", "symbol"],
        "stock_name": ["股票名称", "名称", "name", "stock_name", "证券名称"],
        "trade_type": ["交易类型", "买卖", "trade_type", "action", "方向", "操作"],
        "shares": ["交易数量", "数量", "shares", "volume", "股数"],
        "price": ["成交价", "价格", "price", "成交价格"],
        "trade_date": ["交易日期", "日期", "trade_date", "date", "成交日期"],
    }

    @classmethod
    def parse_excel(cls, file_bytes: bytes, filename: str, sheet_type: str = "position") -> List[Dict]:
        """解析 Excel 文件, 灵活匹配列名"""
        import pandas as pd
        try:
            df = pd.read_excel(io.BytesIO(file_bytes), engine="openpyxl")
        except Exception:
            df = pd.read_excel(io.BytesIO(file_bytes))  # fallback

        if df.empty or len(df.columns) == 0:
            return []

        # 列名映射
        col_map = cls._COLUMN_MAP_POSITION if sheet_type == "position" else cls._COLUMN_MAP_TRADE
        header = {}
        for i, col_name in enumerate(df.columns):
            col_lower = str(col_name).strip().lower()
            for target, aliases in col_map.items():
                if col_lower in aliases or col_lower in [a.lower() for a in aliases]:
                    header[target] = i
                    break

        if "stock_code" not in header:
            return []  # 找不到股票代码列则返回空

        results = []
        for _, row in df.iterrows():
            try:
                item = {}
                for field, idx in header.items():
                    val = row.iloc[idx]
                    if pd.isna(val):
                        val = 0 if field in ("shares", "cost_price", "current_price", "price") else ""
                    item[field] = val
                # 类型转换
                item["stock_code"] = str(item["stock_code"]).zfill(5) if len(str(item["stock_code"])) <= 5 else str(item["stock_code"])
                item["stock_name"] = str(item.get("stock_name", ""))
                item["shares"] = int(float(item.get("shares", 0))) if item.get("shares") else 0
                if sheet_type == "position":
                    item["cost_price"] = float(item.get("cost_price", 0)) if item.get("cost_price") else 0.0
                    item["current_price"] = float(item.get("current_price", 0)) if item.get("current_price") else item.get("cost_price", 0.0)
                else:
                    item["price"] = float(item.get("price", 0)) if item.get("price") else 0.0
                    tt = str(item.get("trade_type", "")).upper()
                    item["trade_type"] = "BUY" if "买" in tt or "BUY" in tt else "SELL"
                    if item.get("trade_date"):
                        item["trade_date"] = str(item["trade_date"])[:10]
                results.append(item)
            except Exception as e:
                logger.warning(f"[⚠️] Excel row parse error: {e}")
        return results

    # ── Batch Import to DB ──────────────────────

    @classmethod
    async def batch_import_positions(cls, db: AsyncSession, items: List[Dict], clear_old: bool = False) -> Dict:
        from app.models.models import Position, MarketData
        cleared = 0

        if clear_old:
            res = await db.execute(select(Position))
            old = res.scalars().all()
            cleared = len(old)
            await db.execute(delete(Position).execution_options(synchronize_session='fetch'))
            await db.flush()

        # 预加载所有行情最新价，用于修正导入数据中的现价
        price_map = {}
        mkt_res = await db.execute(
            select(MarketData.stock_code, MarketData.close, MarketData.trade_date)
            .order_by(MarketData.trade_date.desc())
        )
        seen = set()
        for row in mkt_res:
            if row.stock_code not in seen:
                price_map[row.stock_code] = row.close
                seen.add(row.stock_code)

        imported = 0
        skipped = 0
        for item in items:
            try:
                code = str(item.get("stock_code", "")).strip()
                if not code:
                    continue
                name = item.get("stock_name", "")
                shares = int(float(item.get("shares", 0))) if item.get("shares") else 0
                cost = float(item.get("cost_price", item.get("price", 0))) if item.get("cost_price", item.get("price")) else 0.0
                # 优先用行情真实价格，AI 返回的截图现价仅作兜底
                current = price_map.get(code, float(item.get("current_price", cost) or cost))

                if shares <= 0:
                    logger.warning(f"[⚠️] {code}: shares=0, skipping")
                    skipped += 1
                    continue
                if cost <= 0 and current > 0:
                    cost = current
                if current <= 0 and cost > 0:
                    current = cost

                mv = shares * current
                pl = mv - (shares * cost)
                plr = (pl / (shares * cost) * 100) if (shares * cost) > 0 else 0.0

                # Upsert: 必须先 flush 确保 identity map 中没有待处理的旧对象
                await db.flush()
                res = await db.execute(select(Position).where(Position.stock_code == code))
                existing = res.scalars().first()
                if existing:
                    existing.stock_name = name or existing.stock_name
                    existing.volume = shares
                    existing.avg_cost = cost
                    existing.current_price = current
                    existing.market_value = mv
                    existing.profit_loss = pl
                    existing.profit_loss_ratio = plr
                    existing.first_buy_date = date.today() if not existing.first_buy_date else existing.first_buy_date
                    existing.updated_at = datetime.now()
                    logger.info(f"[+] Updated: {code} {name} vol={shares} cost={cost} price={current}")
                else:
                    db.add(Position(
                        stock_code=code, stock_name=name,
                        volume=shares, avg_cost=cost, current_price=current,
                        market_value=mv, profit_loss=pl, profit_loss_ratio=plr,
                        first_buy_date=date.today()
                    ))
                    logger.info(f"[+] Inserted: {code} {name} vol={shares} cost={cost} price={current}")
                imported += 1
            except Exception as e:
                logger.warning(f"[⚠️] Import position {item.get('stock_code', '?')} error: {e}")

        await db.commit()
        logger.info(f"[✅] Import: {imported} positions (cleared {cleared} old, skipped {skipped})")
        return {"success": True, "imported_count": imported, "cleared_count": cleared, "errors": []}

    @classmethod
    async def batch_import_trades(cls, db: AsyncSession, items: List[Dict]) -> Dict:
        from app.models.models import TradeHistory
        imported = 0

        for item in items:
            try:
                code = str(item.get("stock_code", "")).strip()
                if not code:
                    continue
                name = item.get("stock_name", "")
                shares = int(float(item.get("shares", 0))) if item.get("shares") else 0
                price = float(item.get("price", 0)) if item.get("price") else 0.0

                # 交易类型: 买/促 → BUY, else SELL
                tt = str(item.get("trade_type", "BUY")).upper()
                action = "BUY" if ("买" in tt or "促" in tt or "BUY" in tt) else "SELL"

                # 日期解析
                trade_date = datetime.now()
                date_str = str(item.get("trade_date", ""))[:10]
                if date_str:
                    for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"]:
                        try:
                            trade_date = datetime.strptime(date_str, fmt)
                            break
                        except ValueError:
                            continue

                amount = shares * price
                commission = max(amount * 0.0003, 5.0)
                stamp_tax = amount * 0.001 if action == "SELL" else 0.0

                db.add(TradeHistory(
                    stock_code=code, action=action, price=price,
                    volume=shares, amount=amount, commission=commission,
                    stamp_tax=stamp_tax, trade_date=trade_date,
                    strategy_id="AI_IMPORT", notes="AI 导入"
                ))
                imported += 1
            except Exception as e:
                logger.warning(f"[⚠️] Import trade {item.get('stock_code', '?')} error: {e}")

        await db.commit()
        logger.info(f"[✅] Import: {imported} trades")
        return {"success": True, "imported_count": imported, "cleared_count": 0, "errors": []}
