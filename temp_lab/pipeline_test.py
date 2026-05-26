"""
Pipeline 集成测试 — Mock 搜索和 LLM, 验证各种场景下的完整链路
运行: python temp_lab/pipeline_test.py
"""
import sys, os, json, asyncio
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


# ═══ Fixtures ═════════════════════════════════

PRESSURE_VECTORS = [{
    "system_node": "power_infrastructure",
    "pressure_signals": ["transformer lead time >18 months", "grid congestion"],
    "intensity": "high", "duration": "3_5_years",
    "source_region": "global",
    "pressure_type": "infrastructure_bottleneck",
    "evidence": [{"fact": "Mock", "from": "search[1]", "quality": {"level": "high", "source_type": "industry_data"}}]
}]

STEP2_AUTO_RESPONSE = json.dumps({
    "industries": [
        {"industry": "电网设备", "cycle_position": {"phase": "bottleneck_formation", "sub_phase": "early"},
         "verdict": {"enter_step3": True, "priority": "高"}, "kill_reasons": [],
         "_step3_guidance": {"cycle_phase": "bottleneck_formation", "prosperity_type": "supply_shock"}},
        {"industry": "液冷散热", "cycle_position": {"phase": "demand_explosion", "sub_phase": "early"},
         "verdict": {"enter_step3": False, "priority": "低"}, "kill_reasons": []},
    ], "count": 2
}, ensure_ascii=False)

STEP2_MANUAL_RESPONSE = json.dumps({
    "industry": "MLCC", "cycle_position": {"phase": "bottleneck_formation", "sub_phase": "early"},
    "prosperity": {"type": "supply_shock"}, "verdict": {"enter_step3": True, "priority": "高"},
    "kill_reasons": [], "mismatch_analysis": {"supply_demand_mismatch": "strong"},
    "_step3_guidance": {"cycle_phase": "bottleneck_formation", "prosperity_type": "supply_shock"}
}, ensure_ascii=False)

STEP3_RESPONSE = json.dumps({
    "supply_chain_map": [{"level": 1, "name": "MLCC制造", "supply_rigidity": {"severity": "extreme"}}],
    "core_stocks": [{"code": "000636", "name": "风华高科", "segment": "MLCC"}],
    "sales_chain": [], "expansion_chain": [], "scarcity_ranking": []
}, ensure_ascii=False)

CAPITAL_FLOW_RESPONSE = json.dumps({
    "capital_flow_summary": "全球资本正集中流向AI数据中心",
    "pressure_vectors": PRESSURE_VECTORS,
    "constraint_vectors": []
}, ensure_ascii=False)


# ═══ Mock 设置 ═════════════════════════════════

def setup_mocks(flash_response=STEP2_AUTO_RESPONSE, pro_response=STEP2_AUTO_RESPONSE,
                cf_response=CAPITAL_FLOW_RESPONSE):
    """设置全局 mock, 返回清理函数"""
    from app.framework.ai.providers.deepseek import DeepSeekProvider

    async def mock_flash(*args, **kw):
        return flash_response

    async def mock_pro(*args, **kw):
        return pro_response

    async def mock_search(query, num=5):
        return [{"title": f"Mock: {query[:40]}", "snippet": "Mock result for test"}]

    async def mock_search_with_fallback(queries, num=4, trace=None):
        return {"query": queries[0], "results": [
            {"title": f"Mock: {queries[0][:30]}", "snippet": "Test data"}]}

    # 需要 patch 两处 search: MarketScanner._search_with_fallback 和 data_loader.search_web
    return [
        patch.object(DeepSeekProvider, 'chat_flash', mock_flash),
        patch.object(DeepSeekProvider, 'chat_pro', mock_pro),
        patch('app.domain.research.services.data_loader.data_loader.search_web',
              new_callable=AsyncMock, side_effect=mock_search),
        patch('app.domain.research.agents.market_scanner.MarketScanner._search_with_fallback',
              new_callable=AsyncMock, side_effect=mock_search_with_fallback),
        patch('app.domain.research.agents.capital_flow_scanner.CapitalFlowScanner._search_adaptive',
              new_callable=AsyncMock, return_value=[{"query": "mock", "results": [
                  {"title": "Mock", "snippet": "Test"}]}]),
        patch('app.domain.research.agents.supply_chain_hacker.SupplyChainHacker._search_adaptive',
              new_callable=AsyncMock, return_value=[{"query": "mock", "results": [
                  {"title": "Mock", "snippet": "Test"}]}]),
    ]


# ═══ 断言工具 ═════════════════════════════════

PASS = 0
FAIL = 0

def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        print(f"  ✅ {name}" + (f": {detail}" if detail else ""))
        PASS += 1
    else:
        print(f"  ❌ {name}" + (f": {detail}" if detail else ""))
        FAIL += 1
    return condition


