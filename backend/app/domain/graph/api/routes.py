"""产业知识图谱 API 端点"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from app.domain.graph.store import GraphStore
from app.domain.graph.bridge import graph_bridge

router = APIRouter(prefix="/api/graph", tags=["graph"])


@router.get("/runs")
async def list_graph_runs():
    """列出有图谱数据的 Pipeline 运行"""
    store = GraphStore()
    runs = store.list_runs()
    return {"success": True, "data": runs}


@router.get("/parsers")
async def list_parsers():
    """查看已注册的 Step 解析器"""
    return {"success": True, "data": graph_bridge.list_parsers()}


@router.get("/{run_id}")
async def get_graph(run_id: str):
    """获取完整图谱数据 (前端 ECharts 格式)"""
    store = GraphStore()
    nodes, edges = store.get_graph(run_id)
    if not nodes:
        raise HTTPException(status_code=404, detail=f"No graph data for run_id={run_id}")
    return {
        "success": True,
        "data": {
            "run_id": run_id,
            "nodes": nodes,
            "edges": edges,
        }
    }


@router.get("/{run_id}/node/{node_id}")
async def get_node_detail(run_id: str, node_id: str):
    """获取节点详情"""
    store = GraphStore()
    node = store.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return {"success": True, "data": node}


@router.get("/{run_id}/nodes/{node_type}")
async def get_nodes_by_type(run_id: str, node_type: str):
    """按类型获取节点列表 (chain/process/stock)"""
    store = GraphStore()
    nodes = store.get_nodes_by_type(run_id, node_type)
    return {"success": True, "data": nodes}


@router.delete("/{run_id}")
async def delete_graph(run_id: str):
    """删除指定 run 的图谱数据"""
    store = GraphStore()
    store.delete_run(run_id)
    return {"success": True, "message": f"Deleted graph data for run_id={run_id}"}
