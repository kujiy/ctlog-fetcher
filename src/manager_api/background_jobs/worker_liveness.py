import asyncio
from datetime import datetime, time, timedelta, timezone

from src.config import WORKER_LIVENESS_TTL, WORKER_DEAD_THRESHOLD_MINS
from src.share.job_status import JobStatus
from .. import models
from ..db import get_async_session
JST = timezone(timedelta(hours=9))

async def worker_liveness_monitor():
    """
    Every minute, monitor all WorkerStatus and update running/resume_wait workers to dead if last_ping is more than 20 minutes ago.
    """
    try:
        while True:
            async for session in get_async_session():
                now = datetime.now(JST)
                threshold = now - timedelta(minutes=WORKER_DEAD_THRESHOLD_MINS)
                result = await session.execute(
                    models.WorkerStatus.__table__.select().where(
                        models.WorkerStatus.status.in_([JobStatus.RUNNING.value, JobStatus.RESUME_WAIT.value])
                    )
                )
                workers = result.fetchall()
                for row in workers:
                    w = row
                    offset_aware_last_ping = w.last_ping
                    if w.last_ping is not None and w.last_ping.tzinfo is None:
                        offset_aware_last_ping = w.last_ping.replace(tzinfo=JST)
                    update_needed = False
                    if w.last_ping is None:
                        update_needed = True
                    elif offset_aware_last_ping < threshold:
                        update_needed = True
                    if update_needed:
                        await session.execute(
                            models.WorkerStatus.__table__.update()
                            .where(models.WorkerStatus.id == w.id)
                            .values(status=JobStatus.DEAD.value)
                        )
                await session.commit()
            await asyncio.sleep(WORKER_LIVENESS_TTL)
    except asyncio.CancelledError:
        # Graceful shutdown
        return

def start_worker_liveness_monitor():
    time.sleep(WORKER_LIVENESS_TTL * 10)  # if an API has been dead, wait for a while until all workers send their last_ping. Otherwise, they may be marked as dead immediately.
    return asyncio.create_task(worker_liveness_monitor())

if __name__ == '__main__':
    asyncio.run(worker_liveness_monitor())
