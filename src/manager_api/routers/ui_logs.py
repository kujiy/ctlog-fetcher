from src.config import ETA_BASE_DATE
from src.config import JST, BATCH_SIZE
from src.manager_api.db import get_async_session
from src.manager_api import locks
from src.manager_api.models import WorkerLogStat, WorkerStatus, LogFetchProgress, LogFetchProgressHistory
from datetime import datetime, timedelta
from fastapi import Depends, APIRouter
from sqlalchemy import func, select
from src.share.job_status import JobStatus
import datetime as dt

# background jobs
from src.manager_api.background_jobs.unique_cert_counter import get_unique_cert_counter_count


router = APIRouter()



# --- Overall Progress API ---
@router.get("/api/logs_summary")
async def get_logs_summary(db=Depends(get_async_session)):
    # Get sum from LogFetchProgress table using ORM-style result access
    stmt = select(
        func.sum(LogFetchProgress.sth_end).label("total_tree_size"),
        func.sum(LogFetchProgress.min_completed_end).label("fetched_tree_size"),
        (func.sum(LogFetchProgress.min_completed_end) / func.nullif(func.sum(LogFetchProgress.sth_end), 0)).label("fetched_rate")
    )
    result = await db.execute(stmt)
    row = result.first()

    total_tree_size = row.total_tree_size if row and row.total_tree_size is not None else 0
    fetched_tree_size = row.fetched_tree_size if row and row.fetched_tree_size is not None else 0
    fetched_rate = row.fetched_rate if row and row.fetched_rate is not None else 0

    # --- ETA (days) ---
    today = ETA_BASE_DATE
    now = dt.datetime.now(JST).date()
    days_elapsed = (now - today).days if (now - today).days > 0 else 1
    eta_days = None
    if fetched_rate > 0 and fetched_rate < 1:
        eta_days = int(days_elapsed * (1 - fetched_rate) / fetched_rate)
    elif fetched_rate >= 1:
        eta_days = 0

    # --- Unique .jp count ---
    unique_jp_count = await get_unique_cert_counter_count()

    return {
        "total_tree_size": total_tree_size,
        "fetched_tree_size": fetched_tree_size,
        "fetched_rate": fetched_rate,
        "eta_days": eta_days,
        "unique_jp_count": unique_jp_count,
    }



# Progress information per log
@router.get("/api/logs_progress")
async def get_logs_progress(db=Depends(get_async_session)):
    # Fetch all LogFetchProgress records
    progress_rows = (await db.execute(select(LogFetchProgress).order_by(LogFetchProgress.category, LogFetchProgress.log_name))).scalars().all()
    log_names = [p.log_name for p in progress_rows]

    # Fetch latest snapshot for all log_names from LogFetchProgressHistory
    from sqlalchemy import desc
    latest_snapshots = {}
    if log_names:
        # Get latest snapshot_timestamp for each log_name
        subq = (
            select(
                LogFetchProgressHistory.log_name,
                func.max(LogFetchProgressHistory.snapshot_timestamp).label("max_ts")
            )
            .where(LogFetchProgressHistory.log_name.in_(log_names))
            .group_by(LogFetchProgressHistory.log_name)
            .subquery()
        )
        # Join to get full row for each latest snapshot
        stmt = (
            select(LogFetchProgressHistory)
            .join(subq, (LogFetchProgressHistory.log_name == subq.c.log_name) &
                        (LogFetchProgressHistory.snapshot_timestamp == subq.c.max_ts))
        )
        history_rows = (await db.execute(stmt)).scalars().all()
        for h in history_rows:
            latest_snapshots[h.log_name] = h

    logs = []
    for p in progress_rows:
        log_dict = {k: v for k, v in p.__dict__.items() if not k.startswith('_')}
        # diff calculation with latest snapshot
        diff = {}
        h = latest_snapshots.get(p.log_name)
        if h:
            diff["sth_end"] = (p.sth_end or 0) - (h.sth_end or 0)
            diff["min_completed_end"] = (p.min_completed_end or 0) - (h.min_completed_end or 0)
        else:
            diff["sth_end"] = None
            diff["min_completed_end"] = None
        log_dict["diff"] = diff
        logs.append(log_dict)
    return logs


@router.get("/api/log_fetch_progress_history/{log_name}")
async def get_log_fetch_progress_history(log_name: str, db=Depends(get_async_session)):
    two_weeks_ago = datetime.now(JST) - timedelta(weeks=2)
    stmt = select(LogFetchProgressHistory).where(
        LogFetchProgressHistory.log_name == log_name,
        LogFetchProgressHistory.snapshot_timestamp >= two_weeks_ago
    ).order_by(LogFetchProgressHistory.snapshot_timestamp)
    history = (await db.execute(stmt)).scalars().all()

    def to_dict(entry):
        d = {k: v for k, v in entry.__dict__.items() if not k.startswith('_')}
        # datetime型はisoformatで返す
        for k, v in d.items():
            if isinstance(v, datetime):
                d[k] = v.isoformat()
        return d

    response = [to_dict(entry) for entry in history]
    return {"log_name": log_name, "history": response}


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

