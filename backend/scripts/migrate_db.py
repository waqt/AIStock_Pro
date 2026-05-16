import asyncio
import os
import sys
from sqlalchemy import text

base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(base_dir)

from dotenv import load_dotenv
load_dotenv(os.path.join(base_dir, ".env"))

from app.core.database import engine

async def migrate():
    print("[*] Starting FINAL database migration...")
    async with engine.begin() as conn:
        # 补全 analysis_tasks 表
        task_cols = [
            ("progress", "INTEGER DEFAULT 0"),
            ("pid", "INTEGER NULL"),
            ("updated_at", "DATETIME DEFAULT CURRENT_TIMESTAMP")
        ]
        
        for col_name, col_type in task_cols:
            try:
                await conn.execute(text(f"ALTER TABLE analysis_tasks ADD COLUMN {col_name} {col_type}"))
                print(f"[✅] Added to analysis_tasks: {col_name}")
            except Exception:
                print(f"[!] {col_name} already exists in analysis_tasks.")

    print("[*] Final Migration complete.")

if __name__ == "__main__":
    asyncio.run(migrate())
