import asyncio
from datetime import datetime, timedelta

from sqlalchemy import select, func, and_
from src.config import JST
from src.manager_api.models import WorkerStatus, WorkerStatusAggs
from src.share.logger import logger
from src.manager_api.db import get_async_session

START_TIME = datetime(2025, 8, 25, 0, 0, 0, tzinfo=JST)

async def get_latest_agg_time(session):
    stmt = select(func.max(WorkerStatusAggs.end_time))
    result = await session.execute(stmt)
    latest = result.scalar()
    return latest

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

async def get_id_range(session, start, end):
    stmt = select(func.min(WorkerStatus.id), func.max(WorkerStatus.id)).where(
        WorkerStatus.last_ping >= start,
        WorkerStatus.last_ping < end
    )
    result = await session.execute(stmt)
    min_id, max_id = result.first()
    return min_id, max_id

async def aggregate_worker_status(session, min_id, max_id):
    # statusごとのカウント
    stmt = select(WorkerStatus.status, func.count()).where(
        and_(WorkerStatus.id >= min_id, WorkerStatus.id < max_id)
    ).group_by(WorkerStatus.status)
    result = await session.execute(stmt)
    status_counts = dict(result.all())

    # 全体数
    stmt = select(func.count()).where(and_(WorkerStatus.id >= min_id, WorkerStatus.id < max_id))
    total = (await session.execute(stmt)).scalar()

    # distinct worker_name, log_name
    stmt = select(func.count(func.distinct(WorkerStatus.worker_name))).where(and_(WorkerStatus.id >= min_id, WorkerStatus.id < max_id))
    worker_name_count = (await session.execute(stmt)).scalar()

    stmt = select(func.count(func.distinct(WorkerStatus.log_name))).where(and_(WorkerStatus.id >= min_id, WorkerStatus.id < max_id))
    log_name_count = (await session.execute(stmt)).scalar()

    stmt = select(func.coalesce(func.sum(WorkerStatus.jp_count), 0)).where(and_(WorkerStatus.id >= min_id, WorkerStatus.id < max_id))
    jp_count_sum = (await session.execute(stmt)).scalar()

    return {
        "total_worker_status_count": total,
        "completed": status_counts.get("completed", 0),
        "running": status_counts.get("running", 0),
        "dead": status_counts.get("dead", 0),
        "failed": status_counts.get("failed", 0),
        "resume_wait": status_counts.get("resume_wait", 0),
        "skipped": status_counts.get("skipped", 0),
        "worker_name_count": worker_name_count,
        "log_name_count": log_name_count,
        "jp_count_sum": jp_count_sum,
    }

async def worker_status_aggs():
    while True:
        logger.info(f"  -  6️⃣ worker_status_aggs")
        async for session in get_async_session():
            try:
                latest_agg_time = await get_latest_agg_time(session)
                # JSTのoffset-aware datetimeで現在時刻を取得
                now = datetime.now(JST).replace(minute=0, second=0, microsecond=0)
                target_time = now - timedelta(hours=1)
                while True:
                    start, end = get_next_hour_range(latest_agg_time)
                    # start, end, target_time すべてJSTのoffset-aware
                    if end > target_time:
                        break
                    min_id, max_id = await get_id_range(session, start, end)
                    if min_id is None or max_id is None:
                        print(f"No data to aggregate for {start} - {end}")
                        await register_zero(end, session, start)
                        latest_agg_time = end
                        continue

                    agg = await aggregate_worker_status(session, min_id, max_id)
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
            logger.info(f"      - 6️⃣ worker_status_aggs - sleep_before_loop=3600s")
            await asyncio.sleep(3600)


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