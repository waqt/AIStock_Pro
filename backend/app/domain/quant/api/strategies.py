"""策略API — 查询/管理策略库 (含AI链策略编辑)"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/quant/strategies", tags=["Quant-Strategies"])

from app.domain.quant.strategies import STRATEGY_REGISTRY
from app.domain.quant.strategies.ai_chain.engine import AILogicChainEngine


@router.get("")
async def list_strategies():
    """所有注册策略列表 (传统 + AI链)"""
    result = []
    for name, cls in STRATEGY_REGISTRY.items():
        result.append({
            "name": cls.name if hasattr(cls, 'name') else name,
            "description": cls.description if hasattr(cls, 'description') else "",
            "category": cls.category if hasattr(cls, 'category') else "traditional",
            "required_indicators": cls.required_indicators if hasattr(cls, 'required_indicators') else [],
        })
    # 添加AI链定义
    for d in AILogicChainEngine.list_definitions():
        result.append({
            "name": d["name"],
            "description": d["description"],
            "category": "ai_chain",
            "required_indicators": d.get("required_indicators", []),
        })
    return {"success": True, "data": result}


@router.get("/{name}")
async def get_strategy_detail(name: str):
    """策略详情 (AI链策略包含完整logic_chain文本)"""
    # 先查传统
    if name in STRATEGY_REGISTRY:
        cls = STRATEGY_REGISTRY[name]
        return {"success": True, "data": {
            "name": cls.name, "description": cls.description,
            "category": cls.category,
            "required_indicators": cls.required_indicators,
        }}
    # 查AI链
    import yaml, os
    yaml_path = os.path.join(
        os.path.dirname(__file__), "..", "strategies", "ai_chain", "definitions", f"{name}.yaml")
    if os.path.exists(yaml_path):
        with open(yaml_path, "r", encoding="utf-8") as f:
            definition = yaml.safe_load(f)
        return {"success": True, "data": definition}
    raise HTTPException(status_code=404, detail=f"Strategy {name} not found")


class UpdateAIChainRequest(BaseModel):
    logic_chain: str
    persona: Optional[str] = None
    temperature: Optional[float] = None


@router.put("/ai-chain/{name}")
async def update_ai_chain_strategy(name: str, req: UpdateAIChainRequest):
    """编辑AI链策略的logic_chain文本 (热更新)"""
    import yaml, os
    yaml_path = os.path.join(
        os.path.dirname(__file__), "..", "strategies", "ai_chain", "definitions", f"{name}.yaml")
    if not os.path.exists(yaml_path):
        raise HTTPException(status_code=404, detail=f"AI chain strategy {name} not found")
    with open(yaml_path, "r", encoding="utf-8") as f:
        definition = yaml.safe_load(f)
    definition["logic_chain"] = req.logic_chain
    if req.persona: definition["persona"] = req.persona
    if req.temperature is not None: definition["temperature"] = req.temperature
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(definition, f, allow_unicode=True, default_flow_style=False)
    return {"success": True, "message": f"Updated {name}"}
