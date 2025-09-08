import asyncio
from datetime import datetime
from ..models import CTLogSTH
from ...config import CT_LOG_ENDPOINTS, STH_FETCH_INTERVAL_SEC
from ..db import get_async_session
import aiohttp
from src.share.logger import logger

async def fetch_sth_no_retry(log_name, ct_log_url, now):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{ct_log_url.rstrip('/')}/ct/v1/get-sth", timeout=10) as resp:
                if resp.status != 200:
                    logger.debug(f"[sth_fetcher] HTTP {resp.status} for {log_name}")
                    return None, None
                sth = await resp.json()
                tree_size = sth.get('tree_size', 0)
                sth_ts = sth.get('timestamp', None)
                sth_dt = now
                if sth_ts:
                    try:
                        # If timestamp is too large, treat as ms since epoch
                        if sth_ts > 2_000_000_000:
                            sth_dt = datetime.utcfromtimestamp(sth_ts / 1000)
                        else:
                            sth_dt = datetime.utcfromtimestamp(sth_ts)
                    except Exception as e:
                        logger.debug(f"[sth_fetcher] Invalid timestamp for {log_name}: {sth_ts} ({e}) - using now")
                return tree_size, sth_dt
    except Exception as e:
        logger.debug(f"[sth_fetcher] Exception for {log_name} ({ct_log_url}): {e}")
        return None, None

async def fetch_and_store_sth():
    logger.info("1️⃣  -  fetch_and_store_sth")
    try:
        while True:
            async for session in get_async_session():
                now = datetime.utcnow()
                for category, endpoints in CT_LOG_ENDPOINTS.items():
                    for log_name, ct_log_url in endpoints:
                        tree_size, sth_dt = await fetch_sth_no_retry(log_name, ct_log_url, now)
                        if tree_size is None or sth_dt is None:
                            continue
                        # Overwrite if record exists, otherwise insert new
                        entry = await session.execute(
                            CTLogSTH.__table__.select().where(
                                (CTLogSTH.log_name == log_name) & (CTLogSTH.ct_log_url == ct_log_url)
                            )
                        )
                        entry = entry.fetchone()
                        if entry:
                            await session.execute(
                                CTLogSTH.__table__.update()
                                .where((CTLogSTH.log_name == log_name) & (CTLogSTH.ct_log_url == ct_log_url))
                                .values(tree_size=tree_size, sth_timestamp=sth_dt, fetched_at=now)
                            )
                        else:
                            await session.execute(
                                CTLogSTH.__table__.insert().values(
                                    log_name=log_name,
                                    ct_log_url=ct_log_url,
                                    tree_size=tree_size,
                                    sth_timestamp=sth_dt,
                                    fetched_at=now
                                )
                            )
                        await session.commit()
            await asyncio.sleep(STH_FETCH_INTERVAL_SEC)  # interval between fetches
    except asyncio.CancelledError:
        # Graceful shutdown
        return

def start_sth_fetcher():
    logger.info("️1️⃣ start_sth_fetcher...")
    return asyncio.create_task(fetch_and_store_sth())

if __name__ == '__main__':
    asyncio.run(fetch_and_store_sth())
