from cachetools import TTLCache

from src.share.animal import get_worker_emoji
from src.config import JST, BATCH_SIZE, ORDERED_CATEGORIES
from src.manager_api.db import get_async_session
from src.manager_api.models import WorkerLogStat, WorkerStatus
from datetime import datetime, timedelta
from fastapi import Depends, APIRouter
from sqlalchemy import func, select
from src.share.job_status import JobStatus
from asyncache import cached

@cached(TTLCache(maxsize=1, ttl=timedelta(seconds=300)))
async def get_running_worker_count(db):
    stmt_count = select(func.count()).where(WorkerStatus.status == JobStatus.RUNNING.value)
    total_running_count = (await db.execute(stmt_count)).scalar_one()
    return total_running_count

