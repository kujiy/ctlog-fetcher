from asyncache import cached
from cachetools import TTLCache

from src.manager_api.db_query import get_running_thread_count, worker_status_range_total_count, aggregate_worker_status
from src.share.animal import get_worker_emoji
from src.config import JST, BATCH_SIZE, ORDERED_CATEGORIES
from src.manager_api.db import get_async_session
from src.manager_api.models import WorkerLogStat, WorkerStatus
from datetime import datetime, timedelta
from fastapi import Depends, APIRouter
from sqlalchemy import func, select, text
from src.share.job_status import JobStatus, ALL_JOB_STATUS
from src.manager_api.models import WorkerStatusAggs
from src.share.logger import logger

# background jobs

router = APIRouter()



# ranking of workers by total fetched count and .jp count
async def get_completed_rates(db, threshold: datetime):
    raw_sql = f"""
    SELECT
        worker_name,
        ROUND(SUM(CASE WHEN status = :completed THEN 1 ELSE 0 END) /
              COUNT(*), 2) AS completed_rate
    FROM worker_status
    WHERE last_ping > :threshold
        AND status != :running
    GROUP BY worker_name
    """
    params = {
        "completed": JobStatus.COMPLETED.value,
        "threshold": threshold,
        "running": JobStatus.RUNNING.value
    }
    rows = (await db.execute(text(raw_sql), params)).all()
    result = {}
    for worker_name, completed_rate in rows:
        result[worker_name] = completed_rate
    return result


async def get_durations(db, threshold: datetime):
    raw_sql = f"""
    SELECT
        worker_name,
        ROUND(AVG(duration_sec) / 60, 2) AS average_min,
        ROUND(MAX(duration_sec) / 60, 2) AS max_duration_min
    FROM worker_status
    WHERE last_ping > :threshold
        AND status = :completed
    GROUP BY worker_name
    """
    params = {
        "completed": JobStatus.COMPLETED.value,
        "threshold": threshold,
    }
    rows = (await db.execute(text(raw_sql), params)).all()
    result = {}
    for worker_name, average_min, max_duration_min in rows:
        result[worker_name] = (average_min, max_duration_min)
    return result


@router.get("/api/worker_ranking")
async def get_worker_ranking(db=Depends(get_async_session)):
    # Additional columns for latest metrics
    threshold = datetime.now(JST) - timedelta(hours=2)
    completed_rates = await get_completed_rates(db, threshold)
    durations = await get_durations(db, threshold)

    stmt = select(
        WorkerLogStat.worker_name,
        func.sum(WorkerLogStat.worker_total_count).label('worker_total_count'),
        func.sum(WorkerLogStat.jp_count_sum).label('jp_count_sum')
    ).group_by(WorkerLogStat.worker_name).order_by(text('worker_total_count DESC'))
    rows = (await db.execute(stmt)).all()
    worker_total_count_ranking = []
    for r in rows:
        worker_name = f"{get_worker_emoji(r[0])} {r[0]}"
        worker_total_count = r[1]
        jp_count = r[2] or 0
        jp_ratio = (jp_count / worker_total_count) if worker_total_count > 0 else 0
        duration = durations.get(r[0], [0, 0])
        worker_total_count_ranking.append({
            "worker_name": worker_name,
            "worker_total_count": worker_total_count,
            "jp_count": jp_count,
            "jp_ratio": jp_ratio,
            "completed_rate": completed_rates.get(r[0], 0),
            "average_min": duration[0],
            "max_duration_min": duration[1]
        })

    return {
        "worker_total_count_ranking": worker_total_count_ranking,
    }


