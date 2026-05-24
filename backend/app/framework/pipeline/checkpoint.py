"""
Pipeline 检查点基础设施 — 强确定性 / 强缓存 / 强可回放 / 强日志 / 强可观测 / 强失败恢复
"""
import os, json, time, hashlib
from datetime import datetime


# backend/data/pipeline_checkpoints/
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
CHECKPOINT_DIR = os.path.join(_PROJECT_ROOT, "data", "pipeline_checkpoints")


def _ensure_dir():
    os.makedirs(CHECKPOINT_DIR, exist_ok=True)


def hash_input(data: dict) -> str:
    """对输入做确定性 hash, 作为缓存 key"""
    raw = json.dumps(data, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def checkpoint_path(step: str, slug: str, input_hash: str) -> str:
    _ensure_dir()
    step_dir = os.path.join(CHECKPOINT_DIR, slug)
    os.makedirs(step_dir, exist_ok=True)
    return os.path.join(step_dir, f"{step}_{input_hash}.json")


def load_checkpoint(step: str, slug: str, input_hash: str) -> dict | None:
    """读取缓存 — 如果输入未变, 直接返回上次结果"""
    path = checkpoint_path(step, slug, input_hash)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("output")
    return None


def save_checkpoint(step: str, slug: str, input_hash: str,
                    output: dict, meta: dict = None) -> str:
    """落盘 — 输入hash + 输出 + 元信息"""
    _ensure_dir()
    path = checkpoint_path(step, slug, input_hash)
    record = {
        "step": step,
        "slug": slug,
        "input_hash": input_hash,
        "saved_at": datetime.now().isoformat(),
        "elapsed_seconds": meta.get("elapsed", 0) if meta else 0,
        "input_summary": meta.get("input_summary", "") if meta else "",
        "output": output,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2, default=str)
    return path


def list_checkpoints(slug: str = None) -> list:
    """列出已有检查点"""
    _ensure_dir()
    results = []
    base = CHECKPOINT_DIR if not slug else os.path.join(CHECKPOINT_DIR, slug)
    if not os.path.exists(base):
        return []
    for root, dirs, files in os.walk(base):
        for fn in files:
            if fn.endswith(".json"):
                fp = os.path.join(root, fn)
                try:
                    with open(fp, "r", encoding="utf-8") as f:
                        r = json.load(f)
                    results.append({
                        "step": r.get("step"),
                        "slug": r.get("slug"),
                        "saved_at": r.get("saved_at"),
                        "elapsed": r.get("elapsed_seconds"),
                        "file": fp,
                    })
                except Exception:
                    pass
    return sorted(results, key=lambda x: x.get("saved_at", ""), reverse=True)


def step(step_name: str, slug: str):
    """装饰器: 自动加载/保存检查点

    用法:
    @checkpoint.step("step2_gatekeeper", "AI_power")
    async def run_step2(input_data):
        return await heavy_computation(input_data)
    """
    def decorator(func):
        async def wrapper(input_data: dict, force: bool = False):
            t0 = time.time()
            ih = hash_input(input_data)

            # 命中缓存
            if not force:
                cached = load_checkpoint(step_name, slug, ih)
                if cached:
                    elapsed = time.time() - t0
                    print(f"[checkpoint] {step_name} CACHE HIT ({ih}) in {elapsed:.1f}s")
                    return cached

            # 计算
            print(f"[checkpoint] {step_name} RUN ({ih})...")
            output = await func(input_data)
            elapsed = time.time() - t0

            path = save_checkpoint(step_name, slug, ih, output, {
                "elapsed": round(elapsed, 1),
                "input_summary": str(list(input_data.keys()))[:100],
            })
            print(f"[checkpoint] {step_name} SAVED {path} ({elapsed:.1f}s)")
            return output
        return wrapper
    return decorator
