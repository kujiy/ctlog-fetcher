import asyncio
from datetime import datetime, timedelta

from sqlalchemy import select, func

from src.config import WORKER_LIVENESS_TTL, WORKER_DEAD_THRESHOLD_MINS, JST
from src.manager_api.models import WorkerStatus
from src.share.logger import logger
from src.share.job_status import JobStatus
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
                    select(WorkerStatus).where(
                        WorkerStatus.status.in_([JobStatus.RUNNING.value, JobStatus.RESUME_WAIT.value]),
                        WorkerStatus.last_ping < threshold
                    )
                )
                active_workers = result.scalars().all()
                w: WorkerStatus
                for w in active_workers:
                    # I don't know why but some workers had this status. It must be treated as completed.
                    if w.current in (w.end, w.end + 1):
                        logger.info(f"status={w.status}")
                        w.status = JobStatus.COMPLETED.value
                    ## Digicert comes back, so commenting out the skip logic for now.
                    ## this liveness monitor has been stopped due to a bug. Now we have too many dead workers, so almost jobs gonna be skipped. It's not good.
                    ## maybe after cleaning up the old dead workers, we can enable it again.
                    # elif await should_skip(w.log_name, w.start, w.end):
                    #     # Update the status to SKIPPED
                    #     w.status = JobStatus.SKIPPED.value
                    elif await has_no_ping(threshold, w):
                        w.status = JobStatus.DEAD.value
                    else:
                        raise Exception("Logic error in worker_liveness_monitor")

                await session.commit()
            logger.info(f"  - 2️⃣  - worker_liveness_monitor:sleep_inside_loop={WORKER_LIVENESS_TTL}s")

            # interval between checks
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


async def should_skip(log_name, start, end) -> bool:
    # Use another session to avoid transaction issues
    # If there are more than 3 DEAD or FAILED for the same (log_name, start, end), mark as SKIPPED(means the CT Log API is corrupted)
    async for session in get_async_session():
        # 100% completion judgment: last task may be less than BATCH_SIZE, so check if completed up to sth_end
        count_stmt = (
            select(func.count())
            .select_from(WorkerStatus)
            .where(
                (WorkerStatus.log_name == log_name) &
                (WorkerStatus.start == start) &
                (WorkerStatus.end == end) &
                (WorkerStatus.status.in_([JobStatus.DEAD.value, JobStatus.FAILED.value]))
            )
        )

        count_result = await session.execute(count_stmt)
        dead_count = count_result.scalar()
        return dead_count > 3


async def worker_liveness_monitor_with_sleep():
    logger.info(f"2️⃣  - worker_liveness_monitor_with_sleep - initial sleep:{WORKER_LIVENESS_TTL * 5} seconds")
    # If an API has been dead, wait for a while until all workers send their last_ping. Otherwise, they may be marked as dead immediately.
    await asyncio.sleep(WORKER_LIVENESS_TTL * 5)
    await worker_liveness_monitor()

def start_worker_liveness_monitor():
    logger.info("2️⃣ Starting worker liveness monitor...")
    # if an API has been dead, wait for a while until all workers send their last_ping. Otherwise, they may be marked as dead immediately.
    return asyncio.create_task(worker_liveness_monitor_with_sleep())

if __name__ == '__main__':
    asyncio.run(worker_liveness_monitor())
