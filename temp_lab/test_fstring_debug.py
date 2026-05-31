"""诊断: 测试 SystemDynamicsAgent._build_prompt 的 f-string 是否能正常执行"""
import os, sys, json, traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

# Mock data matching the real structure
mock_chain = [
    {"level": "L1", "name": "设备制造", "supply_rigidity": {"severity": "extreme", "root_cause": "设备紧缺", "expand_cycle": "24-36", "substitutability": "low"},
     "profit_pool": {"margin_estimated": "high"}, "confidence": "high",
     "sub_processes": [
         {"name": "离子注入", "value_magnitude": {"order_of_magnitude": "10亿"}, "competitive_landscape": {"pricing_behavior": "monopoly_limited"},
          "supply_rigidity": {"substitutability": "none"}},
         {"name": "刻蚀", "value_magnitude": {"order_of_magnitude": "50亿"}, "competitive_landscape": {"pricing_behavior": "oligopoly"},
          "supply_rigidity": {"substitutability": "very_low"}}
     ]},
    {"level": "L2", "name": "材料供应", "supply_rigidity": {"severity": "high", "root_cause": "材料紧缺", "expand_cycle": "12-18"},
     "profit_pool": {"margin_estimated": "medium"}, "confidence": "medium", "sub_processes": []},
    {"level": "L3", "name": "封装测试", "supply_rigidity": {"severity": "medium", "root_cause": "产能不足", "expand_cycle": "6-12"},
     "profit_pool": {"margin_estimated": "medium"}, "confidence": "high", "sub_processes": []},
]

mock_scarcity = [
    {"rank": "1", "segment": "设备制造", "rigidity_narrative": "设备紧缺导致产能无法扩张，成为产业链核心瓶颈", "confidence": "high"},
    {"rank": "2", "segment": "材料供应", "rigidity_narrative": "关键材料依赖进口，国产替代周期长", "confidence": "medium"},
]

mock_stocks = [
    {"code": "688012", "name": "中微公司"},
    {"code": "002371", "name": "北方华创"},
]

mock_search = [
    {"query": "设备制造 扩产 瓶颈迁移", "results": [
        {"title": "半导体设备交期延长", "snippet": "半导体设备交期从6个月延长至18个月，核心设备尤甚"},
        {"title": "设备产能瓶颈", "snippet": "龙头设备厂商产能利用率已超95%，新产能需24个月释放"},
    ]},
    {"query": "设备制造 意外受益", "results": [
        {"title": "国产设备受益", "snippet": "设备紧缺推动国产替代加速，部分国内设备商获得验证机会"},
    ]},
]

def main():
    from app.domain.research.agents.system_dynamics_agent import SystemDynamicsAgent
    from app.framework.ai.providers.deepseek import DeepSeekProvider

    agent = SystemDynamicsAgent(provider=DeepSeekProvider())

    # Test 1: _build_prompt with mock data
    print("=" * 60)
    print("TEST 1: _build_prompt with full mock data")
    print("=" * 60)
    try:
        prompt = agent._build_prompt(
            industry="半导体设备",
            chain_map=mock_chain,
            scarcity=mock_scarcity,
            core_stocks=mock_stocks,
            search_data=mock_search,
            step2={"cycle_phase": "early_upswing", "profit_redirection": "下游→上游",
                   "repricing_stage": "early", "payoff_asymmetry": "positive_right_skewed",
                   "substitution_risk": "medium", "propagation_depth": "deep"},
            cross_search_data=[
                {"node": "设备制造", "search_data": [
                    {"query": "设备制造 下游 应用", "results": [{"title": "下游需求", "snippet": "半导体设备主要应用于晶圆制造"}]}
                ]}
            ],
            bn_nodes=[{"name": "设备制造", "level": "L1", "severity": "extreme", "root_cause": "设备紧缺"}]
        )
        print(f"✅ _build_prompt succeeded: {len(prompt)} chars")
    except SyntaxError as e:
        print(f"❌ _build_prompt SYNTAX ERROR: {e}")
        traceback.print_exc()
    except ValueError as e:
        print(f"❌ _build_prompt ValueError: {e}")
        traceback.print_exc()
    except Exception as e:
        print(f"❌ _build_prompt failed: {type(e).__name__}: {e}")
        traceback.print_exc()
        return

    # Test 2: _build_prompt with EMPTY cross_search_data
    print("\n" + "=" * 60)
    print("TEST 2: _build_prompt with empty cross_search_data")
    print("=" * 60)
    try:
        prompt2 = agent._build_prompt(
            industry="测试",
            chain_map=mock_chain,
            scarcity=[],
            core_stocks=[],
            search_data=mock_search,
            step2=None,
            cross_search_data=None,
            bn_nodes=[]
        )
        print(f"✅ _build_prompt (empty cross) succeeded: {len(prompt2)} chars")
    except Exception as e:
        print(f"❌ _build_prompt (empty cross) failed: {type(e).__name__}: {e}")
        traceback.print_exc()

    # Test 3: Test all f-strings in the agent
    print("\n" + "=" * 60)
    print("TEST 3: Test _format_chain_with_sub")
    print("=" * 60)
    try:
        formatted = SystemDynamicsAgent._format_chain_with_sub(mock_chain)
        print(f"✅ _format_chain_with_sub: {len(formatted)} chars")
        print(formatted[:200])
    except Exception as e:
        print(f"❌ _format_chain_with_sub failed: {type(e).__name__}: {e}")
        traceback.print_exc()

    print("\n" + "=" * 60)
    print("TEST 4: Test _extract_bottleneck_nodes")
    print("=" * 60)
    try:
        nodes = SystemDynamicsAgent._extract_bottleneck_nodes(mock_chain)
        print(f"✅ _extract_bottleneck_nodes: {len(nodes)} nodes: {[n['name'] for n in nodes]}")
    except Exception as e:
        print(f"❌ _extract_bottleneck_nodes failed: {type(e).__name__}: {e}")

if __name__ == "__main__":
    main()
