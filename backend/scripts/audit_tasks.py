import asyncio
import os
import sys

base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(base_dir)

from dotenv import load_dotenv
load_dotenv(os.path.join(base_dir, ".env"))

from app.core.database import async_session
from app.models.models import AnalysisTask
from sqlalchemy import select

async def audit():
    print("\n--- TASK DATABASE AUDIT ---")
    try:
        async with async_session() as db:
            res = await db.execute(select(AnalysisTask))
            tasks = res.scalars().all()
            if not tasks:
                print("[!] No tasks found in database.")
            for t in tasks:
                print(f"[{t.status}] ID: {t.id} | Type: {t.task_type} | Created: {t.created_at}")
    except Exception as e:
        print(f"[ERROR] Audit failed: {e}")
    print("--- END AUDIT ---\n")

if __name__ == "__main__":
    asyncio.run(audit())
