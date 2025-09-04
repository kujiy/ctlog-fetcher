import asyncio
import os
import sqlite3
import time
from datetime import datetime, timezone, timedelta

from asyncache import cached
from cachetools import TTLCache

from src.manager_api.db import get_async_session
from sqlalchemy import text
from src.share.logger import logger

# mkdir unique_cert_counter
os.makedirs("unique_cert_counter", exist_ok=True)
SQLITE_DB_PATH = "./unique_cert_counter/unique_cert_counter.sqlite"
STATE_PATH = "./unique_cert_counter/unique_cert_counter_state.txt"
BATCH_SIZE = 1000
SLEEP_SEC = 0.5

JST = timezone(timedelta(hours=9))

def init_sqlite():
    # print("Initializing SQLite...")
    conn = sqlite3.connect(SQLITE_DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS unique_cert_counter (
            issuer TEXT,
            serial_number TEXT,
            id INTEGER,
            PRIMARY KEY (issuer, serial_number)
        )
    """)
    conn.commit()
#     print("Initialized SQLite.")
    return conn

def get_last_max_id():
#     print("Getting last max id from SQLite...")
    if os.path.exists(STATE_PATH):
#         print("Loading last max id from SQLite...")
        with open(STATE_PATH, "r") as f:
            try:
#                 print("opening state file...")
                return int(f.read().strip())
            except Exception:
                return 0
    return 0

def set_last_max_id(max_id):
    with open(STATE_PATH, "w") as f:
        f.write(str(max_id))

async def fetch_and_update_unique_cert_counter():
    conn = init_sqlite()
    c = conn.cursor()
    last_max_id = get_last_max_id()
    # logger.info(f"[unique_cert_counter_sqlite_counter] Start from id > {last_max_id}")


    async for session in get_async_session():
        while True:
            # Fetch next batch
#             print(f"Fetching batch from id > {last_max_id}...")
            result = await session.execute(
                text(f"SELECT id, issuer, serial_number FROM certs WHERE id > :last_id ORDER BY id ASC LIMIT :batch_size"),
                {"last_id": last_max_id, "batch_size": BATCH_SIZE}
            )
            rows = result.fetchall()
            if not rows:
                break

            # Insert into sqlite
            for row in rows:
                try:
                    c.execute(
                        "INSERT OR IGNORE INTO unique_cert_counter (issuer, serial_number, id) VALUES (?, ?, ?)",
                        (row.issuer, row.serial_number, row.id)
                    )
                except Exception as e:
                    logger.error(f"[unique_cert_counter_sqlite_counter] sqlite insert error: {e}")

            conn.commit()
            last_max_id = rows[-1].id
            set_last_max_id(last_max_id)
#             logger.info(f"[unique_cert_counter_sqlite_counter] Processed up to id {last_max_id}")
            time.sleep(SLEEP_SEC)
#         print("while loop done")
        await session.close()
#         print("session closed")
        break
#     print("async for done")
    conn.close()
#     print("conn is closed")
#     logger.info(f"[unique_cert_counter_sqlite_counter] Finished batch update up to id {last_max_id}")

# 10min TTLCache
_cache = TTLCache(maxsize=100, ttl=600)
@cached(_cache)
def get_unique_cert_counter_count():
    if not os.path.exists(STATE_PATH):
        return 0
    try:
        with open(STATE_PATH, "r") as f:
            return int(f.read().strip())
    except Exception as e:
        logger.error(f"[unique_cert_counter_sqlite_counter] Error reading state file: {e}")
        return 0

async def batch_job():
    while True:
        try:
            await fetch_and_update_unique_cert_counter()
        except Exception as e:
            logger.error(f"[unique_cert_counter_sqlite_counter] Error in batch job: {e}")
        await asyncio.sleep(60 * 13)  # mins

def start_unique_cert_counter_sqlite_counter():
    task = asyncio.create_task(batch_job())
    logger.info("[unique_cert_counter_sqlite_counter] Started sqlite counter background job")
    return task

if __name__ == "__main__":
#     print(get_unique_cert_counter_count())
    asyncio.run(fetch_and_update_unique_cert_counter())
