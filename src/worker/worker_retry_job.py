import glob
import json
import os
import time

import requests

from src.worker import logger, PENDING_FILE_DIR
from src.worker.worker_common_funcs import get_stop_event, sleep_with_stop_check
from src.worker.worker_base_models import WorkerArgs



def process_pending_requests_files(args: WorkerArgs, file_glob="pending_*.json"):
    """
    Scan pending_*.json files and delete those whose requests succeed.
    """
    deleted = 0
    for req_file in glob.glob(os.path.join(PENDING_FILE_DIR, file_glob)):
        try:
            with open(req_file, "r") as f:
                req = json.load(f)

            url = req.get("url")
            # Add ?retry=1 or &retry=1 to the URL to indicate this is a retry
            url += f"&retry_del={deleted}" if '?' in url else f"?retry_del={deleted}"

            method = req.get("method", "POST").upper()
            data = req.get("data")
            if not url or not method:
                logger.warning(f"[retry] Invalid pending file format: {req_file}")
                continue

            logger.debug(f"[retry] Attempting to resend: {req_file}")
            if method == "POST":
                resp = requests.post(url, json=data, timeout=180)
            elif method == "GET":
                resp = requests.get(url, params=data, timeout=180)
            else:
                logger.warning(f"[retry] Unsupported method {method}: {req_file}")
                continue

            if resp.status_code == 200:
                logger.debug(f"[retry-success] {req_file} resend succeeded")
                os.remove(req_file)
                deleted += 1
            else:
                # Log detailed retry failure for debugging
                logger.warning(f"[retry-failed] {req_file} status={resp.status_code}")
                logger.warning(f"[retry-failed] response body: {resp.text}")
                if "completed" in req_file:
                    logger.warning(f"[retry-failed] request data: {json.dumps(data, indent=2)}")
        except Exception as e:
            logger.debug(f"[retry-exception] {req_file}: {e}")
            time.sleep(1)
            continue
        time.sleep(1)


# --- Dedicated retry management thread ---

# Generic retry file processing
def retry_manager_unified(args: WorkerArgs):
    """Unified retry manager for ThreadPoolExecutor"""
    logger.debug("Starting unified retry manager")
    my_stop_event = get_stop_event()
    while not my_stop_event.is_set():
        for _ in range(60):
            if my_stop_event.is_set():
                logger.debug("retry_manager_unified: stop_event is set, exiting!")
                return
            sleep_with_stop_check(1, my_stop_event)
        process_pending_requests_files(args)
    logger.debug("Exiting unified retry manager")
