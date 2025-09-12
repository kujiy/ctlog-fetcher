from cachetools import TTLCache

from src.config import JST
from src.manager_api.models import WorkerStatus
from sqlalchemy import func, select
from src.share.job_status import JobStatus
from asyncache import cached

@cached(TTLCache(maxsize=1, ttl=300))
async def get_running_thread_count(db):
    stmt_count = select(func.count()).where(WorkerStatus.status == JobStatus.RUNNING.value)
    total_running_count = (await db.execute(stmt_count)).scalar_one()
    return total_running_count

# get complted thread count last an hour
@cached(TTLCache(maxsize=1, ttl=300))
async def get_completed_thread_count_last_min(db, min: int) -> int:
    from datetime import datetime, timedelta
    one_hour_ago = datetime.now(JST) - timedelta(minutes=min)
    stmt_count = select(func.count()).where(
        WorkerStatus.status == JobStatus.COMPLETED.value,
        WorkerStatus.last_ping >= one_hour_ago
    )
    completed_count = (await db.execute(stmt_count)).scalar_one()
    return completed_count