# --- get_tree_size with 1-minute cache ---
@router.get("/api/worker_stats/{worker_name}")
async def get_worker_stats(
        worker_name: str,
        hours: int = 24,
        bucket_hours: int = 1,
        db=Depends(get_async_session)
):
    # 1. WorkerStatus raw data for two hours
    stat_stmt = select(WorkerStatus).where(
        WorkerStatus.worker_name == worker_name,
        WorkerStatus.last_ping > datetime.now(JST) - timedelta(hours=2)
    ).order_by(WorkerStatus.id.desc())
    worker_status = (await db.execute(stat_stmt)).scalars().all()

    # 2. WorkerStatus: past 24 hours, aggregated hourly
    now = datetime.now(JST)
    since = now - timedelta(hours=hours)
    status_stmt = select(WorkerStatus).where(
        WorkerStatus.worker_name == worker_name,
        WorkerStatus.last_ping >= since
    )
    status_rows = (await db.execute(status_stmt)).scalars().all()

    # a bucket for 24 hours, each 1 hour
    buckets = []
    for i in range(int(hours / bucket_hours)):
        bucket_start = since + timedelta(hours=i * bucket_hours)
        bucket_end = bucket_start + timedelta(hours=bucket_hours)
        buckets.append({
            "hour_label": bucket_start.strftime("%Y-%m-%d %H:00"),
            "start": bucket_start,
            "end": bucket_end,
            "status_counts": {},
            "jp_count_sum": 0,
            "duration_min": {
                "count": 0,
                "max": 0,
                "avg": 0,
            },
            "log_name_counts": {},
        })

    # calculate each worker status into the buckets
    for ws in status_rows:
        last_ping = ws.last_ping
        # Add JST if last_ping is offset-naive
        if last_ping is not None and last_ping.tzinfo is None:
            last_ping = last_ping.astimezone(JST)
        for bucket in buckets:
            if last_ping is not None and bucket["start"] <= last_ping < bucket["end"]:
                # jobs status count
                bucket["status_counts"][ws.status] = bucket["status_counts"].get(ws.status, 0) + 1
                # sum of jp_count
                bucket["jp_count_sum"] += ws.jp_count or 0
                # duration_min: avg, max
                if ws.duration_sec:
                    duration_min = round(ws.duration_sec / 60, 2)
                    bucket["duration_min"]["count"] += 1
                    bucket["duration_min"]["avg"] = round((bucket["duration_min"]["avg"] + ws.duration_sec / 60) / bucket["duration_min"]["count"], 2)
                    if duration_min > bucket["duration_min"]["max"]:
                        bucket["duration_min"]["max"] = duration_min
                # job count per log_name
                bucket["log_name_counts"][ws.log_name] = bucket["log_name_counts"].get(ws.log_name, 0) + 1
                break

    # order by most recent hour first
    buckets_sorted = list(reversed(buckets))

    status_stats = []
    for b in buckets_sorted:
        # status_counts: include all job statuses
        status_counts = {status: b["status_counts"].get(status, 0) for status in ALL_JOB_STATUS}
        # log_name_counts: order by count desc
        log_name_counts = dict(sorted(b["log_name_counts"].items(), key=lambda x: x[1], reverse=True))
        # hour_label: "YYYY-MM-DD HH:00 - HH:00"
        start_hour = b["start"].strftime("%Y-%m-%d %H:00")
        end_hour = (b["end"]).strftime("%Y-%m-%d %H:00")
        hour_label = f"{start_hour} - {end_hour}"
        status_stats.append({
            "hour_label": hour_label,
            "status_counts": status_counts,
            "jp_count_sum": b["jp_count_sum"],
            "log_name_counts": log_name_counts,
            "duration_min": b["duration_min"],
        })

    return {
        "worker_name": worker_name,
        "worker_status": worker_status,
        "status_stats": status_stats,
    }



