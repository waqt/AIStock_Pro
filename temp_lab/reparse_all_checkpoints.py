"""重新解析所有已有 Pipeline checkpoint → 图谱"""
import sys, os, json
sys.path.insert(0, r'E:\workspace\AIResearch\AIStock_Pro\backend')

from app.domain.graph.builder import parse_step2, parse_step3
from app.domain.graph.store import GraphStore

base = r'E:\workspace\AIResearch\AIStock_Pro\backend\data\pipeline_checkpoints'
store = GraphStore()

for d in sorted(os.listdir(base)):
    dpath = os.path.join(base, d)
    if not os.path.isdir(dpath):
        continue

    # 找 Step 2 checkpoint
    step2_files = [f for f in os.listdir(dpath) if f.startswith('step2_gatekeeper') and f.endswith('.json')]
    for sf in step2_files:
        try:
            with open(os.path.join(dpath, sf), encoding='utf-8') as f:
                data = json.load(f)
            output = data.get('output', data)
            output['run_id'] = d  # inject run_id
            nodes, edges = parse_step2(output)
            if nodes:
                store.save_graph(d, 'step2_gatekeeper', nodes, edges)
                print(f'[step2] {d}: {len(nodes)} nodes, {len(edges)} edges')
        except Exception as e:
            print(f'[step2] {d}: FAILED - {e}')

    # 找 Step 3 checkpoint
    step3_files = [f for f in os.listdir(dpath) if f.startswith('step3_sc_hacker_continue') and f.endswith('.json')]
    for sf in step3_files:
        try:
            with open(os.path.join(dpath, sf), encoding='utf-8') as f:
                data = json.load(f)
            output = data.get('output', data)
            output['run_id'] = d
            nodes, edges = parse_step3(output)
            if nodes:
                store.save_graph(d, 'step3_sc_hacker', nodes, edges)
                print(f'[step3] {d}: {len(nodes)} nodes, {len(edges)} edges')
        except Exception as e:
            print(f'[step3] {d}: FAILED - {e}')

print('\nDone. Verifying...')
# 验证
runs = store.list_runs()
for r in runs:
    run_id = r['run_id']
    n, e = store.get_graph(run_id)
    steps = set(x.get('step','') for x in n)
    types = set(x.get('node_type','') for x in n)
    print(f'  {run_id}: {len(n)} nodes, {len(e)} edges, steps={steps}, types={types}')
