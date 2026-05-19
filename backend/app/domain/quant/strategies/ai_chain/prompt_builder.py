"""Prompt构建器: logic_chain + 指标数据 + persona → LLM prompt"""
import json
from decimal import Decimal


class _SafeEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal): return float(o)
        return super().default(o)


class PromptBuilder:
    @staticmethod
    def build(logic_chain: str, persona: str, indicators: dict) -> str:
        # 精简指标数据: 只取最新3个值和关键统计
        slim = {}
        for name, data in indicators.items():
            if isinstance(data, dict):
                slim[name] = {}
                for k, v in data.items():
                    if hasattr(v, 'iloc'):
                        vals = v.dropna().tail(5).tolist()
                        slim[name][k] = {
                            "latest": round(vals[-1], 4) if vals else None,
                            "prev": round(vals[-2], 4) if len(vals) > 1 else None,
                            "trend": "up" if len(vals) >= 3 and vals[-1] > vals[-3] else "down",
                        }
                    elif isinstance(v, (int, float)):
                        slim[name][k] = round(v, 4)

        indicators_json = json.dumps(slim, ensure_ascii=False, indent=2, cls=_SafeEncoder)

        return f"""{persona}

{logic_chain}

## 当前指标数据
```json
{indicators_json}
```

请严格按照上述规则输出纯JSON, 不包含任何解释文字。"""
