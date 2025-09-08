import asyncio
from datetime import datetime, timedelta, timezone
from logging import getLogger
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine, select

from src.manager_api.db import get_async_session
from src.manager_api.models import LogFetchProgress, LogFetchProgressHistory, Base

logger = getLogger("uvicorn")
JST = timezone(timedelta(hours=9))


async def save_log_fetch_progress_snapshot(session):
    try:
        # Fetch all rows from log_fetch_progress
        stmt = select(LogFetchProgress)
        rows = (await session.execute(stmt)).scalars().all()

        # Add snapshot_timestamp and insert into log_fetch_progress_history
        snapshot_timestamp = datetime.now(JST)
        for row in rows:
            history_entry = LogFetchProgressHistory(
                category=row.category,
                log_name=row.log_name,
                min_completed_end=row.min_completed_end,
                sth_end=row.sth_end,
                fetch_rate=row.fetch_rate,
                status=row.status,
                updated_at=row.updated_at,
                snapshot_timestamp=snapshot_timestamp
            )
            session.add(history_entry)

        await session.commit()
        logger.info(f"Snapshot saved at {snapshot_timestamp}")
    except Exception as e:
        logger.error(f"Error saving snapshot: {e}")
        session.rollback()

async def should_save_snapshot(session):
    try:
        # Check the latest snapshot timestamp
        stmt = select(LogFetchProgressHistory.snapshot_timestamp)\
            .order_by(LogFetchProgressHistory.snapshot_timestamp.desc())
        last_snapshot = (await session.execute(stmt)).first()

        if not last_snapshot:
            return True

        # Check if 6 hours have passed since the last snapshot
        now = datetime.now(JST)
        return (now - last_snapshot[0].replace(tzinfo=JST)).total_seconds() >= 6 * 3600
    except Exception as e:
        logger.error(f"Error checking snapshot condition: {e}")
        return False

async def background_log_fetch_snapshot_job():
    logger.info("5️⃣ Background log fetch snapshot job started")
    while True:
        async for session in get_async_session():
            try:
                if await should_save_snapshot(session):
                    await save_log_fetch_progress_snapshot(session)
            except Exception as e:
                logger.error(f"Background job error: {e}")
            await asyncio.sleep(3600)

def start_log_fetch_snapshot_job():
    logger.info("5️⃣ Starting log fetch snapshot job")
    return asyncio.create_task(background_log_fetch_snapshot_job())


if __name__ == "__main__":
    asyncio.run(background_log_fetch_snapshot_job())