# Status information per worker
@router.get("/api/workers_status")
async def get_workers_status(db=Depends(get_async_session)):
    workers = []
    # Fetch up to 100 records with status=running
    stmt_running = select(WorkerStatus).where(WorkerStatus.status == JobStatus.RUNNING.value).order_by(WorkerStatus.last_ping.desc()).limit(100)
    running_workers = (await db.execute(stmt_running)).scalars().all()
    total_running_thread_count = None
    # If fewer than 100 running workers, fetch additional records with other statuses
    if len(running_workers) == 100:
        last_100 = running_workers
        # actual count of running workers
        total_running_thread_count = await get_running_thread_count(db)
    else:
        remaining_limit = 100 - len(running_workers)
        stmt_other = select(WorkerStatus).where(WorkerStatus.status != JobStatus.RUNNING.value).order_by(WorkerStatus.last_ping.desc()).limit(remaining_limit)
        other_workers = (await db.execute(stmt_other)).scalars().all()
        last_100 = running_workers + other_workers
    for w in last_100:
        expected_total_count = (w.end - w.start + 1) if w.end and w.start is not None else 1
        progress = (w.current - w.start) / expected_total_count if expected_total_count > 0 else 0
        workers.append({
            "worker_name": f"{get_worker_emoji(w.worker_name)} {w.worker_name}",
            "log_name": w.log_name,
            "current": w.current,
            "progress": progress,
            "last_ping": w.last_ping.isoformat() if w.last_ping else None,
            "status": w.status,
            "worker_fetched_count": w.current - w.start,
            "last_uploaded_index": getattr(w, 'last_uploaded_index', None),
            "jp_count": w.jp_count,
            "jp_ratio": w.jp_ratio,
            "ip_address": w.ip_address,
            "start": w.start,
            "end": w.end
        })
    threads = total_running_thread_count or len([w for w in last_100 if w.status == JobStatus.RUNNING.value])
    return {
        "summary": {
            "threads": threads,
            "workers": int(threads / len(ORDERED_CATEGORIES)),
            "recent_worker_names": len(set(w['worker_name'] for w in workers)),
            "last_updated": last_100[0].last_ping.isoformat() if last_100 and last_100[0].last_ping else "-",
        },
        "workers": workers
    }

# WorkerStatusAggs全件返却API
async def get_current_worker_status_aggs(db):
    start = datetime.now(JST).replace(minute=0, second=0, microsecond=0)
    end = datetime.now(JST)
    count = await worker_status_range_total_count(end, db, start)
    if count:
        return start, end, await aggregate_worker_status(db, start, end)

@cached(TTLCache(maxsize=1, ttl=600))
@router.get("/api/worker_status_aggs")
async def get_worker_status_aggs(db=Depends(get_async_session)):
    """
    Get all WorkerStatusAggs records (hourly aggregated worker status counts, all JobStatus fields).
    """
    try:
        stmt = select(WorkerStatusAggs).order_by(WorkerStatusAggs.start_time)
        rows = (await db.execute(stmt)).scalars().all()
        aggs = []
        for row in rows:
            aggs.append({
                "start_time": row.start_time.isoformat() if row.start_time else None,
                "end_time": row.end_time.isoformat() if row.end_time else None,
                "total_worker_status_count": getattr(row, "total_worker_status_count", None),
                "completed": getattr(row, "completed", 0),
                "running": getattr(row, "running", 0),
                "dead": getattr(row, "dead", 0),
                "failed": getattr(row, "failed", 0),
                "resume_wait": getattr(row, "resume_wait", 0),
                "skipped": getattr(row, "skipped", 0),
                "worker_name_count": getattr(row, "worker_name_count", 0),
                "log_name_count": getattr(row, "log_name_count", 0),
                "jp_count_sum": getattr(row, "jp_count_sum", 0),
            })
        start, end, current_data = await get_current_worker_status_aggs(db)
        if current_data:
            aggs.append({
                "start_time": start.isoformat(),
                "end_time": end.isoformat(),
                "total_worker_status_count": current_data.get("total_worker_status_count", 0),
                "completed": current_data.get("completed", 0),
                "running": current_data.get("running", 0),
                "dead": current_data.get("dead", 0),
                "failed": current_data.get("failed", 0),
                "resume_wait": current_data.get("resume_wait", 0),
                "skipped": current_data.get("skipped", 0),
                "worker_name_count": current_data.get("worker_name_count", 0),
                "log_name_count": current_data.get("log_name_count", 0),
                "jp_count_sum": current_data.get("jp_count_sum", 0),
            })
        return {
            "worker_status_aggs": aggs,
            "total_records": len(aggs),
            "query_timestamp": datetime.now(JST).isoformat()
        }
    except Exception as e:
        logger.error(e)
        return {
            "error": str(e),
            "worker_status_aggs": [],
            "total_records": 0,
            "query_timestamp": datetime.now(JST).isoformat()
        }
