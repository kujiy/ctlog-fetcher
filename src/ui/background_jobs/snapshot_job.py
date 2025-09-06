import os
import asyncio
import httpx
from datetime import datetime, timedelta, timezone
from logging import getLogger
from src.ui.snapshot_utils import load_snapshot, save_snapshot
from src.config import MANAGER_API_URL_FOR_UI

logger = getLogger("uvicorn")
JST = timezone(timedelta(hours=9))

async def snapshot_job():
    while True:
        try:
            # Wait until 9:30 JST
            now = datetime.now(JST)
            target = now.replace(hour=9, minute=30, second=0, microsecond=0)
            if now >= target:
                # If already past 9:30 today, schedule for tomorrow
                target = target + timedelta(days=1)
            wait_sec = (target - now).total_seconds()
            await asyncio.sleep(wait_sec)
            # After waiting, update snapshot
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.get(f"{MANAGER_API_URL_FOR_UI}/api/worker_ranking")
                if resp.status_code == 200:
                    save_snapshot(resp.json())
                    logger.info("snapshot.json updated at 9:30 JST")
        except Exception as e:
            logger.error(f"Snapshot job error: {e}")
        # Sleep 1 hour as fallback
        await asyncio.sleep(3600)

def should_update_snapshot(snapshot_path):
    if not os.path.exists(snapshot_path):
        return True
    try:
        snapshot = load_snapshot()
        ts = snapshot.get("timestamp")
        if ts:
            snap_time = datetime.fromisoformat(ts).astimezone(JST)
            now_jst = datetime.now(JST)
            today_930 = now_jst.replace(hour=9, minute=30, second=0, microsecond=0)
            if snap_time < today_930:
                return True
            else:
                return False
        else:
            return True
    except Exception as e:
        logger.error(f"Failed to check snapshot.json timestamp: {e}")
        return True

async def run_snapshot_startup():
    # On startup: create or update snapshot.json if missing or outdated
    snapshot_path = os.path.join(os.path.dirname(__file__), "../snapshot.json")
    if should_update_snapshot(snapshot_path):
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{MANAGER_API_URL_FOR_UI}/api/worker_ranking")
                if resp.status_code == 200:
                    save_snapshot(resp.json())
                    logger.info("snapshot.json created or updated on startup")
        except Exception as e:
            logger.error(f"Initial snapshot creation/update failed: {e}")

    # Start background job
    asyncio.create_task(snapshot_job())
