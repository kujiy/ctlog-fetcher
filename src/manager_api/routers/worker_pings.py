import logging
import os
import json
from random import randint

from fastapi import Depends, APIRouter, Request
from src.config import JST, BATCH_SIZE
from src.manager_api.db import get_async_session
from src.manager_api import locks
from src.manager_api.db_query import too_slow_duration_by_log_name
from src.manager_api.models import WorkerLogStat, WorkerStatus
from sqlalchemy import select
from datetime import datetime
from src.share.job_status import JobStatus
from src.config import WORKER_CTLOG_REQUEST_INTERVAL_SEC, WORKER_PING_INTERVAL_SEC
from src.manager_api.base_models import WorkerPingModel, WorkerPingBaseModel, WorkerErrorModel
from src.share.utils import extract_ip_address_hash

router = APIRouter()



"""
a worker has failed_files and pending_files as query parameters.
These query parameters are not processed by the API server at all. They are only for access log purposes.
"""
# ping: only running
async def get_ctlog_request_interval_sec(db, log_name, ip_address_hash: str) -> int:
    ws: WorkerStatus = await too_slow_duration_by_log_name(db, log_name, ip_address_hash)
    if ws:
        # duration_min = ((datetime.now(JST) - ws.created_at.astimezone(JST)).total_seconds()) / 60 / 10
        return randint(WORKER_CTLOG_REQUEST_INTERVAL_SEC, WORKER_CTLOG_REQUEST_INTERVAL_SEC * 10)  # The worker keeps this interval until the next WORKER_PING_INTERVAL_SEC
    return WORKER_CTLOG_REQUEST_INTERVAL_SEC


@router.post("/api/worker/ping")
async def worker_ping(data: WorkerPingModel, request: Request, db=Depends(get_async_session)):
    # await update_worker_status_and_summary(data, db, JobStatus.RUNNING.value, request)
    return {
        "ping_interval_sec": WORKER_PING_INTERVAL_SEC,
        "ctlog_request_interval_sec": await get_ctlog_request_interval_sec(db, data.log_name, extract_ip_address_hash(request))
    }

# completed: when a job is completed
@router.post("/api/worker/completed")
async def worker_completed(data: WorkerPingBaseModel, request: Request, db=Depends(get_async_session)):
    return await update_worker_status_and_summary(data, db, JobStatus.COMPLETED.value, request)

# failed: when a job is failed due to: CT Log API has corrupted data, network error, etc.
@router.post("/api/worker/failed")
async def worker_failed(data: WorkerPingBaseModel, request: Request, db=Depends(get_async_session)):
    return await update_worker_status_and_summary(data, db, JobStatus.FAILED.value, request)


async def update_worker_status_and_summary(data: WorkerPingModel | WorkerPingBaseModel, db, status_value, request: Request):
    lock_key = (data.worker_name, data.log_name, data.start, data.end)
    async with locks[lock_key]:
        ws_stmt = select(WorkerStatus).where(
            WorkerStatus.worker_name == data.worker_name,
            WorkerStatus.log_name == data.log_name,
            WorkerStatus.start == data.start,
            WorkerStatus.end == data.end,
            # Guard: If already marked as completed etc, do not overwrite with later PINGs
            WorkerStatus.status != JobStatus.COMPLETED.value
        ).order_by(WorkerStatus.last_ping.desc())
        ws = (await db.execute(ws_stmt)).scalars().first()
        if ws:
            now = datetime.now(JST)
            ws.worker_name = data.worker_name
            ws.current = data.current
            ws.status = status_value
            ws.last_ping = now
            ws.ip_address = data.ip_address or extract_ip_address_hash(request)
            ws.last_uploaded_index = data.last_uploaded_index
            ws.jp_count = data.jp_count
            ws.jp_ratio = data.jp_ratio
            ws.total_retries = data.total_retries
            ws.max_retry_after = data.max_retry_after
            if status_value == JobStatus.COMPLETED.value and ws.created_at:
                ws.duration_sec = (now - ws.created_at.astimezone(JST)).total_seconds()
            await db.commit()

            # update the summary table
            stat_stmt = select(WorkerLogStat).where(
                WorkerLogStat.log_name == ws.log_name,
                WorkerLogStat.worker_name == ws.worker_name
            )
            stat = (await db.execute(stat_stmt)).scalars().first()
            if not stat:
                stat = WorkerLogStat(log_name=ws.log_name, worker_name=ws.worker_name)
                db.add(stat)
            # Add jp_count_sum only when status is COMPLETED
            if status_value == JobStatus.COMPLETED.value:
                stat.worker_total_count = (stat.worker_total_count or 0) + (data.end - data.start + 1)
                stat.jp_count_sum = (stat.jp_count_sum or 0) + (ws.jp_count or 0)
            stat.last_updated = datetime.now(JST)
            await db.commit()
    return {"message": "ok"}


@router.post("/api/worker/error")
async def worker_error(data: WorkerErrorModel):
    # Add to worker_errors.log (JSON Lines format)
    log_path = os.path.join(os.path.dirname(__file__), "worker_errors.log")
    try:
        with open(log_path, "a") as f:
            f.write(json.dumps(data.model_dump(), ensure_ascii=False) + "\n")
    except Exception as e:
        logging.getLogger("worker_error_api").error(f"Failed to write worker error: {e}")
    return {"message": "ok"}


