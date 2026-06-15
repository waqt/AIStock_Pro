"""GraphBuilder — 确定性解析 Pipeline checkpoint → 图谱节点/边

所有解析全从 checkpoint JSON 中提取, 不调用 LLM。
当前已注册解析器:
  - step2_gatekeeper: MarketScanner 行业看门人 → industry根节点 + 传导链
  - step3_sc_hacker: SupplyChainHacker 产业链拆解 → bottleneck链 + 工艺 + 个股
"""
import hashlib
import json
from typing import Dict, Any, List, Tuple
from app.domain.graph.bridge import graph_bridge


def _node_id(run_id: str, prefix: str, name: str) -> str:
    """确定性节点 ID (基于 run_id + prefix + name)"""
    raw = f"{run_id}:{prefix}:{name}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


def _parse_severity(supply_rigidity: dict) -> str:
    """从 supply_rigidity 提取 severity 枚举"""
    if not isinstance(supply_rigidity, dict):
        return ""
    return supply_rigidity.get("severity", "")


def _parse_china_substitution(competitive: dict) -> str:
    """从 competitive_landscape 提取国产替代率"""
    if not isinstance(competitive, dict):
        return ""
    return competitive.get("china_substitution_rate", "")


def parse_step2(output: dict) -> Tuple[List[dict], List[dict]]:
    """解析 MarketScanner V5.10 输出 → (nodes, edges)

    提取:
      - industry → industry 根节点 (紫色, 图谱"源头")
      - propagation.transmission_order[] → 传导链节点 (chain, subtype=transmission)
      - catalysts[] → 催化剂事件节点 (event, 小图标标记)
      - 跨 Step 链接: 连接已有 Step 3 chain 节点到 industry 根
    """
    import json as _json
    nodes = []
    edges = []
    run_id = output.get("run_id", output.get("_run_id", "unknown"))
    industry = output.get("industry", "")

    # ── 1. Industry 根节点 ──
    ind_id = _node_id(run_id, "industry", industry or "unknown")
    nodes.append({
        "id": ind_id,
        "label": industry,
        "node_type": "industry",
        "subtype": "",
        "level": 0,
        "industry": industry,
        "severity": "",
        "properties": {
            "agent": output.get("agent", ""),
            "cycle_phase": output.get("cycle_position", {}).get("phase", ""),
            "prosperity_type": output.get("prosperity", {}).get("type", ""),
            "verdict_rationale": output.get("verdict", {}).get("rationale", ""),
            "entry_decision": output.get("verdict", {}).get("enter_step3"),
            "recommended_path": output.get("_step3_guidance", {}).get("recommended_path", {}),
        },
    })
    prev_id = ind_id

    # ── 2. 传导链节点 (transmission_order) ──
    transmission = output.get("propagation", {}).get("transmission_order", [])
    for t in transmission:
        stage = t.get("stage", 0)
        name = t.get("node", f"stage_{stage}")
        reason = t.get("reason", "")
        nid = _node_id(run_id, "transmission", name)

        # 收集证据摘要
        evidence_list = t.get("evidence", [])
        evidence_summary = [
            {
                "fact": e.get("fact", "")[:200],
                "source": e.get("from", ""),
                "quality": e.get("quality", {}).get("level", ""),
            }
            for e in evidence_list[:3]
        ]

        nodes.append({
            "id": nid,
            "label": name,
            "node_type": "chain",
            "subtype": "transmission",
            "level": stage,
            "industry": industry,
            "severity": "",
            "properties": {
                "stage": stage,
                "reason": reason,
                "evidence": evidence_summary,
                "source": "step2_transmission",
            },
        })
        edges.append({
            "source_id": prev_id,
            "target_id": nid,
            "edge_type": "feeds_to",
            "weight": 1.0,
            "properties": {
                "stage": stage,
                "hierarchy": f"transmission_stage_{stage}",
            },
        })
        prev_id = nid

    # ── 3. 催化剂节点 (catalysts) ──
    for i, cat in enumerate(output.get("catalysts", [])):
        cat_name = cat.get("catalyst", f"catalyst_{i}")
        cat_id = _node_id(run_id, "catalyst", f"{i}_{cat_name[:30]}")
        nodes.append({
            "id": cat_id,
            "label": cat_name[:60],
            "node_type": "event",
            "subtype": cat.get("type", "catalyst"),
            "level": 0,
            "industry": industry,
            "severity": cat.get("status", "pending"),
            "properties": {
                "type": cat.get("type", ""),
                "expected_date": cat.get("expected_date", ""),
                "watch_signal": cat.get("watch_signal", ""),
                "status": cat.get("status", ""),
                "source": "step2_catalyst",
            },
        })
        edges.append({
            "source_id": ind_id,
            "target_id": cat_id,
            "edge_type": "related",
            "weight": 0.5,
            "properties": {"label": "催化剂"},
        })

    # ── 4. 跨 Step 链接: 连接已有 Step 3 chain 节点 ──
    try:
        from app.domain.graph.store import GraphStore
        store = GraphStore()
        s3_nodes, _ = store.get_graph(run_id)
        s3_chains = [n for n in s3_nodes if n.get("step") == "step3_sc_hacker"
                     and n.get("node_type") in ("chain", "process")]
        for cn in s3_chains:
            edges.append({
                "source_id": ind_id,
                "target_id": cn["id"],
                "edge_type": "feeds_to",
                "weight": 0.7,
                "properties": {"hierarchy": "step2→step3", "label": "产业链传导"},
            })
    except Exception:
        pass  # Step 3 数据可能尚未存在

    return nodes, edges


