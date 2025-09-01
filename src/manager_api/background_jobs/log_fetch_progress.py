import asyncio
from datetime import datetime
from sqlalchemy import select, update, insert
from src.manager_api.models import WorkerStatus, CTLogSTH, LogFetchProgress
from src.config import CT_LOG_ENDPOINTS, LOG_FETCH_PROGRESS_TTL
from src.manager_api.db import get_async_session
from src.share.job_status import JobStatus

import logging

logger = logging.getLogger("log_fetch_progress")

BATCH_SIZE = 16000


async def aggregate_log_fetch_progress():
    # In-memory cache for last min_completed_end per (category, log_name)
    last_completed_map = {}

    while True:
        async for session in get_async_session():
            now = datetime.utcnow()
            logger.info(now.isoformat())
            for category, endpoints in CT_LOG_ENDPOINTS.items():
                for log_name, ct_log_url in endpoints:
                    logger.info(f"Fetching {log_name} progress from {ct_log_url}")
                    # Get latest STH for this log_name
                    sth_end = await sth_by_log_name(log_name, session)

                    # Find min_completed_end using BATCH_SIZE logic, start from last known
                    min_completed_end = last_completed_map.get((category, log_name), None)
                    if sth_end is not None:
                        if min_completed_end is not None:
                            i = min_completed_end + BATCH_SIZE
                        else:
                            i = BATCH_SIZE - 1
                        while i <= sth_end:
                            if await get_completed_worker_status(i, log_name, session):
                                min_completed_end = i
                                i += BATCH_SIZE
                            else:
                                break
                        # Update cache
                        last_completed_map[(category, log_name)] = min_completed_end

                    # Determine fetch_rate
                    fetch_rate, status = await extract_info(min_completed_end, sth_end)

                    # Upsert into LogFetchProgress
                    await upcert_log_fetch_progress(category, fetch_rate, log_name, min_completed_end, now, session,
                                                    status, sth_end)
                    logger.info(f"Updated {log_name} progress from {ct_log_url} as min_completed_end={min_completed_end}, sth_end={sth_end}, fetch_rate={fetch_rate}, status={status}")
        await asyncio.sleep(LOG_FETCH_PROGRESS_TTL)


async def sth_by_log_name(log_name, session):
    sth_stmt = select(CTLogSTH.tree_size).where(
        CTLogSTH.log_name == log_name
    ).order_by(CTLogSTH.fetched_at.desc())
    sth_row = (await session.execute(sth_stmt)).first()
    sth_end = sth_row[0] - 1 if sth_row and sth_row[0] is not None else None
    return sth_end


async def extract_info(min_completed_end, sth_end):
    if min_completed_end is not None and sth_end is not None:
        if sth_end > 0:
            fetch_rate = str(round(min_completed_end / sth_end, 6))
        else:
            fetch_rate = None

        # Determine status
        if min_completed_end >= sth_end:
            status = "completed"
        else:
            status = "in_progress"
    return fetch_rate, status


async def upcert_log_fetch_progress(category, fetch_rate, log_name, min_completed_end, now, session, status, sth_end):
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
                sth_end=sth_end,
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
                sth_end=sth_end,
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
        WorkerStatus.status == JobStatus.COMPLETED.value
    )
    completed = (await session.execute(stmt)).scalars().first()
    return completed


def start_log_fetch_progress():
    asyncio.create_task(aggregate_log_fetch_progress())


if __name__ == '__main__':
    asyncio.run(aggregate_log_fetch_progress())