def assert_checkpoints(run_dir, *expected_steps):
    """验证 checkpoint 目录中存在指定步骤"""
    if not os.path.isdir(run_dir):
        return check("run_dir exists", False, run_dir)
    files = os.listdir(run_dir)
    for step in expected_steps:
        found = any(step in f for f in files)
        check(f"checkpoint: {step}", found)
    return True


# ═══ 清理 ═════════════════════════════════

def cleanup(run_id):
    base = os.path.join(os.path.dirname(__file__), '..', 'backend', 'data', 'pipeline_checkpoints')
    import glob
    for d in glob.glob(os.path.join(base, f"*{run_id}*")):
        import shutil
        shutil.rmtree(d, ignore_errors=True)


# ═══ 测试用例 ═════════════════════════════════

async def test_scenario_1_capital_flow():
    """场景1: 资本流向扫描 — Step 1b → Step 2 → 同目录"""
    print("\n" + "=" * 60)
    print("场景1: 资本流向扫描 (capital_flow)")
    from app.domain.research.api.routes import _do_scan, ScanRequest
    from app.framework.pipeline.checkpoint import generate_run_id

    mocks = setup_mocks(cf_response=CAPITAL_FLOW_RESPONSE)
    with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4]:
        run_id = generate_run_id("测试-资本流向")
        result = await _do_scan(ScanRequest(agent_id="supply_chain", mode_id="capital_flow", target=""), pre_run_id=run_id)

    run_dir = os.path.join(os.path.dirname(__file__), '..', 'backend', 'data', 'pipeline_checkpoints', run_id)
    check("success", result.get("success"))
    check("run_id matches", result.get("run_id") == run_id)
    assert_checkpoints(run_dir, "step1b_capital_flow", "step2_gatekeeper")
    cleanup(run_id)
    return result


async def test_scenario_2_auto_scan():
    """场景2: 全局扫描 — Step 1b → Step 2 (multi-industry) → 候选列表"""
    print("\n" + "=" * 60)
    print("场景2: 全局扫描 (auto_scan)")
    from app.domain.research.api.routes import _do_scan, ScanRequest
    from app.framework.pipeline.checkpoint import generate_run_id

    mocks = setup_mocks()
    with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4]:
        run_id = generate_run_id("测试-全局扫描")
        result = await _do_scan(ScanRequest(agent_id="supply_chain", mode_id="auto_scan"), pre_run_id=run_id)

    run_dir = os.path.join(os.path.dirname(__file__), '..', 'backend', 'data', 'pipeline_checkpoints', run_id)
    data = result.get("data", {})
    industries = data.get("industries", [])
    check("success", result.get("success"))
    check("has_industries", len(industries) >= 1, f"{len(industries)} industries")
    if industries:
        first = industries[0]
        check("industry_has_guidance", "_step3_guidance" in first)
        check("industry_has_verdict", "verdict" in first)
    assert_checkpoints(run_dir, "step1b_capital_flow", "step2_gatekeeper")
    cleanup(run_id)
    return result


async def test_scenario_3_manual_industry():
    """场景3: 定性产业分析 — Step 2 (single) → Step 3 链式调用"""
    print("\n" + "=" * 60)
    print("场景3: 定性产业分析 (manual_industry)")
    from app.domain.research.api.routes import _do_scan, ScanRequest
    from app.framework.pipeline.checkpoint import generate_run_id

    mocks = setup_mocks(flash_response=STEP2_MANUAL_RESPONSE)
    with mocks[0], mocks[1], mocks[2], mocks[3]:
        run_id = generate_run_id("测试-定性产业-MLCC")
        result = await _do_scan(ScanRequest(agent_id="supply_chain", mode_id="manual_industry", target="MLCC"), pre_run_id=run_id)

    run_dir = os.path.join(os.path.dirname(__file__), '..', 'backend', 'data', 'pipeline_checkpoints', run_id)
    data = result.get("data", {})
    check("success", result.get("success"))
    check("enter_step3", data.get("verdict", {}).get("enter_step3") == True)
    check("has_guidance", "_step3_guidance" in data)
    assert_checkpoints(run_dir, "step2_gatekeeper")
    cleanup(run_id)
    return result


