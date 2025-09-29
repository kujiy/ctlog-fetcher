import asyncio
import glob
import os
import shutil

import aiohttp

from src.config import MANAGER_API_URL
from src.share.logger import logger

# n minutes interval for pending failure upload
PENDING_FAILURE_UPLOAD_INTERVAL_SEC = 60 * 1

async def upload_pending_failure_file(file_path: str, api_url: str) -> bool:
    """
    Upload a single pending failure file to the API.

    Args:
        file_path: Path to the JSON file to upload
        api_url: API endpoint URL

    Returns:
        bool: True if upload successful, False otherwise
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = f.read()

        async with aiohttp.ClientSession() as session:
            async with session.post(
                api_url,
                headers={'Content-Type': 'application/json'},
                data=data,
                timeout=30
            ) as resp:
                if resp.status == 200:
                    logger.info(f"[pending_failure_uploader] Successfully uploaded: {file_path}")
                    # Move file to /tmp/ after successful upload
                    tmp_path = f"/tmp/{os.path.basename(file_path)}"
                    shutil.move(file_path, tmp_path)
                    logger.debug(f"[pending_failure_uploader] Moved {file_path} to {tmp_path}")
                    return True
                else:
                    logger.warning(f"[pending_failure_uploader] Upload failed ({resp.status}): {file_path}")
                    return False

    except Exception as e:
        logger.error(f"[pending_failure_uploader] Exception uploading {file_path}: {e}")
        return False

async def process_pending_failures():
    """
    Process all pending failure files in the upload_failure directory.
    """
    logger.info("  -  7️⃣  -  process_pending_failures")

    # Directory path for pending failures
    failure_dir = "pending/upload_failure"

    # Check if directory exists
    if not os.path.exists(failure_dir):
        logger.debug(f"[pending_failure_uploader] Directory {failure_dir} does not exist, skipping")
        return

    # API endpoint
    api_url = f"{MANAGER_API_URL}/api/worker/upload"

    # Find all JSON files in the directory
    json_files = glob.glob(os.path.join(failure_dir, "*.json"))

    if not json_files:
        logger.debug(f"[pending_failure_uploader] No pending failure files found in {failure_dir}")
        return

    logger.info(f"    -  7️⃣ [pending_failure_uploader] Found {len(json_files)} pending failure files to process")

    success_count = 0
    failure_count = 0

    for file_path in json_files:
        success = await upload_pending_failure_file(file_path, api_url)
        if success:
            success_count += 1
        else:
            failure_count += 1

    logger.info(f"    -  7️⃣ [pending_failure_uploader] Processing complete: {success_count} successful, {failure_count} failed")

async def pending_failure_uploader_loop():
    """
    Main loop for the pending failure uploader background job.
    """
    try:
        while True:
            logger.info("  - 7️⃣  -  pending_failure_uploader_loop:while")

            await process_pending_failures()

            logger.info(f"    - 7️⃣  -  pending_failure_uploader_loop:sleep {PENDING_FAILURE_UPLOAD_INTERVAL_SEC} sec")
            await asyncio.sleep(PENDING_FAILURE_UPLOAD_INTERVAL_SEC)

    except asyncio.CancelledError:
        # Graceful shutdown
        logger.info("[pending_failure_uploader] Background job cancelled, shutting down gracefully")
        return

def start_pending_failure_uploader():
    """
    Start the pending failure uploader background job.

    Returns:
        asyncio.Task: The created task for the background job
    """
    logger.info("7️⃣ start_pending_failure_uploader...")
    return asyncio.create_task(pending_failure_uploader_loop())

if __name__ == '__main__':
    #  PYTHONPATH=. MANAGER_API_URL=http://192.168.0.185:1173 python src/manager_api/background_jobs/pending_failure_uploader.py
    # For testing purposes
    asyncio.run(pending_failure_uploader_loop())
