import logging
import os
import json
from fastapi import Depends, APIRouter
from src.config import JST, BATCH_SIZE
from src.manager_api.db import get_async_session
from src.manager_api import locks
from src.manager_api.models import WorkerLogStat, WorkerStatus
from sqlalchemy import select
from datetime import datetime
from src.share.job_status import JobStatus
from src.config import WORKER_CTLOG_REQUEST_INTERVAL_SEC, WORKER_PING_INTERVAL_SEC
from src.manager_api.base_models import WorkerPingModel, WorkerPingBaseModel, WorkerErrorModel

router = APIRouter()



"""
a worker has failed_files and pending_files as query parameters.
These query parameters are not processed by the API server at all. They are only for access log purposes.
"""
# ping: only running
@router.post("/api/worker/ping")
async def worker_ping(data: WorkerPingModel, db=Depends(get_async_session)):
    await update_worker_status_and_summary(data, db, JobStatus.RUNNING.value)
    return {
        "ping_interval_sec": WORKER_PING_INTERVAL_SEC,
        "ctlog_request_interval_sec": WORKER_CTLOG_REQUEST_INTERVAL_SEC
    }

# completed: when a job is completed
@router.post("/api/worker/completed")
async def worker_completed(data: WorkerPingBaseModel, db=Depends(get_async_session)):
    return await update_worker_status_and_summary(data, db, JobStatus.COMPLETED.value)

# failed: when a job is failed due to: CT Log API has corrupted data, network error, etc.
@router.post("/api/worker/failed")
async def worker_failed(data: WorkerPingBaseModel, db=Depends(get_async_session)):
    return await update_worker_status_and_summary(data, db, JobStatus.FAILED.value)



async def update_worker_status_and_summary(data: WorkerPingModel | WorkerPingBaseModel, db, status_value):
    lock_key = (data.worker_name, data.log_name, data.start, data.end)
    async with locks[lock_key]:
        ws_stmt = select(WorkerStatus).where(
            WorkerStatus.worker_name == data.worker_name,
            WorkerStatus.log_name == data.log_name,
            WorkerStatus.start == data.start,
            WorkerStatus.end == data.end,
            # Guard: If already marked as completed etc, do not overwrite with later PINGs
            WorkerStatus.status == JobStatus.RUNNING.value
        )
        ws = (await db.execute(ws_stmt)).scalars().first()
        if ws:
            ws.worker_name = data.worker_name
            ws.current = data.current
            ws.status = status_value
            ws.last_ping = datetime.now(JST)
            ws.ip_address = data.ip_address
            ws.last_uploaded_index = data.last_uploaded_index
            ws.jp_count = data.jp_count
            ws.jp_ratio = data.jp_ratio
            await db.commit()
            # update the summary table
            stat_stmt = select(WorkerLogStat).where(
                WorkerLogStat.log_name==ws.log_name,
                WorkerLogStat.worker_name==ws.worker_name
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


