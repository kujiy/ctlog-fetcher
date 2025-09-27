import datetime as dt
from datetime import datetime, timedelta

from fastapi import Depends, APIRouter
from sqlalchemy import func, select

from src.config import ETA_BASE_DATE
from src.config import JST
# background jobs
from src.manager_api.db import get_async_session
from src.manager_api.models import WorkerStatus, LogFetchProgress, LogFetchProgressHistory

router = APIRouter()



# --- Overall Progress API ---
async def count_ip_address(db):
    # SELECT distinct(ip_address) FROM ct.worker_status where last_ping > JST two hours ago
    stmt = select(func.count(func.distinct(WorkerStatus.ip_address))).where(
        WorkerStatus.last_ping >= datetime.now(JST) - timedelta(hours=2)
    )
    result = await db.execute(stmt)
    count = result.scalar()
    return count if count is not None else 0


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

    # --- ETA (timestamp) ---
    eta_base_datetime = dt.datetime.combine(ETA_BASE_DATE, dt.time.min).replace(tzinfo=JST)
    now_datetime = dt.datetime.now(JST)
    time_elapsed = now_datetime - eta_base_datetime
    eta_timestamp = None
    if fetched_rate > 0 and fetched_rate < 1:
        # Calculate remaining time based on elapsed time and progress rate
        time_elapsed_seconds = time_elapsed.total_seconds()
        total_estimated_seconds = time_elapsed_seconds / float(fetched_rate)
        remaining_seconds = total_estimated_seconds - time_elapsed_seconds
        remaining_time = timedelta(seconds=remaining_seconds)
        eta_timestamp = (now_datetime + remaining_time).isoformat()
    elif fetched_rate >= 1:
        eta_timestamp = now_datetime.isoformat()

    # --- Unique .jp count ---
    unique_jp_count = 0  #TODO
    ip_address_count = await count_ip_address(db)
    return {
        "total_tree_size": total_tree_size,
        "fetched_tree_size": fetched_tree_size,
        "fetched_rate": fetched_rate,
        "eta_timestamp": eta_timestamp,
        "unique_jp_count": unique_jp_count,
        "ip_address_count": ip_address_count,
    }



# Progress information per log
@router.get("/api/logs_progress")
async def get_logs_progress(db=Depends(get_async_session)):
    # Fetch all LogFetchProgress records
    progress_rows = (await db.execute(select(LogFetchProgress).order_by(LogFetchProgress.category, LogFetchProgress.log_name))).scalars().all()
    log_names = [p.log_name for p in progress_rows]

    # Fetch latest snapshot for all log_names from LogFetchProgressHistory
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
        h = latest_snapshots.get(p.log_name)
        if h:
            diff = {
                "snapshot_timestamp": h.snapshot_timestamp,
                "sth_end": (p.sth_end or 0) - (h.sth_end or 0),
                "min_completed_end": (p.min_completed_end or 0) - (h.min_completed_end or 0)
            }
        else:
            diff = {
                "snapshot_timestamp": 0,
                "sth_end": 0,
                "min_completed_end": 0
            }
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
