"""LLM输出解析器: text → SignalResult"""
import re, json
from ..base import SignalResult


class Parser:
    @staticmethod
    def parse(text: str, stock_code: str, strategy_name: str) -> SignalResult:
        text = text.strip()
        # 提取JSON
        if "```" in text:
            m = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
            if m: text = m.group(1).strip()
        # 括号计数截断
        if text.startswith("{"):
            depth = 0; end = 0
            for i, ch in enumerate(text):
                if ch == "{": depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0: end = i + 1; break
            if end > 0: text = text[:end]

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return SignalResult.create(stock_code, strategy_name, "ai_chain",
                "HOLD", 0.3, f"LLM输出解析失败: {text[:100]}")

        signal = data.get("signal", "HOLD").upper()
        if signal not in ("BUY", "SELL", "HOLD"):
            signal = "HOLD"
        confidence = min(max(float(data.get("confidence", 0.5)), 0.1), 0.99)
        reasoning = data.get("reasoning", "")[:500]

        return SignalResult.create(stock_code, strategy_name, "ai_chain",
            signal, confidence, reasoning)
