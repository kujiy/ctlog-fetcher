import asyncio
from datetime import datetime, timedelta

from sqlalchemy import select, func, and_
from src.config import JST
from src.manager_api.db_query import worker_status_range_total_count, aggregate_worker_status
from src.manager_api.models import WorkerStatusAggs
from src.share.logger import logger
from src.manager_api.db import get_async_session

START_TIME = datetime(2025, 8, 25, 0, 0, 0, tzinfo=JST)

async def get_latest_agg_time(session):
    stmt = select(func.max(WorkerStatusAggs.end_time))
    result = await session.execute(stmt)
    latest = result.scalar()
    return latest.replace(tzinfo=JST) if latest and latest.tzinfo is None else latest

def get_next_hour_range(latest_agg_time):
    if latest_agg_time is None:
        start = START_TIME
    else:
        # latest_agg_timeがnaiveならJSTを付与
        if latest_agg_time.tzinfo is None:
            start = latest_agg_time.replace(tzinfo=JST)
        else:
            start = latest_agg_time.astimezone(JST)
    end = start + timedelta(hours=1)
    return start, end


async def worker_status_aggs():
    while True:
        logger.info(f"  -  6️⃣ worker_status_aggs")
        async for session in get_async_session():
            try:
                latest_agg_time = await get_latest_agg_time(session)
                target_end_time = datetime.now(JST).replace(minute=0, second=0, microsecond=0)
                logger.info(f"      -  6️⃣ Latest agg time: {latest_agg_time}, Target End time: {target_end_time}")
                while True:
                    start, end = get_next_hour_range(latest_agg_time)
                    # start, end, target_time すべてJSTのoffset-aware
                    if end > target_end_time:
                        logger.info(f"      -  6️⃣ End time {end} exceeds target time {target_end_time}, breaking loop.")
                        break
                    count = await worker_status_range_total_count(end, session, start)
                    if count == 0:
                        logger.info(f"No data to aggregate for {start} - {end}")
                        await register_zero(end, session, start)
                        latest_agg_time = end
                        continue

                    agg = await aggregate_worker_status(session, start, end)
                    if agg is not None:
                        ws_agg = WorkerStatusAggs(
                            start_time=start,
                            end_time=end,
                            **agg
                        )
                        session.add(ws_agg)
                        print(f"Aggregated {start} - {end}")
                    latest_agg_time = end
                await session.commit()
                await session.close()
            except Exception as e:
                print("[❌ WorkerStatusAggs ]Error:", e)
                await session.rollback()
                await session.close()
            logger.info(f"      - 6️⃣ worker_status_aggs - sleep_before_loop=600s")
            await asyncio.sleep(600)


async def register_zero(end, session, start):
    ws_agg = WorkerStatusAggs(
        start_time=start,
        end_time=end,
        total_worker_status_count=0,
        completed=0,
        running=0,
        dead=0,
        failed=0,
        resume_wait=0,
        skipped=0,
        worker_name_count=0,
        log_name_count=0,
        jp_count_sum=0,
    )
    session.add(ws_agg)


async def worker_status_aggs_wrapper():
    await worker_status_aggs()

def start_worker_status_aggs():
    logger.info("6️⃣ Starting worker_status_aggs_wrapper...")
    return asyncio.create_task(worker_status_aggs_wrapper())

if __name__ == '__main__':
    asyncio.run(worker_status_aggs())