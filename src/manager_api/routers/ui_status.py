from asyncache import cached
from cachetools import TTLCache

from src.manager_api.db_query import get_running_thread_count
from src.share.animal import get_worker_emoji
from src.config import JST, BATCH_SIZE, ORDERED_CATEGORIES
from src.manager_api.db import get_async_session
from src.manager_api.models import WorkerLogStat, WorkerStatus
from datetime import datetime, timedelta
from fastapi import Depends, APIRouter
from sqlalchemy import func, select, text
from src.share.job_status import JobStatus

# background jobs

router = APIRouter()



# ranking of workers by total fetched count and .jp count
@router.get("/api/worker_ranking")
async def get_worker_ranking(db=Depends(get_async_session)):
    stmt = select(
        WorkerLogStat.worker_name,
        func.sum(WorkerLogStat.worker_total_count).label('worker_total_count'),
        func.sum(WorkerLogStat.jp_count_sum).label('jp_count_sum')
    ).group_by(WorkerLogStat.worker_name)
    rows = (await db.execute(stmt)).all()
    worker_total_count_ranking = []
    jp_ranking = []
    for r in rows:
        worker_name = f"{get_worker_emoji(r[0])} {r[0]}"
        worker_total_count = r[1]
        jp_count = r[2] or 0
        jp_ratio = (jp_count / worker_total_count) if worker_total_count > 0 else 0
        worker_total_count_ranking.append({
            "worker_name": worker_name,
            "worker_total_count": worker_total_count,
            "jp_count": jp_count,
            "jp_ratio": jp_ratio
        })
        jp_ranking.append({
            "worker_name": worker_name,
            "jp_count": jp_count,
            "jp_ratio": jp_ratio
        })
    worker_total_count_ranking = sorted(worker_total_count_ranking, key=lambda x: x["worker_total_count"], reverse=True)
    jp_ranking = sorted(jp_ranking, key=lambda x: x["jp_count"], reverse=True)
    return {
        "worker_total_count_ranking": worker_total_count_ranking,
        "jp_count_ranking": jp_ranking
    }


# --- get_tree_size with 1-minute cache ---
@router.get("/api/worker_stats/{worker_name}")
async def get_worker_stats(worker_name: str, db=Depends(get_async_session)):
    # 1. WorkerLogStat: sorted by jp_count_sum desc
    stat_stmt = select(WorkerLogStat).where(WorkerLogStat.worker_name == worker_name)
    stat_rows = (await db.execute(stat_stmt)).scalars().all()
    log_stats = sorted(
        [
            {
                "log_name": s.log_name,
                "worker_total_count": s.worker_total_count,
                "jp_count_sum": s.jp_count_sum,
                "last_updated": s.last_updated.isoformat() if s.last_updated else None,
            }
            for s in stat_rows
        ],
        key=lambda x: x["worker_total_count"] or 0,
        reverse=True
    )

    # 2. WorkerStatus: past 24 hours, aggregated hourly
    now = datetime.now(JST)
    since = now - timedelta(hours=24)
    status_stmt = select(WorkerStatus).where(
        WorkerStatus.worker_name == worker_name,
        WorkerStatus.last_ping >= since
    )
    status_rows = (await db.execute(status_stmt)).scalars().all()

    # a bucket for 24 hours, each 1 hour
    buckets = []
    for i in range(24):
        bucket_start = since + timedelta(hours=i)
        bucket_end = bucket_start + timedelta(hours=1)
        buckets.append({
            "start": bucket_start,
            "end": bucket_end,
            "status_counts": {},
            "jp_count_sum": 0,
            "log_name_counts": {},
            "hour_label": bucket_start.strftime("%Y-%m-%d %H:00"),
        })

    # calculate each worker status into the buckets
    for ws in status_rows:
        last_ping = ws.last_ping
        # Add JST if last_ping is offset-naive
        if last_ping is not None and last_ping.tzinfo is None:
            last_ping = last_ping.replace(tzinfo=JST)
        for bucket in buckets:
            if last_ping is not None and bucket["start"] <= last_ping < bucket["end"]:
                # jobs status count
                st = ws.status or "unknown"
                bucket["status_counts"][st] = bucket["status_counts"].get(st, 0) + 1
                # sum of jp_count
                bucket["jp_count_sum"] += ws.jp_count or 0
                # job count per log_name
                ln = ws.log_name or "unknown"
                bucket["log_name_counts"][ln] = bucket["log_name_counts"].get(ln, 0) + 1
                break

    job_status_order = [JobStatus.RUNNING.value, JobStatus.COMPLETED.value, JobStatus.RESUME_WAIT.value, JobStatus.SKIPPED.value, JobStatus.DEAD.value]

    # order by most recent hour first
    buckets_sorted = list(reversed(buckets))

    status_stats = []
    for b in buckets_sorted:
        # status_counts: include all job statuses
        status_counts = {status: b["status_counts"].get(status, 0) for status in job_status_order}
        # log_name_counts: order by count desc
        log_name_counts = dict(sorted(b["log_name_counts"].items(), key=lambda x: x[1], reverse=True))
        # hour_label: "YYYY-MM-DD HH:00 - HH:00"
        start_hour = b["start"].strftime("%Y-%m-%d %H:00")
        end_hour = (b["end"]).strftime("%H:00")
        hour_label = f"{start_hour} - {end_hour}"
        status_stats.append({
            "hour_label": hour_label,
            "status_counts": status_counts,
            "jp_count_sum": b["jp_count_sum"],
            "log_name_counts": log_name_counts,
        })

    return {
        "worker_name": worker_name,
        "log_stats": log_stats,
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
@cached(TTLCache(maxsize=1, ttl=600))
@router.get("/api/worker_status_aggs")
async def get_worker_status_aggs(db=Depends(get_async_session)):
    """
    Get all WorkerStatusAggs records (hourly aggregated worker status counts, all JobStatus fields).
    """
    from src.manager_api.models import WorkerStatusAggs
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
        return {
            "worker_status_aggs": aggs,
            "total_records": len(aggs),
            "query_timestamp": datetime.now(JST).isoformat()
        }
    except Exception as e:
        return {
            "error": str(e),
            "worker_status_aggs": [],
            "total_records": 0,
            "query_timestamp": datetime.now(JST).isoformat()
        }