def parse_step3(output: dict) -> Tuple[List[dict], List[dict]]:
    """解析 SupplyChainHacker V5.11b 输出 → (nodes, edges)"""
    nodes = []
    edges = []
    run_id = output.get("run_id", output.get("_run_id", "unknown"))
    supply_chain = output.get("supply_chain_map", [])
    industry = output.get("industry", "")

    seen_nodes = set()
    chain_node_ids = {}

    # ── 1. 每层供应链节点 ──
    for i, node in enumerate(supply_chain):
        name = node.get("name", f"chain_{i}")
        level = node.get("level", i + 1)
        severity = _parse_severity(node.get("supply_rigidity", {}))
        bottleneck = node.get("bottleneck_narrative", "")
        competitive = node.get("competitive_landscape", {})
        profit_pool = node.get("profit_pool", {})
        subst_rate = _parse_china_substitution(competitive)

        nid = _node_id(run_id, "chain", name)
        chain_node_ids[(level, name)] = nid
        if nid in seen_nodes:
            continue
        seen_nodes.add(nid)

        subtype = "bottleneck" if bottleneck else ""
        nodes.append({
            "id": nid,
            "label": name,
            "node_type": "chain",
            "subtype": subtype,
            "level": level,
            "industry": industry,
            "severity": severity,
            "properties": {
                "bottleneck_narrative": bottleneck[:500] if bottleneck else "",
                "supply_rigidity": node.get("supply_rigidity", {}),
                "profit_pool": profit_pool,
                "competitive_landscape": competitive,
                "chokepoint_checklist": node.get("chokepoint_checklist", {}),
                "value_node_tags": node.get("value_node_tags", []),
                "china_substitution_rate": subst_rate,
                "level": level,
            },
        })

        # ── 2. L1→L2→L3→L4 层级关系边 ──
        for prev_level in range(level - 1, 0, -1):
            prev_nid = chain_node_ids.get((prev_level, name))
            if prev_nid:
                edges.append({
                    "source_id": prev_nid,
                    "target_id": nid,
                    "edge_type": "feeds_to",
                    "weight": 1.0,
                    "properties": {"hierarchy": f"L{prev_level}→L{level}"},
                })
                break

        # ── 3. 子工艺节点 (sub_processes) ──
        for sp in node.get("sub_processes", []):
            sp_name = sp.get("name", "")
            if not sp_name:
                continue
            sp_id = _node_id(run_id, "process", sp_name)
            if sp_id in seen_nodes:
                continue
            seen_nodes.add(sp_id)

            sp_severity = _parse_severity(sp.get("supply_rigidity", {}))
            sp_competitive = sp.get("competitive_landscape", {})
            sp_value_mag = sp.get("value_magnitude", {})

            nodes.append({
                "id": sp_id,
                "label": sp_name,
                "node_type": "process",
                "subtype": "bottleneck" if sp_severity in ("extreme", "very_high") else "",
                "level": level * 10,
                "industry": industry,
                "severity": sp_severity,
                "properties": {
                    "supply_rigidity": sp.get("supply_rigidity", {}),
                    "value_magnitude": sp_value_mag,
                    "value_owners": sp.get("value_owners", []),
                    "profit_pool": sp.get("profit_pool", {}),
                    "competitive_landscape": sp_competitive,
                    "value_node_tags": sp.get("value_node_tags", []),
                    "pricing_behavior": sp_competitive.get("pricing_behavior", ""),
                },
            })

            # 子工艺 → 父链 belongs_to
            edges.append({
                "source_id": sp_id,
                "target_id": nid,
                "edge_type": "belongs_to",
                "weight": 1.0,
                "properties": {},
            })

            # 子工艺 A 股映射 → stock 节点
            for am in sp.get("a_stock_mapping", []):
                s_code = am.get("code", "")
                s_name = am.get("name", "")
                if not s_code or not s_name:
                    continue
                stock_id = _node_id(run_id, "stock", s_code)
                if stock_id not in seen_nodes:
                    seen_nodes.add(stock_id)
                    nodes.append({
                        "id": stock_id,
                        "label": f"{s_name}({s_code})",
                        "node_type": "stock",
                        "subtype": "",
                        "level": level * 10 + 1,
                        "industry": industry,
                        "severity": "",
                        "properties": {
                            "code": s_code,
                            "name": s_name,
                            "investment_logic": am.get("investment_logic", ""),
                            "source": "sub_process_mapping",
                        },
                    })
                edges.append({
                    "source_id": stock_id,
                    "target_id": sp_id,
                    "edge_type": "maps_to",
                    "weight": 1.0,
                    "properties": {"logic": am.get("investment_logic", "")},
                })

    # ── 4. scarcity_ranking → 瓶颈节点标记 ──
    for item in output.get("scarcity_ranking", []):
        seg_name = item.get("segment", "")
        if not seg_name:
            continue
        nid = _node_id(run_id, "chain", seg_name)
        if nid in seen_nodes:
            # 追加稀缺信息到已有节点
            for n in nodes:
                if n["id"] == nid:
                    n["properties"]["scarcity_rank"] = item.get("rank")
                    n["properties"]["rigidity_narrative"] = item.get("rigidity_narrative", "")
                    if not n.get("severity"):
                        n["severity"] = "high"

    # ── 5. sales_chain → 传导边 ──
    for item in output.get("sales_chain", []):
        seg = item.get("segment", "")
        if not seg:
            continue
        seg_id = _node_id(run_id, "chain", seg)
        if seg_id in seen_nodes:
            for n in output.get("supply_chain_map", []):
                n_name = n.get("name", "")
                if not n_name:
                    continue
                n_nid = _node_id(run_id, "chain", n_name)
                if n_nid == seg_id:
                    continue
                if n_nid in seen_nodes:
                    edges.append({
                        "source_id": n_nid,
                        "target_id": seg_id,
                        "edge_type": "sales_chain",
                        "weight": float(item.get("lead_months", "1").split("-")[0]) if item.get("lead_months") else 1.0,
                        "properties": {"reason": item.get("reason", ""), "lead_months": item.get("lead_months", "")},
                    })
                    break

    # ── 6. expansion_chain → 滞后传导边 ──
    for item in output.get("expansion_chain", []):
        seg = item.get("segment", "")
        if not seg:
            continue
        seg_id = _node_id(run_id, "chain", seg)
        if seg_id in seen_nodes:
            for n in output.get("supply_chain_map", []):
                n_name = n.get("name", "")
                if not n_name:
                    continue
                n_nid = _node_id(run_id, "chain", n_name)
                if n_nid == seg_id:
                    continue
                if n_nid in seen_nodes:
                    edges.append({
                        "source_id": seg_id,
                        "target_id": n_nid,
                        "edge_type": "expansion_chain",
                        "weight": float(item.get("lag_months", "6").split("-")[0]) if item.get("lag_months") else 1.0,
                        "properties": {"reason": item.get("reason", ""), "lag_months": item.get("lag_months", "")},
                    })
                    break

    # ── 7. 跨 Step 链接: 连接已有 Step 2 节点 ──
    try:
        from app.domain.graph.store import GraphStore
        store = GraphStore()
        s2_nodes, _ = store.get_graph(run_id)
        # 找 Step 2 的 industry 根节点
        ind_nodes = [n for n in s2_nodes if n.get("step") == "step2_gatekeeper"
                     and n.get("node_type") == "industry"]
        if ind_nodes:
            ind_id = ind_nodes[0]["id"]
            for n in nodes:
                if n.get("node_type") in ("chain", "process"):
                    edges.append({
                        "source_id": ind_id,
                        "target_id": n["id"],
                        "edge_type": "feeds_to",
                        "weight": 0.7,
                        "properties": {"hierarchy": "step2→step3", "label": "产业链传导"},
                    })
    except Exception:
        pass

    return nodes, edges


# ── 注册 Step 2 解析器 ──
@graph_bridge.register("step2_gatekeeper")
def _step2_parser(output: dict):
    return parse_step2(output)


# ── 注册 Step 3 解析器 ──
@graph_bridge.register("step3_sc_hacker")
def _step3_parser(output: dict):
    return parse_step3(output)
