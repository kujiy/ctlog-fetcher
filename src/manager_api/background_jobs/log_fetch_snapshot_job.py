import asyncio
from datetime import datetime, timedelta, timezone
from logging import getLogger
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from src.manager_api.models import LogFetchProgress, LogFetchProgressHistory, Base

logger = getLogger("uvicorn")
JST = timezone(timedelta(hours=9))

# Database engine setup
engine = create_engine('mysql+pymysql://root@127.0.0.1:3306/ct')
Session = sessionmaker(bind=engine)

async def save_log_fetch_progress_snapshot():
    session = Session()
    try:
        # Fetch all rows from log_fetch_progress
        rows = session.query(LogFetchProgress).all()

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

        session.commit()
        logger.info(f"Snapshot saved at {snapshot_timestamp}")
    except Exception as e:
        logger.error(f"Error saving snapshot: {e}")
        session.rollback()
    finally:
        session.close()

async def should_save_snapshot():
    session = Session()
    try:
        # Check the latest snapshot timestamp
        last_snapshot = session.query(LogFetchProgressHistory.snapshot_timestamp).order_by(
            LogFetchProgressHistory.snapshot_timestamp.desc()).first()

        if not last_snapshot:
            return True

        # Check if 6 hours have passed since the last snapshot
        now = datetime.now(JST)
        return (now - last_snapshot[0]).total_seconds() >= 6 * 3600
    except Exception as e:
        logger.error(f"Error checking snapshot condition: {e}")
        return False
    finally:
        session.close()

async def background_log_fetch_snapshot_job():
    while True:
        try:
            if await should_save_snapshot():
                await save_log_fetch_progress_snapshot()
            await asyncio.sleep(3600)  # Check every hour
        except Exception as e:
            logger.error(f"Background job error: {e}")
            await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(save_log_fetch_progress_snapshot())