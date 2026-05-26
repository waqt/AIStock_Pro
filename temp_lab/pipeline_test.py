"""
Pipeline 集成测试 — Mock 搜索和 LLM, 使用真实 checkpoint 数据做 fixture
运行: python temp_lab/pipeline_test.py
"""
import sys, os, json, asyncio
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

# ═══ 从真实 checkpoint 加载 fixture ═════════════════

def load_fixture(step, industry="capital_flow"):
    """从最近一次成功的 checkpoint 加载 fixture 数据"""
    base = os.path.join(os.path.dirname(__file__), '..', 'backend', 'data', 'pipeline_checkpoints')
    if not os.path.isdir(base):
        return None
    for d in sorted(os.listdir(base), reverse=True):
        if industry not in d: continue
        for f in os.listdir(os.path.join(base, d)):
            if f.startswith(step) and f.endswith('.json'):
                path = os.path.join(base, d, f)
                with open(path, 'r', encoding='utf-8') as fp:
                    record = json.load(fp)
                print(f"  Fixture loaded: {d}/{f} ({len(json.dumps(record.get('output',{})))} chars)")
                return record.get("output", {})
    return None


# ═══ 测试用例 ═════════════════════════════════

async def test_capital_flow_pipeline():
    """测试资本流向扫描完整链路: Step 1b → Step 2 → checkpoints"""
    from app.domain.research.api.routes import _do_scan, ScanRequest
    from app.domain.research.agents.market_scanner import MarketScanner

    print("\n=== Test: Capital Flow Pipeline ===")

    # 加载 fixture
    cf_fixture = load_fixture("step1b_capital_flow", "资本流向") or {
        "pressure_vectors": [{
            "system_node": "power_infrastructure",
            "pressure_signals": ["transformer lead time >18 months"],
            "intensity": "high", "duration": "3_5_years"
        }]
    }
    step2_fixture = load_fixture("step2_gatekeeper", "MLCC") or {
        "industry": "test", "cycle_position": {"phase": "bottleneck_formation"},
        "verdict": {"enter_step3": True, "priority": "高"}, "kill_reasons": []
    }

    step2_auto_fixture = {
        "industries": [
            {"industry": "电网设备", "verdict": {"enter_step3": True, "priority": "高"},
             "_step3_guidance": {"cycle_phase": "bottleneck_formation", "prosperity_type": "supply_shock"}},
            {"industry": "液冷散热", "verdict": {"enter_step3": False, "priority": "低"}},
        ], "count": 2
    }

    # Mock LLM
    from app.framework.ai.providers.deepseek import DeepSeekProvider

    async def mock_chat_flash(prompt, max_tokens=4096, **kw):
        return json.dumps(step2_auto_fixture, ensure_ascii=False)

    async def mock_chat_pro(prompt, max_tokens=4096, **kw):
        return json.dumps(step2_auto_fixture, ensure_ascii=False)

    # Mock search
    async def mock_search(query, num=5):
        return [{"title": f"Mock: {query[:40]}", "snippet": "Mock search result for pipeline test"}]

    with (patch.object(DeepSeekProvider, 'chat_flash', mock_chat_flash),
          patch.object(DeepSeekProvider, 'chat_pro', mock_chat_pro),
          patch('app.domain.research.agents.market_scanner.MarketScanner._search_with_fallback',
                new_callable=AsyncMock) as mock_search_m,
          patch('app.domain.research.services.data_loader.data_loader.search_web',
                new_callable=AsyncMock) as mock_search_dl):

        mock_search_m.return_value = {"query": "mock", "results": [
            {"title": "Mock result", "snippet": "Test data"}]}
        mock_search_dl.return_value = [{"title": "Mock", "snippet": "Test"}]

        # 测试1: 资本流向模式同步执行
        print("\n  [Test 1] _do_scan capital_flow sync")
        from app.framework.pipeline.checkpoint import generate_run_id
        pre_run_id = generate_run_id("测试-资本流向")
        result = await _do_scan(ScanRequest(agent_id="supply_chain", mode_id="capital_flow", target=""),
                                pre_run_id=pre_run_id)

        success = result.get("success")
        run_id = result.get("run_id", "")
        has_step2 = result.get("data") is not None

        print(f"    success: {success}")
        print(f"    run_id: {run_id}")
        print(f"    has_step2_data: {has_step2}")
        print(f"    run_id matches: {run_id == pre_run_id}")

        # 检查 checkpoint 文件
        import glob
        checkpoint_dir = os.path.join(os.path.dirname(__file__), '..', 'backend', 'data', 'pipeline_checkpoints')
        run_dir = os.path.join(checkpoint_dir, run_id) if run_id else ""
        if run_dir and os.path.isdir(run_dir):
            files = os.listdir(run_dir)
            has_step1b = any('step1b' in f for f in files)
            has_step2 = any('step2_gatekeeper' in f and '.json' in f for f in files)
            print(f"    step1b_checkpoint: {has_step1b}")
            print(f"    step2_checkpoint: {has_step2}")
            print(f"    all files: {files}")
        else:
            print(f"    run directory NOT FOUND: {run_dir}")

        # 测试2: 验证 API 端点
        print("\n  [Test 2] Pipeline run detail API")
        # 直接调用 get_pipeline_run 逻辑
        from app.framework.pipeline.checkpoint import load_manifest, list_checkpoints
        manifest = load_manifest(run_id)
        checkpoints = list_checkpoints(run_id)
        step_names = [c.get("step", "?") for c in checkpoints]
        print(f"    manifest: {manifest is not None}")
        print(f"    checkpoint steps: {step_names}")

        print("\n  ✅ All tests passed" if (success and has_step1b) else "\n  ❌ Tests failed")


if __name__ == "__main__":
    asyncio.run(test_capital_flow_pipeline())
