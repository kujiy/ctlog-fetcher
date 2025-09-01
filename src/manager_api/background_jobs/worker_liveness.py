import asyncio
from datetime import datetime, timedelta, timezone

from src.config import WORKER_LIVENESS_TTL
from .. import models
from ..db import get_async_session
JST = timezone(timedelta(hours=9))

async def worker_liveness_monitor():
    """
    Every minute, monitor all WorkerStatus and update running/resume_wait workers to dead if last_ping is more than 20 minutes ago.
    """
    while True:
        async for session in get_async_session():
            now = datetime.now(JST)
            threshold = now - timedelta(minutes=WORKER_DEAD_THRESHOLD_MINS)
            # print(threshold)
            result = await session.execute(
                models.WorkerStatus.__table__.select().where(
                    models.WorkerStatus.status.in_(['running', 'resume_wait'])
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
                # print(update_needed)
                if update_needed:
                    await session.execute(
                        models.WorkerStatus.__table__.update()
                        .where(models.WorkerStatus.id == w.id)
                        .values(status='dead')
                    )
            await session.commit()
        await asyncio.sleep(WORKER_LIVENESS_TTL)

def start_worker_liveness_monitor():
    asyncio.create_task(worker_liveness_monitor())

if __name__ == '__main__':
    asyncio.run(worker_liveness_monitor())
