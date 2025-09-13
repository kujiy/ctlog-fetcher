from cachetools import TTLCache
from src.share.job_status import JobStatus
from asyncache import cached
from sqlalchemy import select, func, and_
from src.config import JST
from src.manager_api.models import WorkerStatus


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






## worker status aggs


async def aggregate_worker_status(session, start, end):
    # statusごとのカウント
    stmt = select(WorkerStatus.status, func.count()).where(
        and_(WorkerStatus.last_ping >= start, WorkerStatus.last_ping < end)
    ).group_by(WorkerStatus.status)
    result = await session.execute(stmt)
    status_counts = dict(result.all())

    # 全体数
    stmt = select(func.count()).where(and_(WorkerStatus.last_ping >= start, WorkerStatus.last_ping < end))
    total = (await session.execute(stmt)).scalar()

    # distinct worker_name, log_name
    stmt = select(func.count(func.distinct(WorkerStatus.worker_name))).where(and_(WorkerStatus.last_ping >= start, WorkerStatus.last_ping < end))
    worker_name_count = (await session.execute(stmt)).scalar()

    stmt = select(func.count(func.distinct(WorkerStatus.log_name))).where(and_(WorkerStatus.last_ping >= start, WorkerStatus.last_ping < end))
    log_name_count = (await session.execute(stmt)).scalar()

    stmt = select(func.coalesce(func.sum(WorkerStatus.jp_count), 0)).where(and_(WorkerStatus.last_ping >= start, WorkerStatus.last_ping < end))
    jp_count_sum = (await session.execute(stmt)).scalar()

    return {
        "total_worker_status_count": total,
        "completed": status_counts.get("completed", 0),
        "running": status_counts.get("running", 0),
        "dead": status_counts.get("dead", 0),
        "failed": status_counts.get("failed", 0),
        "resume_wait": status_counts.get("resume_wait", 0),
        "skipped": status_counts.get("skipped", 0),
        "worker_name_count": worker_name_count,
        "log_name_count": log_name_count,
        "jp_count_sum": jp_count_sum,
    }


async def worker_status_range_total_count(end, session, start):
    # last_pingでデータが存在するか確認
    stmt = select(func.count()).where(
        and_(WorkerStatus.last_ping >= start, WorkerStatus.last_ping < end)
    )
    count = (await session.execute(stmt)).scalar()
    return count

