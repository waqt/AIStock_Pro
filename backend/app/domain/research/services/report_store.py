"""
研报持久化存储 — JSON 文件存储, 支持列表/读取/保存/删除
"""
import json, os, re, glob
from datetime import datetime
from typing import List, Dict, Optional
from app.framework.logger import logger

REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "data", "research_reports")
REPORTS_DIR = os.path.abspath(REPORTS_DIR)


def _sanitize(s: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', '_', s)[:30]


def save_report(agent: str, industry: str, data: Dict) -> str:
    """保存研报, 返回 report_id (文件名)"""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{ts}_{agent}_{_sanitize(industry)}.json"
    filepath = os.path.join(REPORTS_DIR, filename)

    record = {
        "report_id": filename.replace(".json", ""),
        "agent": agent,
        "industry": industry,
        "created_at": datetime.now().isoformat(),
        "data": data,
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2, default=str)

    logger.info(f"[ReportStore] Saved: {filename}")
    return record["report_id"]


def list_reports(limit: int = 20) -> List[Dict]:
    """列出最近的研报 (摘要, 不含完整数据)"""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    files = sorted(glob.glob(os.path.join(REPORTS_DIR, "*.json")), reverse=True)[:limit]

    reports = []
    for fp in files:
        try:
            with open(fp, "r", encoding="utf-8") as f:
                r = json.load(f)
            data = r.get("data", {})
            # 摘要字段
            core_stocks = data.get("core_stocks", [])
            reports.append({
                "report_id": r.get("report_id", ""),
                "agent": r.get("agent", ""),
                "industry": r.get("industry", ""),
                "created_at": r.get("created_at", ""),
                "summary": data.get("summary") or data.get("final_summary") or data.get("global_summary", "")[:150],
                "stocks_count": len(core_stocks),
                "stocks": [
                    {"code": s.get("code"), "name": s.get("name")}
                    for s in core_stocks[:5]
                ],
                "verdict": data.get("verdict") or "",
            })
        except Exception as e:
            logger.warning(f"[ReportStore] Failed to read {fp}: {e}")
    return reports


def get_report(report_id: str) -> Optional[Dict]:
    """读取单篇研报完整内容"""
    filepath = os.path.join(REPORTS_DIR, f"{report_id}.json")
    if not os.path.exists(filepath):
        return None
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def delete_report(report_id: str) -> bool:
    """删除单篇研报"""
    filepath = os.path.join(REPORTS_DIR, f"{report_id}.json")
    if not os.path.exists(filepath):
        return False
    os.remove(filepath)
    logger.info(f"[ReportStore] Deleted: {report_id}")
    return True
