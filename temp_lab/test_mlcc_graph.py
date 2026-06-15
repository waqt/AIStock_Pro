"""MLCC 真实数据端到端测试: 加载 checkpoint → GraphBridge → API 验证"""
import sys, json
sys.path.insert(0, r'E:\workspace\AIResearch\AIStock_Pro\backend')
from app.domain.graph.builder import parse_step3
from app.domain.graph.store import GraphStore

# 1. 加载 MLCC Step 3 checkpoint
with open(r'E:\workspace\AIResearch\AIStock_Pro\backend\data\pipeline_checkpoints\20260527_MLCC_v1\step3_sc_hacker_9c7a3c47dc13.json', encoding='utf-8') as f:
    data = json.load(f)

output = data.get('output', data.get('data', data))
output['run_id'] = 'MLCC_demo'

# 2. 解析并保存
nodes, edges = parse_step3(output)
print(f'MLCC Step3: {len(nodes)} nodes, {len(edges)} edges')
for n in nodes[:8]:
    sp = n.get('properties', {}).get('subtype', '')
    print(f'  [{n["node_type"]}] {n["label"]} lv={n["level"]} sev={n["severity"]}{" BOTTLENECK" if sp=="bottleneck" else ""}')

store = GraphStore()
store.save_graph('MLCC_demo', 'step3_sc_hacker', nodes, edges)

# 3. API 验证
import httpx
r = httpx.get('http://127.0.0.1:8000/api/graph/MLCC_demo')
if r.status_code == 200:
    d = r.json()
    print(f'\nAPI: {len(d["data"]["nodes"])} nodes, {len(d["data"]["edges"])} edges')
else:
    print(f'\nAPI FAILED: {r.status_code} {r.text}')
