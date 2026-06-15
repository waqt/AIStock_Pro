"""端到端测试: 加载真实 Step 3 checkpoint → 构建图谱 → API 查询"""
import sys, json
sys.path.insert(0, r'E:\workspace\AIResearch\AIStock_Pro\backend')
from app.domain.graph.builder import parse_step3
from app.domain.graph.store import GraphStore

runs = [
    ("20260527_人工智能应用_v1", "step3_sc_hacker_continue.json"),
    ("20260529_STT固态变压器_v1", "step3_sc_hacker_continue.json"),
    ("20260608_物理AI_v1", "step3_sc_hacker_continue.json"),
]

base = r'E:\workspace\AIResearch\AIStock_Pro\backend\data\pipeline_checkpoints'

for run_dir, checkpoint_file in runs:
    check_path = f'{base}/{run_dir}/{checkpoint_file}'
    try:
        with open(check_path, encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"  SKIP: {run_dir} / {checkpoint_file} not found")
        continue

    output = data.get("output", data)
    output["run_id"] = run_dir

    nodes, edges = parse_step3(output)
    print(f"\n{run_dir}:")
    print(f"  Nodes: {len(nodes)}  Edges: {len(edges)}")

    if nodes:
        store = GraphStore()
        store.save_graph(run_dir, "step3_sc_hacker", nodes, edges)
        print(f"  Saved to graph.db ✓")

        # 统计节点类型
        from collections import Counter
        type_counts = Counter(n["node_type"] for n in nodes)
        print(f"  Types: {dict(type_counts)}")

        # 瓶颈节点
        bottlenecks = [n for n in nodes if n.get("subtype") == "bottleneck"]
        if bottlenecks:
            print(f"  Bottlenecks: {[n['label'] for n in bottlenecks]}")

        # severity 最高的
        sev_map = {"extreme": 0, "very_high": 1, "high": 2}
        severe = [n for n in nodes if n.get("severity") in sev_map and n["node_type"] != "stock"]
        severe.sort(key=lambda n: sev_map.get(n.get("severity", ""), 99))
        if severe:
            top = severe[:3]
            print(f"  Most severe: {[(n['label'], n['severity']) for n in top]}")

print("\nDone. Open browser at http://127.0.0.1:8000/graph.html to view graphs")
