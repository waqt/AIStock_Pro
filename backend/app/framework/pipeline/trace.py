"""
TraceContext — Agent 执行期证据链路收集器
每个 Agent 实例化一个上下文, 记录所有搜索+LLM调用, 最终写入 .trace.txt
"""
import time
from datetime import datetime
from app.framework.pipeline.checkpoint import save_trace


class TraceContext:
    """在 agent 执行期间收集搜索/LLM 调用证据"""

    def __init__(self, run_id: str):
        self.run_id = run_id
        self.events: list = []
        self._t0 = time.time()

    def record_search(self, query: str, results: list):
        """记录一次 web 搜索"""
        self.events.append({
            "type": "search",
            "ts": datetime.now().isoformat(),
            "query": query,
            "result_count": len(results),
            "results": [
                {"title": r.get("title", "")[:200],
                 "snippet": r.get("snippet", "")[:300],
                 "url": r.get("url", "")}
                for r in results[:5]
            ],
        })

    def record_llm(self, prompt: str, response: str, model: str = ""):
        """记录一次 LLM 调用"""
        self.events.append({
            "type": "llm",
            "ts": datetime.now().isoformat(),
            "model": model,
            "prompt": prompt[:8000],       # 截断, 确保可读但不过大
            "response": response[:4000],
        })

    def record_db(self, query: str, row_count: int):
        """记录一次 DB 查询"""
        self.events.append({
            "type": "db",
            "ts": datetime.now().isoformat(),
            "query": query[:500],
            "row_count": row_count,
        })

    def record_note(self, key: str, value: str):
        """记录关键判断或中间结论"""
        self.events.append({
            "type": "note",
            "ts": datetime.now().isoformat(),
            "key": key,
            "value": value[:2000],
        })

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "started_at": datetime.fromtimestamp(self._t0).isoformat(),
            "elapsed_seconds": round(time.time() - self._t0, 1),
            "event_count": len(self.events),
            "events": self.events,
        }

    def write(self, step: str) -> str:
        """落盘 .trace.txt"""
        return save_trace(self.run_id, step, self.to_dict())
