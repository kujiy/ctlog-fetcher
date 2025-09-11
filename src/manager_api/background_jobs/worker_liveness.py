import asyncio
import time
from datetime import datetime, timedelta, timezone
from sqlalchemy import select

from src.config import WORKER_LIVENESS_TTL, WORKER_DEAD_THRESHOLD_MINS, JST
from src.share.logger import logger
from src.share.job_status import JobStatus
from .. import models
from ..db import get_async_session

async def worker_liveness_monitor():
    """
    Every minute, monitor all WorkerStatus and update running/resume_wait workers to dead if last_ping is more than n minutes ago.
    """
    try:
        while True:
            logger.info("  - 2️⃣  - worker_liveness_monitor")
            async for session in get_async_session():
                now = datetime.now(JST)
                threshold = now - timedelta(minutes=WORKER_DEAD_THRESHOLD_MINS)
                result = await session.execute(
                    select(models.WorkerStatus).where(
                        models.WorkerStatus.status.in_([JobStatus.RUNNING.value, JobStatus.RESUME_WAIT.value])
                    )
                )
                workers = result.scalars().all()
                for w in workers:
                    if await has_no_ping(threshold, w):
                        w.status = JobStatus.DEAD.value
                    else:
                        if await should_skip(session, w):
                            # Update the status to SKIPPED
                            w.status = JobStatus.SKIPPED.value
                await session.commit()
            logger.info(f"  - 2️⃣  - worker_liveness_monitor:sleep_inside_loop={WORKER_LIVENESS_TTL}s")
            await asyncio.sleep(WORKER_LIVENESS_TTL)
    except asyncio.CancelledError:
        # Graceful shutdown
        return


async def has_no_ping(threshold, w) -> bool:
    offset_aware_last_ping = w.last_ping
    if w.last_ping and w.last_ping.tzinfo is None:
        offset_aware_last_ping = w.last_ping.replace(tzinfo=JST)
    if w.last_ping is None:
        return True
    elif offset_aware_last_ping < threshold:
        return True
    return False


async def should_skip(session, w) -> bool:
    # 100% completion judgment: last task may be less than BATCH_SIZE, so check if completed up to sth_end
    count_stmt = models.WorkerStatus.__table__.count().where(
        (models.WorkerStatus.log_name == w.log_name) &
        (models.WorkerStatus.start == w.start) &
        (models.WorkerStatus.end == w.end) &
        (models.WorkerStatus.status.in_([JobStatus.DEAD.value, JobStatus.FAILED.value]))
    )
    count_result = await session.execute(count_stmt)
    dead_count = count_result.scalar()
    return dead_count > 3


async def worker_liveness_monitor_with_sleep():
    logger.info(f"2️⃣  - worker_liveness_monitor_with_sleep - initial sleep:{WORKER_LIVENESS_TTL * 5} seconds")
    await asyncio.sleep(WORKER_LIVENESS_TTL * 5)  # interval between fetches
    await worker_liveness_monitor()

def start_worker_liveness_monitor():
    logger.info("2️⃣ Starting worker liveness monitor...")
    # if an API has been dead, wait for a while until all workers send their last_ping. Otherwise, they may be marked as dead immediately.
    return asyncio.create_task(worker_liveness_monitor_with_sleep())

if __name__ == '__main__':
    asyncio.run(worker_liveness_monitor())
