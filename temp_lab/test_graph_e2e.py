"""
产业图谱端到端测试 — 模拟 Step 3 输出 → GraphStore → API 查询
"""
import sys, os, json
sys.path.insert(0, r'E:\workspace\AIResearch\AIStock_Pro\backend')

# 导入 graph 模块
from app.domain.graph.builder import parse_step3
from app.domain.graph.store import GraphStore

# 模拟 Step 3 输出 (精简版)
mock_output = {
    "industry": "人形机器人",
    "supply_chain_map": [
        {
            "level": 1,
            "name": "丝杠/减速器",
            "bottleneck_narrative": "高精度丝杠产能严重不足, 进口设备交期24月+",
            "chokepoint_checklist": {
                "bottleneck_severity": "very_high",
                "is_sole_source": True,
                "customer_switch_cost_months": 18,
            },
            "supply_rigidity": {
                "severity": "extreme",
                "root_cause": "equipment_constraint",
                "expand_cycle": "over_24m",
            },
            "profit_pool": {
                "share_of_industry_profit": "dominant_30_50pct",
                "margin_level": "very_high_above_40pct",
            },
            "competitive_landscape": {
                "structure": "oligopoly_CR3_above_70",
                "global_leaders": ["NSK", "THK"],
                "china_substitution_rate": "below_5pct",
            },
            "value_node_tags": ["高精度丝杠", "行星滚柱丝杠", "国产替代"],
            "sub_processes": [
                {
                    "name": "磨削加工",
                    "supply_rigidity": {"severity": "extreme", "root_cause": "equipment_constraint"},
                    "value_magnitude": {"order_of_magnitude": "1B_10B"},
                    "value_owners": [{"name": "日本精工", "investable_in_a_share": False}],
                    "profit_pool": {"share_of_industry_profit": "significant_15_30pct", "margin_level": "very_high_above_40pct"},
                    "competitive_landscape": {"structure": "monopoly_single_supplier", "pricing_behavior": "collusive_oligopoly", "global_leaders": ["NSK"]},
                    "a_stock_mapping": [{"code": "002747", "name": "埃斯顿", "investment_logic": "国产丝杠替代龙头"}],
                    "value_node_tags": ["磨削设备"],
                }
            ],
        },
        {
            "level": 2,
            "name": "空心杯电机",
            "bottleneck_narrative": "微型精密绕组设备依赖进口",
            "supply_rigidity": {"severity": "very_high", "root_cause": "technology_gap"},
            "profit_pool": {"share_of_industry_profit": "significant_15_30pct", "margin_level": "high_30_40pct"},
            "competitive_landscape": {"structure": "oligopoly_CR3_above_70", "china_substitution_rate": "5_20pct"},
            "sub_processes": [],
        }
    ],
    "scarcity_ranking": [
        {"rank": 1, "segment": "丝杠/减速器", "rigidity_narrative": "产能刚性最大"},
    ],
    "sales_chain": [
        {"segment": "谐波减速器", "value_node_tags": ["谐波"], "reason": "T样阶段先行采购", "lead_months": "1-3"},
    ],
    "expansion_chain": [
        {"segment": "力矩传感器", "value_node_tags": ["传感器"], "reason": "量产后才放量", "lag_months": "6-12"},
    ],
}

# 测试 1: parse_step3
print("=" * 50)
print("Test 1: parse_step3")
nodes, edges = parse_step3(mock_output)
print(f"  Nodes: {len(nodes)}")
for n in nodes:
    print(f"    [{n['node_type']}] {n['label']} (level={n['level']}, severity={n['severity']})")
print(f"  Edges: {len(edges)}")
for e in edges:
    print(f"    {e['edge_type']}: {e['source_id'][:8]}... -> {e['target_id'][:8]}... (w={e['weight']})")

# 测试 2: save to GraphStore
print()
print("Test 2: GraphStore.save_graph")
store = GraphStore()
store.save_graph("test_run_001", "step3_sc_hacker", nodes, edges)
print("  Save OK")

# 测试 3: read from GraphStore
print()
print("Test 3: GraphStore.get_graph")
read_nodes, read_edges = store.get_graph("test_run_001")
print(f"  Read nodes: {len(read_nodes)}")
print(f"  Read edges: {len(read_edges)}")
assert len(read_nodes) == len(nodes), f"Node count mismatch: {len(read_nodes)} vs {len(nodes)}"
assert len(read_edges) == len(edges), f"Edge count mismatch: {len(read_edges)} vs {len(edges)}"
print("  Assertions PASSED")

# 测试 4: list runs
print()
print("Test 4: GraphStore.list_runs")
runs = store.list_runs()
print(f"  Runs: {[r['run_id'] for r in runs]}")
assert any(r['run_id'] == 'test_run_001' for r in runs), "test_run_001 not found"

# 测试 5: nodes by type
print()
print("Test 5: GraphStore.get_nodes_by_type")
stock_nodes = store.get_nodes_by_type("test_run_001", "stock")
print(f"  Stock nodes: {len(stock_nodes)}")
for sn in stock_nodes:
    print(f"    {sn['label']}: {sn['properties'].get('investment_logic', '')[:50]}")

# 清理
store.delete_run("test_run_001")
print()
print("Test 6: Cleanup OK")

print()
print("=" * 50)
print("ALL TESTS PASSED ✅")
