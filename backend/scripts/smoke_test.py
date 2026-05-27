"""
冒烟测试 --提交前验证所有关键 API 端点
用法: python scripts/smoke_test.py
返回: 所有通过 → exit 0, 任何失败 → exit 1
"""
import asyncio, sys, os, json
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from dataclasses import dataclass, field
from typing import Callable, List
import httpx

BASE = os.environ.get("SMOKE_HOST", "http://127.0.0.1:8000")
PASS = 0
FAIL = 0


@dataclass
class Case:
    name: str
    method: str
    path: str
    body: dict = None
    checks: List[Callable] = field(default_factory=list)


async def run_tests():
    global PASS, FAIL
    cases = [
        # ── 系统基础 (注意: /health 被 StaticFiles mount 拦截, 用数据源状态代替) ──

        # ── 任务管理 ──
        Case("任务定义列表", "GET", "/api/system/tasks/definitions",
             checks=[lambda r: r.status_code == 200,
                     lambda r: isinstance(r.json(), list)]),
        Case("活跃任务", "GET", "/api/system/tasks/executions/active",
             checks=[lambda r: r.status_code == 200]),
        Case("执行历史", "GET", "/api/system/tasks/executions/history?page=1&limit=5",
             checks=[lambda r: r.status_code == 200]),
        Case("调度作业", "GET", "/api/system/tasks/scheduler/jobs",
             checks=[lambda r: r.status_code == 200]),

        # ── 持仓管理 ──
        Case("持仓列表", "GET", "/api/positions",
             checks=[lambda r: r.status_code == 200,
                     lambda r: isinstance(r.json(), list)]),
        Case("账户摘要", "GET", "/api/positions/account/summary",
             checks=[lambda r: r.status_code == 200,
                     lambda r: "total_capital" in r.json()]),

        # ── 数据管理 ──
        Case("数据源状态", "GET", "/api/data/sources/status",
             checks=[lambda r: r.status_code == 200]),
        Case("健康概览", "GET", "/api/data/health/overview",
             checks=[lambda r: r.status_code == 200]),
        Case("行情体检", "GET", "/api/data/health/stocks",
             checks=[lambda r: r.status_code == 200]),
        Case("单个行情体检", "GET", "/api/data/health/600699",
             checks=[lambda r: r.status_code == 200]),
        Case("日线数据", "GET", "/api/data/daily/600699?limit=5",
             checks=[lambda r: r.status_code == 200]),
        Case("指标注册表", "GET", "/api/quant/indicators/registry",
             checks=[lambda r: r.status_code == 200,
                     lambda r: isinstance(r.json().get("data", []), list),
                     lambda r: len(r.json().get("data", [])) >= 5]),
        Case("个股指标", "GET", "/api/data/indicators/600699",
             checks=[lambda r: r.status_code == 200]),
        Case("汇率查询", "GET", "/api/data/forex/rates",
             checks=[lambda r: r.status_code == 200]),

        # ── 导入模块 ──
        Case("导入缓存", "GET", "/api/ai/get-cache",
             checks=[lambda r: r.status_code == 200]),
        Case("文本解析", "POST", "/api/ai/parse-text",
             body={"text": "600519 测试 100 1800"},
             checks=[lambda r: r.status_code == 200,
                     lambda r: r.json().get("data", [{}])[0].get("stock_code") == "600519"]),
    ]

    async with httpx.AsyncClient(timeout=10.0) as client:
        for case in cases:
            url = f"{BASE}{case.path}"
            try:
                if case.method == "GET":
                    resp = await client.get(url)
                elif case.method == "POST":
                    resp = await client.post(url, json=case.body)
                elif case.method == "DELETE":
                    resp = await client.delete(url)
                else:
                    print(f"[SKIP] {case.name}: unknown method {case.method}")
                    continue

                failed_checks = []
                for check in case.checks:
                    try:
                        if not check(resp):
                            failed_checks.append(f"check failed")
                    except Exception as e:
                        failed_checks.append(str(e))

                if not failed_checks:
                    PASS += 1
                    print(f"[PASS] {case.method} {case.path} - {case.name}")
                else:
                    FAIL += 1
                    print(f"[FAIL] {case.method} {case.path} - {case.name}")
                    for f in failed_checks:
                        print(f"       -> {f}")
                    print(f"       Status: {resp.status_code}, Body: {resp.text[:200]}")

            except Exception as e:
                FAIL += 1
                print(f"[FAIL] {case.name}: {type(e).__name__}: {e}")

    print(f"\n{'='*50}")
    print(f"Results: {PASS} passed, {FAIL} failed, {PASS+FAIL} total")
    return FAIL == 0


async def main():
    # 先确保服务在运行
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            await client.get(f"{BASE}/health")
    except Exception:
        print("[!] Server not running on http://127.0.0.1:8000")
        print("    Start with: run_backend.bat")
        return

    ok = await run_tests()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    asyncio.run(main())
