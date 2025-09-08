import os
import json
import asyncio
import httpx
from datetime import datetime, timedelta, timezone
from logging import getLogger
from src.config import MANAGER_API_URL_FOR_UI

logger = getLogger("uvicorn")
JST = timezone(timedelta(hours=9))
SNAPSHOT_PATH = os.path.join(os.path.dirname(__file__), "../snapshot.json")

def load_snapshot():
    if not os.path.exists(SNAPSHOT_PATH):
        return None
    with open(SNAPSHOT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_snapshot(worker_ranking):
    data = {
        "timestamp": datetime.now(JST).isoformat(),
        "worker_total_count_ranking": [
            {
                "worker_name": r["worker_name"],
                "worker_total_count": r["worker_total_count"],
                "jp_count": r.get("jp_count", 0)
            }
            for r in worker_ranking.get("worker_total_count_ranking", [])
        ]
    }
    with open(SNAPSHOT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def should_update_snapshot():
    if not os.path.exists(SNAPSHOT_PATH):
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

async def background_snapshot_json_wrapper():
    logger.info("  - 📸 [UI:snapshot_json] background_snapshot_json_wrapper")
    await background_snapshot_json()

def start_ui_snapshot_json():
    logger.info("📸 [UI:snapshot_json] start_ui_snapshot_json")
    return asyncio.create_task(background_snapshot_json_wrapper())

async def background_snapshot_json():
    while True:
        logger.info("      - 📸 [UI:snapshot_json] background_snapshot_json")
        try:
            if should_update_snapshot():
                async with httpx.AsyncClient() as client:
                    resp = await client.get(f"{MANAGER_API_URL_FOR_UI}/api/worker_ranking")
                    if resp.status_code == 200:
                        save_snapshot(resp.json())
                        logger.info("snapshot.json created or updated")
            # Sleep until next 9:30 JST
            now = datetime.now(JST)
            next_930 = now.replace(hour=9, minute=30, second=0, microsecond=0)
            if now >= next_930:
                next_930 += timedelta(days=1)
            wait_sec = (next_930 - now).total_seconds()
            await asyncio.sleep(wait_sec)
        except Exception as e:
            logger.error(f"Snapshot job error: {e}")
            await asyncio.sleep(3600)
