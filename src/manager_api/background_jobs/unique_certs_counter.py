import asyncio
import os
from datetime import datetime, timezone, timedelta
from ..models import Cert
from ..db import get_async_session
from sqlalchemy import text
import logging

logger = logging.getLogger("unique_certs_counter")

# JST timezone
JST = timezone(timedelta(hours=9))

async def count_unique_certs_and_save():
    """Execute every n minutes and save the number of unique certificates to a file"""
    try:
        while True:
            try:
                async for session in get_async_session():
                    # SELECT COUNT(DISTINCT issuer, serial_number) FROM ct.certs;
                    result = await session.execute(
                        text("SELECT COUNT(DISTINCT issuer, serial_number) FROM certs")
                    )
                    unique_count = result.scalar() or 0

                # Save to file
                file_path = "/tmp/unique_certs_count.txt"
                with open(file_path, 'w') as f:
                    f.write(str(unique_count))

                now = datetime.now(JST)
                logger.info(f"[unique_certs_counter] Updated unique certs count: {unique_count} at {now}")

            except Exception as e:
                logger.error(f"[unique_certs_counter] Error counting unique certs: {e}")

            # Wait n seconds
            await asyncio.sleep(60 * 15)  # 60 sec * n mins
    except asyncio.CancelledError:
        # Graceful shutdown
        return

def start_unique_certs_counter():
    """Start the unique certificate counter in the background"""
    task = asyncio.create_task(count_unique_certs_and_save())
    logger.info("[unique_certs_counter] Started unique certs counter background job")
    return task

def get_unique_certs_count():
    """Read the number of unique certificates from the file"""
    try:
        file_path = "/tmp/unique_certs_count.txt"
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                count = int(f.read().strip())
                return count
        else:
            return "-"
    except Exception as e:
        logger.error(f"[unique_certs_counter] Error reading unique certs count: {e}")
        return "-"


if __name__ == "__main__":
    asyncio.run(count_unique_certs_and_save())
