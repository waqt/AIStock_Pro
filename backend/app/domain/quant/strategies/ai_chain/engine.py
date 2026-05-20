"""AI链执行引擎 — 加载YAML定义 → 获取指标 → 构建Prompt → LLM → 解析"""
import yaml, os
from ..base import SignalResult
from .prompt_builder import PromptBuilder
from .parser import Parser


DEFINITIONS_DIR = os.path.join(os.path.dirname(__file__), "definitions")


class AILogicChainEngine:
    def __init__(self, provider, definition_name: str):
        yaml_path = os.path.join(DEFINITIONS_DIR, f"{definition_name}.yaml")
        if not os.path.exists(yaml_path):
            raise FileNotFoundError(f"AI chain definition not found: {yaml_path}")
        with open(yaml_path, "r", encoding="utf-8") as f:
            self.definition = yaml.safe_load(f)
        self.provider = provider
        self.name = self.definition.get("name", definition_name)

    async def execute(self, stock_code: str, indicators: dict) -> SignalResult:
        prompt = PromptBuilder.build(
            logic_chain=self.definition.get("logic_chain", ""),
            persona=self.definition.get("persona", ""),
            indicators=indicators,
        )
        text = await self.provider.chat_pro(
            prompt, max_tokens=512)
        if not text:
            return SignalResult.create(stock_code, self.name, "ai_chain",
                "HOLD", 0.3, "LLM无响应")
        return Parser.parse(text, stock_code, self.name)

    @staticmethod
    def list_definitions() -> list:
        defs = []
        if not os.path.isdir(DEFINITIONS_DIR):
            return defs
        for fn in sorted(os.listdir(DEFINITIONS_DIR)):
            if fn.endswith(".yaml"):
                try:
                    with open(os.path.join(DEFINITIONS_DIR, fn), "r", encoding="utf-8") as f:
                        d = yaml.safe_load(f)
                    defs.append({
                        "name": d.get("name", fn.replace(".yaml", "")),
                        "description": d.get("description", ""),
                        "persona": d.get("persona", ""),
                        "required_indicators": d.get("required_indicators", []),
                    })
                except Exception:
                    pass
        return defs