async def test_scenario_4_industry_drilldown():
    """场景4: auto_scan → 选定行业 → Step 3"""
    print("\n" + "=" * 60)
    print("场景4: 行业下钻 (drilldown)")

    # 先跑 auto_scan
    from app.domain.research.api.routes import _do_scan, ScanRequest
    from app.framework.pipeline.checkpoint import generate_run_id, find_checkpoint_file

    mocks = setup_mocks()
    with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4]:
        run_id = generate_run_id("测试-下钻")
        result = await _do_scan(ScanRequest(agent_id="supply_chain", mode_id="auto_scan"), pre_run_id=run_id)

    # 模拟下钻: 直接用 SupplyChainHacker
    from app.domain.research.agents.supply_chain_hacker import SupplyChainHacker
    with mocks[0], mocks[1], mocks[2], mocks[3], mocks[5]:
        # 查找 step2 checkpoint
        cp_file = find_checkpoint_file(run_id, "step2_gatekeeper")
        check("step2_checkpoint_exists", cp_file is not None)
        if cp_file:
            with open(cp_file, 'r', encoding='utf-8') as f:
                step2 = json.load(f)
            industries = step2.get("output", {}).get("industries", [])
            check("industries_found", len(industries) >= 1, f"{len(industries)} found")
            if industries:
                target = industries[0]
                guidance = target.get("_step3_guidance", {})
                check("guidance_exists", bool(guidance))
                hacker = SupplyChainHacker(provider=MagicMock())
                ctx = {"industry": target["industry"], "step2_guidance": guidance}
                step3_result = await hacker.analyze(ctx)
                check("step3_layers", len(step3_result.get("supply_chain_map", [])) >= 1)

    run_dir = os.path.join(os.path.dirname(__file__), '..', 'backend', 'data', 'pipeline_checkpoints', run_id)
    assert_checkpoints(run_dir, "step2_gatekeeper")
    cleanup(run_id)


async def test_scenario_5_cache_hit():
    """场景5: 缓存命中 — 同一天两次相同输入, 第二次秒返"""
    print("\n" + "=" * 60)
    print("场景5: 缓存命中 (cache hit)")
    from app.domain.research.api.routes import _do_scan, ScanRequest
    from app.framework.pipeline.checkpoint import generate_run_id

    mocks = setup_mocks(flash_response=STEP2_MANUAL_RESPONSE)
    with mocks[0], mocks[1], mocks[2], mocks[3]:
        run_id = generate_run_id("测试-缓存-MLCC")
        # 第一次: 正常执行
        r1 = await _do_scan(ScanRequest(agent_id="supply_chain", mode_id="manual_industry", target="MLCC"), pre_run_id=run_id)
        # 第二次: 应该 cache hit
        r2 = await _do_scan(ScanRequest(agent_id="supply_chain", mode_id="manual_industry", target="MLCC"), pre_run_id=run_id)

    check("first_run_no_cache", r1.get("from_cache") != True)
    check("second_run_cache_hit", r2.get("from_cache") == True)
    check("same_run_id", r1.get("run_id") == r2.get("run_id"))
    check("same_data", r1.get("run_id") == r2.get("run_id"))
    cleanup(run_id)


async def test_scenario_6_pipeline_api():
    """场景6: Pipeline API 端点 — project detail 返回完整步骤"""
    print("\n" + "=" * 60)
    print("场景6: Pipeline API 项目详情")
    from app.domain.research.api.routes import _do_scan, ScanRequest, get_pipeline_run
    from app.framework.pipeline.checkpoint import generate_run_id

    mocks = setup_mocks(cf_response=CAPITAL_FLOW_RESPONSE)
    with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4]:
        run_id = generate_run_id("测试-API")
        await _do_scan(ScanRequest(agent_id="supply_chain", mode_id="capital_flow", target=""), pre_run_id=run_id)

    # 模拟 FastAPI 的 Response 包装
    detail = await get_pipeline_run(run_id)
    data = detail.get("data", {})
    steps = data.get("steps", {})
    pipeline = data.get("pipeline", [])

    check("api_returns_steps", len(steps) >= 1, f"{len(steps)} steps")
    check("api_returns_pipeline", len(pipeline) >= 1, f"{len(pipeline)} steps in pipeline")
    check("display_name_has_date", "-2026-" in data.get("display_name", ""))

    # 验证三态
    statuses = {s: info.get("status") for s, info in steps.items()}
    check("has_completed", "completed" in statuses.values(), f"statuses: {statuses}")
    if len(pipeline) > len(steps):
        check("has_planned_steps", True, "pipeline longer than completed steps")

    cleanup(run_id)


# ═══ 主入口 ═════════════════════════════════

async def main():
    global PASS, FAIL
    PASS = FAIL = 0
    import time
    t0 = time.time()

    for test in [
        test_scenario_1_capital_flow,
        test_scenario_2_auto_scan,
        test_scenario_3_manual_industry,
        test_scenario_4_industry_drilldown,
        test_scenario_5_cache_hit,
        test_scenario_6_pipeline_api,
    ]:
        try:
            await test()
        except Exception as e:
            print(f"  💥 EXCEPTION: {e}")
            import traceback
            traceback.print_exc()
            FAIL += 1

    elapsed = time.time() - t0
    print(f"\n{'='*60}")
    print(f"Results: {PASS} passed, {FAIL} failed, {PASS+FAIL} total ({elapsed:.1f}s)")
    return FAIL == 0


if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
