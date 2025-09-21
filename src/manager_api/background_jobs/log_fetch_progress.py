import asyncio
from datetime import datetime

from sqlalchemy import select, update, insert

from src.config import CT_LOG_ENDPOINTS, LOG_FETCH_PROGRESS_TTL, BATCH_SIZE, JST
from src.manager_api.db import get_async_session
from src.manager_api.models import WorkerStatus, CTLogSTH, LogFetchProgress, LogFetchProgressStatus
from src.share.job_status import JobStatus
from src.share.logger import logger


async def aggregate_log_fetch_progress():
    # In-memory cache for last min_completed_end per (category, log_name)
    last_completed_map = {}

    try:
        while True:
            logger.info("  - 4️⃣  -  aggregate_log_fetch_progress:while")
            async for session in get_async_session():
                now = datetime.now(JST)
                for category, endpoints in CT_LOG_ENDPOINTS.items():
                    for log_name, ct_log_url in endpoints:
                        logger.debug(f"Fetching {log_name} progress from {ct_log_url}")
                        # Get latest STH for this log_name
                        sth_end = await sth_by_log_name(log_name, session)
                        max_end = sth_end - 1

                        # Find min_completed_end using BATCH_SIZE logic, start from last known
                        min_completed_end = await get_min_completed_end(category, last_completed_map, log_name, session)
                        if max_end is not None:
                            if min_completed_end is not None:
                                i = min_completed_end + BATCH_SIZE
                            else:
                                i = BATCH_SIZE - 1
                            # speed up by fetching all completed ends at once
                            completed_ends = await get_all_completed_worker_ends(log_name, min_completed_end, session)
                            # set for O(1) lookups that speeds up the loop
                            completed_ends_set = set(completed_ends)
                            while i <= max_end:
                                if i in completed_ends_set:
                                    min_completed_end = i
                                    i += BATCH_SIZE
                                else:
                                    break
                            # 100% completion judgment: The last task may be less than BATCH_SIZE, so check if completed up to max_end(sth_end - 1)
                            if 0 < i - max_end <= BATCH_SIZE and max_end in completed_ends_set:
                                min_completed_end = max_end
                            # Update cache
                            last_completed_map[(category, log_name)] = min_completed_end

                        # Determine fetch_rate
                        fetch_rate, status = await extract_info(min_completed_end, max_end)

                        # Upsert into LogFetchProgress
                        await upcert_log_fetch_progress(category, fetch_rate, log_name, min_completed_end, now, session,
                                                        status, max_end)
                        logger.debug(f"Updated {log_name} progress from {ct_log_url} as min_completed_end={min_completed_end}, sth_end={sth_end}, fetch_rate={fetch_rate}, status={status}")
            logger.info(f"  - 4️⃣  -  aggregate_log_fetch_progress:sleep {LOG_FETCH_PROGRESS_TTL} seconds")
            await asyncio.sleep(LOG_FETCH_PROGRESS_TTL)
    except asyncio.CancelledError:
        # Graceful shutdown
        return


async def get_min_completed_end(category, last_completed_map, log_name, session):
    min_completed_end = last_completed_map.get((category, log_name), None)
    if min_completed_end is None:
        # Try to get from DB
        min_completed_end = await get_log_fetch_progress_min_completed_end(category, log_name, session)
    if min_completed_end is None:
        # Fallback to BATCH_SIZE - 1
        min_completed_end = BATCH_SIZE - 1
    return min_completed_end


async def sth_by_log_name(log_name, session):
    sth_stmt = select(CTLogSTH.tree_size).where(
        CTLogSTH.log_name == log_name
    ).order_by(CTLogSTH.fetched_at.desc())
    sth_row = (await session.execute(sth_stmt)).first()
    # tree_size is 1-based, convert to 0-based index
    sth_end = sth_row[0] if sth_row and sth_row[0] is not None else None
    return sth_end


async def extract_info(min_completed_end, max_end):
    if min_completed_end is not None and max_end is not None:
        if max_end > 0:
            fetch_rate = round(min_completed_end / max_end, 6)
        else:
            fetch_rate = None

        # Determine status
        if min_completed_end >= max_end:
            status = LogFetchProgressStatus.COMPLETED.value
        else:
            status = LogFetchProgressStatus.IN_PROGRESS.value
    return fetch_rate, status


async def upcert_log_fetch_progress(category, fetch_rate, log_name, min_completed_end, now, session, status, max_end):
    existing_stmt = select(LogFetchProgress).where(
        LogFetchProgress.category == category,
        LogFetchProgress.log_name == log_name
    )
    existing = (await session.execute(existing_stmt)).scalars().first()
    if existing:
        await session.execute(
            update(LogFetchProgress)
            .where(LogFetchProgress.id == existing.id)
            .values(
                min_completed_end=min_completed_end,
                sth_end=max_end,
                fetch_rate=fetch_rate,
                status=status,
                updated_at=now
            )
        )
    else:
        await session.execute(
            insert(LogFetchProgress).values(
                category=category,
                log_name=log_name,
                min_completed_end=min_completed_end,
                sth_end=max_end,
                fetch_rate=fetch_rate,
                status=status,
                updated_at=now
            )
        )
    await session.commit()


async def get_completed_worker_status(i, log_name, session):
    stmt = select(WorkerStatus).where(
        WorkerStatus.log_name == log_name,
        WorkerStatus.end == i,
        WorkerStatus.status.in_([JobStatus.COMPLETED.value, JobStatus.SKIPPED.value])
    )
    completed = (await session.execute(stmt)).scalars().first()
    return completed

# 新規: 一括取得
async def get_all_completed_worker_ends(log_name, min_completed_end, session):
    stmt = select(WorkerStatus.end).where(
        WorkerStatus.log_name == log_name,
        WorkerStatus.end > min_completed_end,
        WorkerStatus.status.in_([JobStatus.COMPLETED.value, JobStatus.SKIPPED.value])
    )
    result = await session.execute(stmt)
    return [row[0] for row in result.fetchall()]

# Helper: fetch min_completed_end from LogFetchProgress for cold start
async def get_log_fetch_progress_min_completed_end(category, log_name, session):
    stmt = select(LogFetchProgress.min_completed_end).where(
        LogFetchProgress.category == category,
        LogFetchProgress.log_name == log_name
    ).order_by(LogFetchProgress.updated_at.desc())
    row = (await session.execute(stmt)).first()
    return row[0] if row and row[0] is not None else None


async def log_fetch_progress_wrapper():
    logger.info("4️⃣  -  log_fetch_progress_wrapper")
    await aggregate_log_fetch_progress()

def start_log_fetch_progress():
    logger.info("4️⃣ start_log_fetch_progress...")
    return asyncio.create_task(log_fetch_progress_wrapper())


if __name__ == '__main__':
    asyncio.run(aggregate_log_fetch_progress())
