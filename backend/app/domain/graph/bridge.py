"""GraphBridge — 最小耦合 Pipeline → 图谱集成点"""
from typing import Callable, Dict, Any, Tuple, List
from app.framework.logger import logger


class GraphBridge:
    """每个 Step 只需加一行 graph_bridge.notify(run_id, step, output)"""

    def __init__(self):
        self._parsers: Dict[str, Callable] = {}

    def register(self, step: str):
        """装饰器: 注册某个 Step 的解析器"""
        def wrapper(fn: Callable):
            self._parsers[step] = fn
            logger.info(f"[GraphBridge] Registered parser: {step}")
            return fn
        return wrapper

    async def notify(self, run_id: str, step: str, output: dict):
        """Pipeline 中调用 — 只这一行"""
        parser = self._parsers.get(step)
        if not parser:
            return  # 未注册的 step 静默跳过
        try:
            nodes, edges = parser(output)
            if nodes:
                from app.domain.graph.store import GraphStore
                GraphStore().save_graph(run_id, step, nodes, edges)
                logger.info(f"[GraphBridge] {run_id}/{step}: {len(nodes)} nodes, {len(edges)} edges")
        except Exception as e:
            logger.warning(f"[GraphBridge] {run_id}/{step} parse failed: {e}")

    def list_parsers(self) -> List[str]:
        return list(self._parsers.keys())


graph_bridge = GraphBridge()  # 单例
