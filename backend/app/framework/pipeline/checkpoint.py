"""
Pipeline 检查点基础设施 — 强确定性 / 强缓存 / 强可回放 / 强日志 / 强可观测 / 强失败恢复
"""
import os, json, time, hashlib
from datetime import datetime


# backend/data/pipeline_checkpoints/
# checkpoint.py is in backend/app/framework/pipeline/, go up 3 levels to reach backend/
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
CHECKPOINT_DIR = os.path.join(_PROJECT_ROOT, "data", "pipeline_checkpoints")


def _ensure_dir():
    os.makedirs(CHECKPOINT_DIR, exist_ok=True)


def hash_input(data: dict) -> str:
    """对输入做确定性 hash, 作为缓存 key"""
    raw = json.dumps(data, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def checkpoint_path(step: str, run_id: str, input_hash: str = "") -> str:
    """检查点 JSON 文件路径 — 按 run_id 组织目录"""
    _ensure_dir()
    run_dir = os.path.join(CHECKPOINT_DIR, run_id)
    os.makedirs(run_dir, exist_ok=True)
    if input_hash:
        return os.path.join(run_dir, f"{step}_{input_hash}.json")
    return os.path.join(run_dir, f"{step}.json")


def load_checkpoint(step: str, run_id: str, input_hash: str) -> dict | None:
    """读取缓存 — 如果输入未变, 直接返回上次结果.
    跨版本搜索: run_id 的版本号可能变化, 所以搜索所有匹配前缀的目录.
    """
    # 先精确查当前 run_id
    path = checkpoint_path(step, run_id, input_hash)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("output")

    # 跨版本搜索: 去掉 _v{n} 后缀, 搜索所有匹配的目录
    import re
    base = re.sub(r'_v\d+$', '', run_id)
    _ensure_dir()
    if os.path.exists(CHECKPOINT_DIR):
        for name in sorted(os.listdir(CHECKPOINT_DIR), reverse=True):
            if not name.startswith(base):
                continue
            rp = os.path.join(CHECKPOINT_DIR, name)
            if not os.path.isdir(rp):
                continue
            cp = os.path.join(rp, f"{step}_{input_hash}.json")
            if os.path.exists(cp):
                with open(cp, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data.get("output")
    return None


def save_checkpoint(step: str, run_id: str, input_hash: str,
                    output: dict, meta: dict = None) -> str:
    """落盘 — 输入hash + 输出 + 元信息"""
    _ensure_dir()
    path = checkpoint_path(step, run_id, input_hash)
    record = {
        "step": step,
        "run_id": run_id,
        "input_hash": input_hash,
        "saved_at": datetime.now().isoformat(),
        "elapsed_seconds": meta.get("elapsed", 0) if meta else 0,
        "input_summary": meta.get("input_summary", "") if meta else "",
        "output": output,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2, default=str)
    return path


def save_trace(run_id: str, step: str, trace_data: dict) -> str:
    """写 trace 日志 — 每行一个 JSON 事件, 便于 grep 和逐行解析"""
    _ensure_dir()
    run_dir = os.path.join(CHECKPOINT_DIR, run_id)
    os.makedirs(run_dir, exist_ok=True)
    path = os.path.join(run_dir, f"{step}.trace.txt")
    with open(path, "w", encoding="utf-8") as f:
        for event in trace_data.get("events", []):
            f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
    return path


def save_manifest(run_id: str, manifest: dict) -> str:
    """写 run manifest — 运行元信息"""
    _ensure_dir()
    path = os.path.join(CHECKPOINT_DIR, run_id, "_run_manifest.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2, default=str)
    return path


def load_manifest(run_id: str) -> dict | None:
    """读取 run manifest"""
    path = os.path.join(CHECKPOINT_DIR, run_id, "_run_manifest.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def generate_run_id(industry: str) -> str:
    """生成 run_id: {YYYYMMDD}_{safe_slug}_v{n}, 自动递增版本号"""
    import re
    safe = re.sub(r'[^a-zA-Z0-9一-鿿_-]', '_', industry)[:50]
    today = datetime.now().strftime("%Y%m%d")
    base = f"{today}_{safe}"
    # 扫描已有 run, 自动递增
    _ensure_dir()
    version = 1
    for name in os.listdir(CHECKPOINT_DIR):
        if name.startswith(base) and os.path.isdir(os.path.join(CHECKPOINT_DIR, name)):
            try:
                v = int(name.rsplit("_v", 1)[-1])
                version = max(version, v + 1)
            except ValueError:
                pass
    return f"{base}_v{version}"


def list_checkpoints(run_id: str = None) -> list:
    """列出已有检查点 — 可按 run_id 过滤"""
    _ensure_dir()
    results = []
    base = CHECKPOINT_DIR if not run_id else os.path.join(CHECKPOINT_DIR, run_id)
    if not os.path.exists(base):
        return []
    for root, dirs, files in os.walk(base):
        for fn in files:
            if fn.endswith(".json") and not fn.startswith("_"):
                fp = os.path.join(root, fn)
                try:
                    with open(fp, "r", encoding="utf-8") as f:
                        r = json.load(f)
                    results.append({
                        "step": r.get("step"),
                        "run_id": r.get("run_id", os.path.basename(os.path.dirname(fp))),
                        "saved_at": r.get("saved_at"),
                        "elapsed": r.get("elapsed_seconds"),
                        "file": fp,
                    })
                except Exception:
                    pass
    return sorted(results, key=lambda x: x.get("saved_at", ""), reverse=True)


def list_runs() -> list:
    """列出所有 run (含状态摘要)"""
    _ensure_dir()
    runs = []
    if not os.path.exists(CHECKPOINT_DIR):
        return runs
    for name in os.listdir(CHECKPOINT_DIR):
        rp = os.path.join(CHECKPOINT_DIR, name)
        if not os.path.isdir(rp):
            continue
        manifest = load_manifest(name) or {}
        runs.append({
            "run_id": name,
            "industry": manifest.get("industry", ""),
            "mode": manifest.get("mode", ""),
            "status": manifest.get("status", "unknown"),
            "started_at": manifest.get("started_at", ""),
            "completed_at": manifest.get("completed_at", ""),
            "elapsed_seconds": manifest.get("elapsed_seconds", 0),
        })
    return sorted(runs, key=lambda x: x.get("started_at", ""), reverse=True)


def step(step_name: str, run_id: str):
    """装饰器: 自动加载/保存检查点

    用法:
    @checkpoint.step("step2_gatekeeper", "20260525_AI_power_v1")
    async def run_step2(input_data):
        return await heavy_computation(input_data)
    """
    def decorator(func):
        async def wrapper(input_data: dict, force: bool = False):
            t0 = time.time()
            ih = hash_input(input_data)

            # 命中缓存
            if not force:
                cached = load_checkpoint(step_name, run_id, ih)
                if cached:
                    elapsed = time.time() - t0
                    print(f"[checkpoint] {step_name} CACHE HIT ({ih}) in {elapsed:.1f}s")
                    return cached

            # 计算
            print(f"[checkpoint] {step_name} RUN ({ih})...")
            output = await func(input_data)
            elapsed = time.time() - t0

            path = save_checkpoint(step_name, run_id, ih, output, {
                "elapsed": round(elapsed, 1),
                "input_summary": str(list(input_data.keys()))[:100],
            })
            print(f"[checkpoint] {step_name} SAVED {path} ({elapsed:.1f}s)")
            return output
        return wrapper
    return decorator
