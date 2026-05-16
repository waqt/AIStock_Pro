import asyncio
import os
import sys

base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(base_dir)

from dotenv import load_dotenv
load_dotenv(os.path.join(base_dir, ".env"))

from app.core.database import async_session
from app.models.models import TaskExecution
from sqlalchemy import select

async def audit():
    print("\n--- TASK DATABASE AUDIT (V5.0) ---")
    try:
        async with async_session() as db:
            res = await db.execute(select(TaskExecution))
            tasks = res.scalars().all()
            if not tasks:
                print("[!] No task executions found in database.")
            for t in tasks:
                print(f"[{t.status}] ID: {t.id} | Code: {t.task_code} | Started: {t.start_time}")
    except Exception as e:
        print(f"[ERROR] Audit failed: {e}")
    print("--- END AUDIT ---\n")

if __name__ == "__main__":
    asyncio.run(audit())
