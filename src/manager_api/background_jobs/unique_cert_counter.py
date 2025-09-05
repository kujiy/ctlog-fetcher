import asyncio
import time
from datetime import datetime, timezone, timedelta

from src.manager_api.db import get_async_session
from src.manager_api.models import Cert, UniqueCertCounter
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from src.share.logger import logger
from asyncache import cached
from cachetools import TTLCache

BATCH_SIZE = 1000
SLEEP_SEC = 0.5

JST = timezone(timedelta(hours=9))

async def fetch_and_update_unique_cert_counter():
    last_max_id = 0
    while True:
        async for session in get_async_session():
            while True:
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

                # Insert into unique_cert_counter table
                for row in rows:
                    try:
                        obj = UniqueCertCounter(
                            id=row.id,
                            issuer=row.issuer,
                            serial_number=row.serial_number,
                            certificate_fingerprint_sha256=row.certificate_fingerprint_sha256
                        )
                        session.add(obj)
                        await session.flush()
                    except IntegrityError as e:
                        await session.rollback()
                        # Ignore unique constraint errors, do not rollback the whole transaction
                        if 'Duplicate entry' in str(e):  # 1062
                            pass
                        else:
                            raise
                    except Exception as e:
                        logger.error(f"[unique_cert_counter] insert error: {e}")
                        await session.rollback()

                await session.commit()
                last_max_id = rows[-1].id
                time.sleep(SLEEP_SEC)
            await session.close()
            break

async def batch_job():
    while True:
        try:
            await fetch_and_update_unique_cert_counter()
        except Exception as e:
            logger.error(f"[unique_cert_counter] Error in batch job: {e}")
        await asyncio.sleep(60 * 13)  # 13 minutes

def start_unique_cert_counter():
    task = asyncio.create_task(batch_job())
    logger.info("[unique_cert_counter] Started MySQL counter background job")
    return task


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
