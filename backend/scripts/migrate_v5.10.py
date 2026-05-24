"""V5.10: 建 report_registry 表 + 回填现有 JSON 报告"""
import sys, os, asyncio, json, glob
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text

async def run():
    from app.framework.database.session import engine, async_session
    from app.models.models import ReportRegistry
    from sqlalchemy import select

    # 1. 建表
    async with engine.begin() as conn:
        try:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS report_registry (
                    id INTEGER PRIMARY KEY AUTO_INCREMENT,
                    report_type VARCHAR(30) NOT NULL COMMENT 'macro/supply_chain/market_scan/capex_scan',
                    report_id VARCHAR(100) NOT NULL COMMENT '文件名(不含.json)',
                    title VARCHAR(200) COMMENT '可读标题',
                    industry VARCHAR(80) COMMENT '行业',
                    agent VARCHAR(80) COMMENT '生成方',
                    filepath VARCHAR(500) COMMENT '相对路径',
                    generated_at DATETIME NOT NULL COMMENT '生成时间',
                    valid_until DATETIME COMMENT '有效期',
                    status VARCHAR(20) DEFAULT 'valid' COMMENT 'valid/expired/regenerated',
                    summary VARCHAR(200) COMMENT '摘要',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE KEY uq_report_id (report_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """))
            print("  OK: report_registry table created")
        except Exception as e:
            if "already exists" in str(e).lower():
                print("  SKIP: table already exists")
            else:
                print(f"  ERROR: {e}")

    # 2. 回填 research_reports
    reports_dir = os.path.join(os.path.dirname(__file__), "..", "data", "research_reports")
    count = 0
    if os.path.exists(reports_dir):
        async with async_session() as db:
            for fp in sorted(glob.glob(os.path.join(reports_dir, "*.json"))):
                try:
                    with open(fp, "r", encoding="utf-8") as f:
                        r = json.load(f)
                    rid = r.get("report_id", os.path.basename(fp).replace(".json", ""))
                    # check existing
                    ex = await db.execute(select(ReportRegistry).where(ReportRegistry.report_id == rid))
                    if ex.scalars().first():
                        continue
                    db.add(ReportRegistry(
                        report_type="supply_chain" if "产业链" in r.get("agent","") else "market_scan",
                        report_id=rid,
                        title=r.get("data",{}).get("title") or r.get("industry",""),
                        industry=r.get("industry",""),
                        agent=r.get("agent",""),
                        filepath=f"data/research_reports/{rid}.json",
                        generated_at=r.get("created_at",""),
                        status="valid",
                        summary=r.get("data",{}).get("final_summary","")[:200],
                    ))
                    count += 1
                except Exception as e:
                    print(f"  WARN: {os.path.basename(fp)}: {e}")
            await db.commit()
    print(f"  Backfilled {count} research reports")

    # 3. macro_report.json
    macro_path = os.path.join(os.path.dirname(__file__), "..", "data", "macro_report.json")
    if os.path.exists(macro_path):
        async with async_session() as db:
            with open(macro_path, "r", encoding="utf-8") as f:
                r = json.load(f)
            rid = r.get("report_id", "macro_report")
            ex = await db.execute(select(ReportRegistry).where(ReportRegistry.report_id == rid))
            if not ex.scalars().first():
                db.add(ReportRegistry(
                    report_type="macro",
                    report_id=rid,
                    title="宏观周期报告",
                    agent=r.get("generated_by","GlobalCapexScanner"),
                    filepath="data/macro_report.json",
                    generated_at=r.get("generated_at",""),
                    valid_until=r.get("valid_until"),
                    status="valid",
                ))
                await db.commit()
                print("  OK: macro_report registered")

    print("V5.10 migration complete.")

if __name__ == "__main__":
    asyncio.run(run())
