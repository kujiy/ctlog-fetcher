import asyncio
import time
from datetime import datetime, timezone, timedelta

from src.manager_api.db import get_async_session
from src.manager_api.models import Cert, UniqueCertCounter
from sqlalchemy import select, func
from sqlalchemy.dialects.mysql import insert as mysql_insert
from src.share.logger import logger
from asyncache import cached
from cachetools import TTLCache

BATCH_SIZE = 1000
SLEEP_SEC = 0.5

JST = timezone(timedelta(hours=9))

async def fetch_and_update_unique_cert_counter():
    logger.info("  - 3️⃣  - fetch_and_update_unique_cert_counter")
    # Cold start: get max id from unique_cert_counter
    MAX_CACHE_SIZE = 1_000_000
    cache_set = set()
    async for session in get_async_session():
        result = await session.execute(
            select(func.max(UniqueCertCounter.id))
        )
        last_max_id = result.scalar() or 0
        while True:
            # logger.info(f"3️⃣ last_max_id={last_max_id}")
            # Fetch next batch from Cert table
            result = await session.execute(
                select(Cert.id, Cert.issuer, Cert.serial_number, Cert.certificate_fingerprint_sha256)
                .where(Cert.id > last_max_id)
                .order_by(Cert.id.asc())
                .limit(BATCH_SIZE)
            )
            rows = result.fetchall()
            if not rows:
                break

            # Bulk insert into unique_cert_counter table, ignoring duplicates
            values = []
            for row in rows:
                triplet = (row.issuer, row.serial_number, row.certificate_fingerprint_sha256)
                if triplet in cache_set:
                    continue
                values.append({
                    "id": row.id,
                    "issuer": row.issuer,
                    "serial_number": row.serial_number,
                    "certificate_fingerprint_sha256": row.certificate_fingerprint_sha256
                })
                if len(cache_set) < MAX_CACHE_SIZE:
                    cache_set.add(triplet)
            if values:
                stmt = mysql_insert(UniqueCertCounter).values(values)
                stmt = stmt.prefix_with("IGNORE")
                await session.execute(stmt)

            await session.commit()
            last_max_id = rows[-1].id
            # inserting sleep to avoid long transaction locks
            await asyncio.sleep(SLEEP_SEC)

        # escape the async for loop(close the context/session)
        break

async def count_job_wrapper():
    logger.info("3️⃣  - unique_counter count_job_wrapper...")
    while True:
        await fetch_and_update_unique_cert_counter()
        logger.info(f"    - 3️⃣  - unique_counter count_job_wrapper:sleep 13 minutes")
        await asyncio.sleep(60 * 13)  # 13 minutes


def start_unique_cert_counter():
    logger.info("3️⃣ [unique_cert_counter] Started MySQL counter background job")
    return asyncio.create_task(count_job_wrapper())


_cache = TTLCache(maxsize=100, ttl=600)
@cached(_cache)
async def get_unique_cert_counter_count():
    from sqlalchemy import func
    async for session in get_async_session():
        result = await session.execute(
            select(func.count()).select_from(UniqueCertCounter)
        )
        count = result.scalar_one()
        await session.close()
        return count

if __name__ == "__main__":
    asyncio.run(fetch_and_update_unique_cert_counter())
