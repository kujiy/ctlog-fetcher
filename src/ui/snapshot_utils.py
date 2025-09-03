import os
import json
from datetime import datetime, timedelta, timezone

SNAPSHOT_PATH = os.path.join(os.path.dirname(__file__), "snapshot.json")
JST = timezone(timedelta(hours=9))

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

