# worker
import glob
import argparse
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
import hashlib
import time
import requests
import threading
import json
import socket
import logging
import sys
import random
import concurrent.futures
from src.share.job_status import JobStatus
from src.share.cert_parser import JPCertificateParser
import uuid
import signal
import traceback
import re
import datetime
import urllib.parse
from src.config import CT_LOG_ENDPOINTS, WORKER_THREAD_MANAGER_INTERVAL_SEC
from collections import Counter

from dotenv import load_dotenv
load_dotenv()


logger = logging.getLogger("ct_worker")

# --- Settings ---
MAX_CONSOLE_LINES = 8
DEFAULT_CATEGORIES = Counter(["google", "google", "google", "cloudflare", "letsencrypt", "digicert", "trustasia"])

PENDING_FILE_DIR = "pending"
os.makedirs(PENDING_FILE_DIR, exist_ok=True)
FAILED_FILE_DIR = "tests/resources/failed"
os.makedirs(FAILED_FILE_DIR, exist_ok=True)


# Global management of stop_event for each thread
stop_events = {}

def get_stop_event() -> threading.Event:
    return stop_events.get(threading.get_ident())

def register_stop_event(event=None):
    if event is None:
        event = threading.Event()
    stop_events[threading.get_ident()] = event


class NeedTreeSizeException(Exception):
    pass

def fetch_ct_log(ct_log_url, start, end, proxies=None):
    # Google CT log API: /ct/v1/get-entries?start={start}&end={end}
    base_url = ct_log_url.rstrip('/')
    url = f"{base_url}/ct/v1/get-entries?start={start}&end={end}"
    try:
        # If proxies is a list, select randomly
        if proxies and isinstance(proxies, list):
            proxy_url = random.choice(proxies)
            use_proxies = {"http": proxy_url, "https": proxy_url}
        else:
            use_proxies = proxies
        resp = requests.get(url, proxies=use_proxies, timeout=10)
        logger.debug(f"Response body: {resp.text[:200]}")
        if resp.status_code == 200:
            return resp.json().get('entries', [])
        elif resp.status_code == 429:
            retry_after = resp.headers.get('Retry-After')
            logger.debug(f"[WARN] CT log rate limited (429): {retry_after} seconds. url={url}")
            try:
                wait_sec = int(retry_after) if retry_after else 5
            except Exception:
                wait_sec = 5
            logger.debug(f"CT log rate limited (429): waiting {wait_sec}s. url={url}")
            sleep_with_stop_check(wait_sec, my_stop_event)
            return []
        elif resp.status_code == 400 and "need tree size":
            logger.debug(f"NeedTreeSizeException: {resp.text} url={url}")
            raise NeedTreeSizeException(resp.text)
        else:
            logger.debug(f"Failed to fetch CT log: {resp.status_code} url={url}")
            sleep_with_stop_check(5, my_stop_event)
            return []
    except Exception as e:
        logger.debug(f"fetch_ct_log exception: [{type(e).__name__}] {e} url={url}")
        if isinstance(e, NeedTreeSizeException):
            raise
        return []

def worker_job_thread(category, task, args, global_tasks, ctlog_request_interval_sec):
    global status_lines
    log_name = task.get('log_name', '')
    current = task.get('start', 0)
    end = task.get('end', 0)
    logger.debug(f"[DEBUG] Start job: category={category} log_name={log_name} start={current} end={end}")
    proxies = args.proxies if args.proxies else None
    failed_uploads = []
    failed_lock = threading.Lock()
    ct_log_url = task.get('ct_log_url', '')
    # Add all necessary information to the task
    task = task.copy()
    task["manager"] = args.manager
    task["worker_name"] = args.worker_name
    task["log_name"] = log_name
    task["ct_log_url"] = ct_log_url
    task["start"] = task.get('start')
    task["end"] = end
    task["ip_address"] = get_my_ip()
    task["status"] = JobStatus.RUNNING.value
    jobkey = f"{category}_{log_name}_{current}_{end}"
    global_tasks[jobkey] = task
    omikuji_list = ["大吉", "中吉", "小吉", "吉", "末吉", "凶"]
    req_count = 0
    last_ping_time = 0
    start_time = time.time()
    last_uploaded_index = None
    empty_entries_count = 0
    my_ip = get_my_ip()
    worker_jp_count = 0
    worker_total_count = 0

    need_tree_size = False

    my_stop_event = get_stop_event()

    try:
        jp_certs_buffer = []
        ping_interval_sec = 1
        while current <= end and not my_stop_event.is_set():
            logger.debug(f"[DEBUG] Loop: category={category} log_name={log_name} current={current} end={end}")
            omikuji = random.choice(omikuji_list)
            with failed_lock:
                retry_count = len(failed_uploads)
            update_console_message(status_lines, category, log_name, req_count, current, worker_jp_count, worker_total_count, end, task, start_time, omikuji, retry_count)

            # Check stop_event before API call
            if my_stop_event.is_set():
                logger.debug(f"[DEBUG] Stop event detected in worker_job_thread for {category}")
                break

            try:
                # Fetch a CT LOG API: always request up to end, but only process as many as returned
                entries = fetch_ct_log(ct_log_url, current, end, proxies)
            except NeedTreeSizeException as e:
                logger.info(f"[{category}] NeedTreeSizeException caught: {e}. Completing job.")
                need_tree_size = True
                break

            req_count += 1
            actual_entry_size = len(entries)
            logger.debug(f"[DEBUG] Fetched entries: {actual_entry_size} (current={current})")

            if empty_entries_count > 10:
                logger.debug(f"[WARN] Entries were empty 10 times in a row: category={category} log_name={log_name} current={current}")
                break
            if not entries:
                empty_entries_count += 1
                continue
            else:
                empty_entries_count = 0

            # Check stop_event before processing
            if my_stop_event.is_set():
                logger.debug(f"[DEBUG] Stop event detected before processing for {category}")
                break

            # Parsing
            jp_certs = extract_jp_certs(entries, log_name, ct_log_url, args, my_ip, current)
            if jp_certs:
                worker_jp_count += len(jp_certs)  # Add the number of found jp_certs before deduplication as a reward for the worker
                jp_certs_buffer.extend(jp_certs)
                before = len(jp_certs_buffer)
                # Remove duplicates
                jp_certs_buffer = filter_jp_certs_unique(jp_certs_buffer)
                after = len(jp_certs_buffer)
                logger.debug(f"[DEBUG] JP certs buffer: before={before} after={after} added={len(jp_certs)} total_jp_count={worker_jp_count}")

            # upload if buffer is large enough
            if len(jp_certs_buffer) >= 32:
                last_uploaded_index = upload_jp_certs(args, category, current, jp_certs_buffer, failed_lock)
                jp_certs_buffer = []

            worker_total_count += actual_entry_size
            last_ping_time, ping_interval_sec, ctlog_request_interval_sec = send_ping(
                args, category, log_name, ct_log_url, task, end, current, last_uploaded_index,
                worker_jp_count, worker_total_count, my_ip, last_ping_time, status="running", default_ping_seconds=ping_interval_sec, default_ctlog_request_interval_sec=ctlog_request_interval_sec
            )

            # Use sleep_with_stop_check instead of time.sleep
            logger.debug(f"ctlog_request_interval_sec: {ctlog_request_interval_sec}")
            sleep_with_stop_check(ctlog_request_interval_sec, my_stop_event)

            # if the entry is empty, it may loop infinitely, but it will break with empty_entries_count, so it's okay
            current += actual_entry_size
            task["current"] = current

        # Upload the remaining jp_certs anyway at the end of the job
        if jp_certs_buffer:
            last_uploaded_index = upload_jp_certs(args, category, current, jp_certs_buffer, failed_lock)
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"[{category}] Exception in worker_job_thread:\n{tb}")
        report_worker_error(
            args=args,
            error_type="worker_job_thread_error",
            error_message=str(e),
            traceback_str=tb
        )
        return None


    # update the status as completed
    status_key = f"{category}-{log_name}"
    if my_stop_event and my_stop_event.is_set():
        # Erase from console when stopped by category API (normal stop)
        if status_key in status_lines:
            del status_lines[status_key]
        logger.debug(f"[DEBUG] Exit job (stopped by category API): category={category} log_name={log_name} current={current} end={end}")
        return task.copy()
    if (current > end) or need_tree_size:
        console_msg = "✅ Completed!"
        task["status"] = JobStatus.COMPLETED.value
        global_tasks[jobkey]["status"] = JobStatus.COMPLETED.value
        send_completed(args, log_name, ct_log_url, task, end, current, last_uploaded_index, worker_jp_count, worker_total_count, my_ip)
        expect_total_count = end - task.get('start', 0) + 1
        fetched_rate = worker_total_count / expect_total_count
        status_lines[status_key] = (
            f"[{category}] {console_msg} Commited {fetched_rate*100:.1f}% ({worker_total_count}/{expect_total_count}) | Range: {task['start']} - {task['end']}  | 🇯🇵 Domain: {worker_jp_count} | {random.choice(omikuji_list)}"
        )
    else:
        # Show "❌ Failed." only for abnormal termination(including Ctrl+C)
        console_msg = "❌ Failed."
        send_resume(task)
        expect_total_count = end - task.get('start', 0) + 1
        fetched_rate = worker_total_count / expect_total_count
        status_lines[status_key] = (
            f"[{category}] {console_msg} Commited {fetched_rate*100:.1f}% ({worker_total_count}/{expect_total_count}) | Range: {task['start']} - {task['end']}  | 🇯🇵 Domain: {worker_jp_count} | {random.choice(omikuji_list)}"
        )

    logger.debug(f"[DEBUG] Exit job: category={category} log_name={log_name} current={current} end={end}")
    return task.copy()



# --- common retrying process ---
def save_pending_request(request_info, prefix):
    """
    request_info: dict with keys: url, method, data
    prefix: e.g. 'pending_upload', 'pending_completed'
    """
    filename = pending_file_name(request_info, prefix)
    fname = os.path.join(PENDING_FILE_DIR, filename)

    with open(fname, "w") as f:
        json.dump(request_info, f, indent=2)


def pending_file_name(request_info, prefix):
    # Generate timestamp
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    # Extract log_name and worker_name from request data
    data = request_info.get('data', {})
    log_name = data.get('log_name', 'unknown') if isinstance(data, dict) else 'unknown'
    worker_name = data.get('worker_name', 'unknown') if isinstance(data, dict) else 'unknown'
    # Clean log_name and worker_name for filename (remove invalid characters)
    log_name_clean = ''.join(c for c in log_name if c.isalnum() or c in '-_')[:20]
    worker_name_clean = ''.join(c for c in worker_name if c.isalnum() or c in '-_')[:20]
    # Generate short UUID
    uuid_short = uuid.uuid4().hex[:8]
    return f"{prefix}_{timestamp}_{log_name_clean}_{worker_name_clean}_{uuid_short}.json"


def send_completed(args, log_name, ct_log_url, task, end, current, last_uploaded_index, worker_jp_count, worker_total_count, my_ip):
    completed_data = {
        "worker_name": args.worker_name,
        "log_name": log_name,
        "ct_log_url": ct_log_url,
        "start": task.get('start'),
        "end": end,
        "current": current,
        "worker_total_count": worker_total_count,
        "last_uploaded_index": last_uploaded_index,
        "status": JobStatus.COMPLETED.value,  # Add the missing required status field
        "jp_count": worker_jp_count,
        "jp_ratio": (worker_jp_count / worker_total_count) if worker_total_count > 0 else 0,
        "ip_address": my_ip
    }
    url = f"{args.manager}/api/worker/completed"
    try:
        resp = requests.post(url, json=completed_data, timeout=180)
        if resp.status_code != 200:
            # Log detailed API response for debugging
            logger.debug(f"[worker] failed to send completed api: status={resp.status_code}")
            logger.debug(f"[worker] completed api response body: {resp.text}")
            logger.debug(f"[worker] completed api request data: {json.dumps(completed_data, indent=2)}")
            raise Exception(f"status={resp.status_code} body={resp.text}")
        else:
            logger.debug(f"[worker] completed api - successfully sent: {log_name} range={task.get('start')}-{end}")
    except Exception as e:
        logger.debug(f"[worker] failed to send completed api: {e}")
        save_pending_request({
            "url": url,
            "method": "POST",
            "data": completed_data
        }, prefix="pending_completed")



# --- Dedicated retry management thread ---

# Generic retry file processing
def process_pending_requests_files(args, file_glob="pending_*.json"):
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



def retry_manager_unified(args):
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



def handle_api_failure(category, fail_count, last_job, MAX_FAIL, logger, task_ref, args=None):
    status = None
    jobkey = None
    if last_job:
        jobkey = f"{category}_{last_job.get('log_name','')}_{last_job.get('start',0)}_{last_job.get('end',0)}"
        global global_tasks
        if jobkey in global_tasks:
            status = global_tasks[jobkey].get('status')
        else:
            status = last_job.get('status')
    logger.debug(f"fail_count: {fail_count}/{MAX_FAIL}, jobkey: {jobkey}, status: {status}")
    if fail_count >= MAX_FAIL and last_job:
        batch_size = last_job["end"] - last_job["start"] + 1
        if status != JobStatus.COMPLETED.value:
            # If the job is incomplete, resume
            logger.warning(f"{category}: API failure/exception occurred {fail_count} times, resuming unfinished job (range: {last_job['start']}-{last_job['end']})")
            resume_task = last_job.copy()
            resume_task["current"] = resume_task["start"]
            resume_task["status"] = JobStatus.RUNNING.value
            task_ref[0] = resume_task
            return True, 0, resume_task
        else:
            # If the job is complete, perform DNS check before generating the next range job
            if args is not None:
                wait_for_manager_api_ready(args.manager)
            next_start = last_job["end"] + 1
            next_end = last_job["end"] + batch_size
            logger.warning(
                f"{category}: API failure/exception occurred {fail_count} times, autonomously generating the next range job (next range: {next_start}-{next_end}): Autonomous recovery succeeded ✅")
            new_task = last_job.copy()
            new_task["start"] = next_start
            new_task["current"] = next_start
            new_task["end"] = next_end
            new_task["status"] = JobStatus.RUNNING.value
            task_ref[0] = new_task
            return True, 0, new_task
    return False, fail_count, last_job



def category_job_manager(category, args, global_tasks, my_stop_event):
    logger.debug(f"category_job_manager: {category} ident={threading.get_ident()}")
    """Manager to sequentially fetch and execute jobs for each category (ThreadPoolExecutor version)"""
    last_job = None
    fail_count = 0
    MAX_FAIL = 6
    task = None
    ctlog_request_interval_sec = 1

    try:
        while not my_stop_event.is_set():
            try:
                url = f"{args.manager}/api/worker/next_task?category={category}&worker_name={args.worker_name}"
                logger.debug(url)
                resp = requests.get(url)
                logger.debug(f"status_code: {resp.status_code}, body: {resp.text[:200]}")
                if resp.status_code == 200:
                    task = resp.json()
                    # when the job is completed
                    if not task or "start" not in task:
                        # support the case where the API returns {"message": "all logs completed", "sleep_sec": ...}
                        if isinstance(task, dict) and task.get("message") == "all logs completed":
                            sleep_sec = int(task.get("sleep_sec", 600))
                            logger.info(f"{category}: collected all log_names, sleeping for {sleep_sec} seconds")
                            sleep_with_stop_check(sleep_sec, my_stop_event)
                        else:
                            logger.info(f"{category}: unexpected API response: no next job, waiting 60 seconds")
                            sleep_with_stop_check(60, my_stop_event)
                        continue

                    # Reset fail_count on successful retrieval
                    fail_count = 0
                    # Get ctlog_request_interval_sec from the next_task API (default to 1 if not present)
                    ctlog_request_interval_sec = int(task.get("ctlog_request_interval_sec", 1))
                    last_job = task.copy()
                else:
                    logger.debug(f"{category}: failed to get next_task: {resp.status_code}")
                    fail_count += 1
                    # Wait for 2 seconds, but return immediately if stop_event is set
                    sleep_with_stop_check(10, my_stop_event)

                    # Try several times, and if it still fails, generate the task autonomously
                    result, fail_count, last_job = handle_api_failure(category, fail_count, last_job, MAX_FAIL, logger, [task], args)
                    if result:
                        # task autonomous generation
                        task = last_job.copy()
                    else:
                        continue
            except requests.exceptions.RequestException as e:
                # Communication errors are expected
                logger.debug(f"[{category}] Communication error getting next_task. The manager api might have been down. : {e}")
                fail_count += 1
                sleep_with_stop_check(1, my_stop_event)
                result, fail_count, last_job = handle_api_failure(category, fail_count, last_job, MAX_FAIL, logger, [task], args)
                if result:
                    task = last_job.copy()
                else:
                    continue
            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f"[{category}] Exception getting next_task (moving to the fail-safe mode):\n{tb}")
                report_worker_error(
                    args=args,
                    error_type="category_job_manager_error",
                    error_message=str(e),
                    traceback_str=tb
                )
                fail_count += 1
                sleep_with_stop_check(1, my_stop_event)
                result, fail_count, last_job = handle_api_failure(category, fail_count, last_job, MAX_FAIL, logger, [task], args)
                if result:
                    task = last_job.copy()
                else:
                    continue

            if my_stop_event.is_set():
                break

            # Generate a worker_job_thread for each category
            try:
                completed_task = worker_job_thread(category, task, args, global_tasks, ctlog_request_interval_sec)
            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f"[{category}] Exception in job thread:\n{tb}")
                report_worker_error(
                    args=args,
                    error_type="category_job_manager_jobthread_error",
                    error_message=str(e),
                    traceback_str=tb
                )
                completed_task = None
            if completed_task is not None:
                last_job = completed_task
            if not my_stop_event.is_set():
                logger.debug(f"{category}: job completed. Fetching next job")
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"[{category}] Exception in category_job_manager:\n{tb}")
        report_worker_error(
            args=args,
            error_type="category_job_manager_fatal",
            error_message=str(e),
            traceback_str=tb
        )

    logger.debug(f"Exiting category job manager for {category}")



def send_resume(info):
    try:
        requests.post(f"{info['manager']}/api/worker/resume_request", json={
            "worker_name": info["worker_name"],
            "log_name": info["log_name"],
            "ct_log_url": info["ct_log_url"],
            "start": info["start"],
            "end": info["end"],
            "ip_address": info.get("ip_address")
        }, timeout=10)
    except Exception as e:
        logger.debug(f"Failed to send resume_request: {e}")


# By default, the hostname is converted to two Japanese-style words plus a number. If a nickname is specified, it is used as is.
def default_worker_name():
    # By default, convert the hostname to two Japanese-style words plus a number. If a nickname is specified, use it as is.
    hostname = socket.gethostname()
    words = ["pin",   "pon",   "chin",  "kan",   "pafu",  "doki",  "bata",  "kero",  "piyo",  "goro",  "fuwu",  "zun",   "kyu",   "pata",  "ponk", "boon"]
    h = int(hashlib.sha256(hostname.encode()).hexdigest(), 16)
    w1 = words[h % len(words)]
    w2 = words[(h // len(words)) % len(words)]
    num = h % 10000
    return f"{w1}-{w2}-{num:04d}"

def category_job_manager_with_wrapper(category, args, global_tasks, stop_event):
    register_stop_event(stop_event)
    category_job_manager(category, args, global_tasks, stop_event)


# --- Category Watcher Thread ---
def category_thread_manager(args, executor, category_thread_info):
    """
    Periodically call /api/worker/categories and manage the increase/decrease of category threads.
    category_thread_info: { (category, idx): {"thread": future, "stop_event": event} }
    """
    register_stop_event()

    my_stop_event = get_stop_event()
    last_desired_counts = DEFAULT_CATEGORIES.copy()
    last_all_categories = list(DEFAULT_CATEGORIES.keys())
    while not my_stop_event.is_set():
        try:
            desired_counts, all_categories = fetch_categories(args.manager)
            # Only update if fetch_categories succeeded (i.e., did not fall back to DEFAULT_CATEGORIES)
            if desired_counts != DEFAULT_CATEGORIES:
                last_desired_counts = desired_counts
                last_all_categories = all_categories
        except Exception:
            # On any error, keep using last successful values
            pass

        # Use last successful values
        desired_counts = last_desired_counts
        all_categories = last_all_categories

        # Get the current state of threads
        running_counts = {}
        for (cat, idx), info in list(category_thread_info.items()):
            # info["thread"] is the return value of ThreadPoolExecutor.submit (Future)
            if info["thread"].done():
                # Remove finished threads
                del category_thread_info[(cat, idx)]
                continue
            running_counts[cat] = running_counts.get(cat, 0) + 1

        # Immediately stop and remove threads for categories not in all_categories
        for (cat, idx), info in list(category_thread_info.items()):
            if cat not in all_categories:
                info["stop_event"].set()
                del category_thread_info[(cat, idx)]

        # Thread scaling
        # 1. Increase
        for cat, desired in desired_counts.items():    # e.g. google, digicert...
            running = running_counts.get(cat, 0)      # e.g. google needs 3 threads
            for i in range(running, desired):        # Start new threads as needed
                # Start new threads for categories such as google, digicert, etc.
                stop_evt = threading.Event()
                future = executor.submit(category_job_manager_with_wrapper, cat, args, global_tasks, stop_evt)
                category_thread_info[(cat, i)] = {"thread": future, "stop_event": stop_evt}
                time.sleep(1)

        # 2. Decrease
        for (cat, idx), info in list(category_thread_info.items()):
            desired = desired_counts.get(cat, 0)
            if idx >= desired:
                # Stop instruction
                info["stop_event"].set()
                # No join (managed by ThreadPoolExecutor future)

        sleep_with_stop_check(WORKER_THREAD_MANAGER_INTERVAL_SEC)

ordered_categories = []
def fetch_categories(domain: str):
    global ordered_categories
    url = f"{domain}/api/worker/categories"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            # current API: {"all_categories": [...], "ordered_categories": [...]}
            all_categories = data["all_categories"]
            ordered_categories = data["ordered_categories"]
            desired_counts = Counter(ordered_categories)
            return desired_counts, all_categories
        # error
        desired_counts = DEFAULT_CATEGORIES
        all_categories = list(DEFAULT_CATEGORIES.keys())
    except Exception:
        desired_counts = DEFAULT_CATEGORIES
        all_categories = list(DEFAULT_CATEGORIES.keys())
    return desired_counts, all_categories


def main(args):
    global status_lines, global_tasks
    categories = list(CT_LOG_ENDPOINTS.keys())
    status_lines = {}
    executor = None
    futures = {}

    # --- Category thread management ---
    # Dictionary for managing category threads: (category, idx): {"thread": future, "stop_event": event}
    category_thread_info = {}  # (category, idx): {"thread": future, "stop_event": event}

    def handle_terminate(signum, frame):
        if getattr(handle_terminate, '_called', False):
            logger.debug("handle_terminate: already called, skipping duplicate execution.")
            return
        handle_terminate._called = True

        # Set stop_event for all threads
        for ev in list(stop_events.values()):
            ev.set()

        # Send resume requests for running jobs
        for category, task in global_tasks.items():
            if task.get("status") == JobStatus.RUNNING.value and task.get("current", task["start"]) < task["end"]:
                logger.info(f"Terminating {category}, sending resume_request API...")
                send_resume(task)

        # Shutdown ThreadPoolExecutor
        if executor:
            logger.debug("Shutting down ThreadPoolExecutor...")
            executor.shutdown(wait=False)
            logger.debug("ThreadPoolExecutor shutdown completed")

        logger.debug("Sending sys.exit()")
        sys.exit(0)


    signal.signal(signal.SIGINT, handle_terminate)
    signal.signal(signal.SIGTERM, handle_terminate)

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format='[%(asctime)s] [%(threadName)s] %(levelname)s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    logger.info(f"Worker started. Worker name: {args.worker_name}")

    # Create single ThreadPoolExecutor for all tasks
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=args.max_threads)

    try:
        # Submit retry manager to executor
        def retry_wrapper(*a, **kw):
            register_stop_event()
            retry_manager_unified(*a, **kw)
        retry_future = executor.submit(retry_wrapper, args)
        futures["retry_manager"] = retry_future

        # start category watcher thread
        watcher_thread = threading.Thread(
            target=category_thread_manager,
            args=(args, executor, category_thread_info),
            daemon=True
        )
        watcher_thread.start()

        logger.info("All tasks submitted to ThreadPoolExecutor (category watcher enabled)")

        # Main loop for console updates
        update_console_screen(args, handle_terminate, status_lines)

    except KeyboardInterrupt:
        handle_terminate(None, None)
    finally:
        if executor:
            executor.shutdown(wait=True)


def get_console_refresh_time(start_time):
    """
    Returns the refresh interval (in seconds) for the console screen based on elapsed time.
    - 0-5 min: 5 sec
    - 5-10 min: 30 sec
    - 10-15 min: 60 sec
    - 15+ min: 120 sec
    """
    elapsed = time.time() - start_time
    if elapsed < 1 * 60:
        return 5
    elif elapsed < 2 * 60:
        return 30
    elif elapsed < 3 * 60:
        return 60
    else:
        return 120


def update_console_screen(args, handle_terminate, status_lines):
    # Main loop for top-like progress display
    start_time = time.time()
    try:
        while True:
            sys.stdout.write(f"\033[{len(status_lines) + 1}F")  # Move cursor up to start position

            # --- Always display the worker name here ---
            refresh_time = get_console_refresh_time(start_time)
            sys.stdout.write(f"\r[WorkerName] {args.worker_name} | Refresh: {refresh_time}s\033[K\n")

            # Loop through all keys in status_lines (category-log_name)
            shown = set()
            for key, line in status_lines.items():
                if '-' in key:
                    cat, log_name = key.split('-', 1)
                else:
                    cat, log_name = key, ''
                # 22 chars + []
                if log_name:
                    disp = f"{cat}: {log_name}"
                    cat_disp = f"[{disp:<22}]"
                else:
                    cat_disp = f"[{cat:<22}]"
                # Replace the first category name
                line_disp = re.sub(r"^\[.*?\]", cat_disp, line)
                sys.stdout.write(f"\r{line_disp}\033[K\n")
                shown.add(cat)
            # Fill in categories not displayed with 'waiting...'
            for cat in ordered_categories:
                if cat not in shown:
                    cat_disp = f"[{cat:<22}]"
                    line = f"{cat_disp} waiting..."
                    sys.stdout.write(f"\r{line}\033[K\n")
            sys.stdout.flush()
            sleep_with_stop_check(refresh_time)
    except KeyboardInterrupt:
        handle_terminate(None, None)


def update_console_message(status_lines, category, log_name, req_count, current, worker_jp_count, worker_total_count, end, task, start_time, omikuji, retry_count):
    # Clear status_lines if it gets too large
    if len(status_lines) > MAX_CONSOLE_LINES:
        status_lines.clear()

    retry_str = f" | ⏳Retry: {retry_count}" if retry_count > 0 else ""
    jp_ratio = (worker_jp_count / worker_total_count) if worker_total_count > 0 else 0
    total_count = end - task.get('start', 0) + 1
    done_count = current - task.get('start', 0)
    progress_pct = (done_count / total_count) * 100 if total_count > 0 else 0
    elapsed = time.time() - start_time
    speed = done_count / elapsed if elapsed > 0 else 0
    remain = total_count - done_count
    eta_sec = remain / speed if speed > 0 else 0
    if eta_sec > 0 and eta_sec < 86400:
        eta_h = int(eta_sec // 3600)
        eta_m = int((eta_sec % 3600) // 60)
        eta_str = f"{eta_h}h {eta_m}m"
        if eta_sec < 300:
            face = "🤩"
        elif eta_sec < 600:
            face = "😊"
        else:
            face = "🙂"
    elif eta_sec >= 86400:
        eta_d = int(eta_sec // 86400)
        eta_h = int((eta_sec % 86400) // 3600)
        eta_str = f"{eta_d}d {eta_h}h"
        face = "😥"
    else:
        eta_str = "--"
        face = "😩"
    status_key = f"{category}-{log_name}"
    status_lines[status_key] = (
        f"[{category}] 🌐 Req: {req_count} | 📍 Index: {current} | 🇯🇵 Domain: {worker_jp_count}({jp_ratio*100:.2f}%) | Progress: {progress_pct:.2f}% | ⏱️ ETA: {eta_str} {face} | {omikuji}{retry_str}"
    )

def report_worker_error(args, error_type, error_message, traceback_str, entry=None, log_name=None, ct_log_url=None, ct_index=None):
    payload = {
        "worker_name": getattr(args, "worker_name", "unknown"),
        "log_name": log_name or getattr(args, "log_name", None) or "unknown",
        "ct_log_url": ct_log_url or getattr(args, "ct_log_url", None) or "unknown",
        "ct_index": ct_index,
        "error_type": error_type,
        "error_message": error_message,
        "traceback": traceback_str,
        "entry": json.dumps(entry, separators=(',', ':')) if entry is not None else None
    }
    try:
        requests.post(f"{args.manager}/api/worker/error", json=payload, timeout=10)
    except Exception as post_e:
        logger.warning(f"[worker_error] failed to report error: {post_e}")


def extract_jp_certs(entries, log_name, ct_log_url, args, my_ip, current):
    jp_certs = []
    parser = JPCertificateParser()
    for i, entry in enumerate(entries):
        try:
            cert_data = parser.parse_only_jp_cert(entry)
        except Exception as e:
            tb = traceback.format_exc()
            ct_index = current + i

            # Save failed entry to tests/resources/failed directory
            try:
                failed_entry_data = {
                    "entry": entry,
                    "log_name": log_name,
                    "ct_log_url": ct_log_url,
                    "ct_index": ct_index,
                    "worker_name": args.worker_name,
                    "error_message": str(e),
                    "traceback": tb,
                    "timestamp": time.time()
                }
                failed_filename = f"failed_entry_{log_name}_{ct_index}_{uuid.uuid4().hex[:8]}.json"
                failed_filepath = os.path.join(FAILED_FILE_DIR, failed_filename)
                with open(failed_filepath, "w") as f:
                    json.dump(failed_entry_data, f, indent=2)
                logger.debug(f"Saved failed entry to {failed_filepath}")
            except Exception as save_e:
                logger.warning(f"Failed to save failed entry: {save_e}")

            report_worker_error(
                args=args,
                error_type="parse_error",
                error_message=str(e),
                traceback_str=tb,
                entry=entry,
                log_name=log_name,
                ct_log_url=ct_log_url,
                ct_index=ct_index
            )
            continue
        if cert_data:
            jp_certs.append({
                "ct_entry": json.dumps(entry, separators=(',', ':')),
                "ct_log_url": ct_log_url,
                "log_name": log_name,
                "worker_name": args.worker_name,
                "ct_index": current + i,
                "ip_address": my_ip,
                "issuer": cert_data.get('issuer'),
                "common_name": cert_data.get('subject_common_name')
            })
    return jp_certs


# --- JP certs filter for uniqueness ---
# Remove duplicate JP certificates
def filter_jp_certs_unique(jp_certs):
    seen = set()
    filtered = []
    for cert in jp_certs:
        key = (
            cert.get("issuer"),
            cert.get("serial_number"),
            cert.get("certificate_fingerprint_sha256"),
        )
        if key not in seen:
            seen.add(key)
            filtered.append(cert)
    return filtered

# --- upload_jp_certs: moved above worker_job_thread ---
# Upload JP certificates to the manager API
def upload_jp_certs(args, category, current, jp_certs, failed_lock):
    last_uploaded_index = None
    if jp_certs:
        url = f"{args.manager}/api/worker/upload"
        try:
            resp = requests.post(url, json=jp_certs, timeout=180)
            if resp.status_code == 200:
                last_uploaded_index = current
            else:
                logger.warning(f"[{category}] Upload failed: {resp.status_code} {resp.text}")
                with failed_lock:
                    save_pending_request({
                        "url": url,
                        "method": "POST",
                        "data": jp_certs
                    }, prefix="pending_upload")
        except Exception as e:
            logger.debug(f"[{category}] Upload exception: {e}")
            with failed_lock:
                save_pending_request({
                    "url": url,
                    "method": "POST",
                    "data": jp_certs
                }, prefix="pending_upload")
    return last_uploaded_index

# --- send_ping: moved above worker_job_thread ---
# Send a ping to the manager API to report progress and get updated intervals
def send_ping(args, category, log_name, ct_log_url, task, end, current, last_uploaded_index, worker_jp_count, worker_total_count, my_ip, last_ping_time, status="running", default_ping_seconds=180, default_ctlog_request_interval_sec=1):
    """
    The interval for sending pings is controlled by the API response's ping_interval_sec/ctlog_request_interval_sec.
    The number of failed_files and pending_files is included as query parameters.
    """
    now = time.time()
    if now - last_ping_time >= default_ping_seconds:
        jp_ratio = (worker_jp_count / worker_total_count) if worker_total_count > 0 else 0
        ping_data = {
            "worker_name": args.worker_name,
            "log_name": log_name,
            "ct_log_url": ct_log_url,
            "start": task.get('start'),
            "end": end,
            "current": current,
            "worker_total_count": worker_total_count,
            "last_uploaded_index": last_uploaded_index,
            "status": status,
            "jp_count": worker_jp_count,
            "jp_ratio": jp_ratio,
            "ip_address": my_ip
        }
        failed_files = len([f for f in os.listdir(FAILED_FILE_DIR) if os.path.isfile(os.path.join(FAILED_FILE_DIR, f))])
        pending_files = len([f for f in os.listdir(PENDING_FILE_DIR) if os.path.isfile(os.path.join(PENDING_FILE_DIR, f))])
        url = f"{args.manager}/api/worker/ping?failed_files={failed_files}&pending_files={pending_files}"
        ping_interval_sec = default_ping_seconds
        ctlog_request_interval_sec = default_ctlog_request_interval_sec
        try:
            resp = requests.post(url, json=ping_data)
            last_ping_time = now
            if resp.status_code == 200:
                try:
                    resp_json = resp.json()
                    ping_interval_sec = int(resp_json.get("ping_interval_sec", default_ping_seconds))
                    ctlog_request_interval_sec = int(resp_json.get("ctlog_request_interval_sec", default_ctlog_request_interval_sec))
                except Exception:
                    ping_interval_sec = default_ping_seconds
                    ctlog_request_interval_sec = default_ctlog_request_interval_sec
        except Exception as e:
            logger.debug(f"[{category}] ping failed: {e}")
            ping_interval_sec = default_ping_seconds
            ctlog_request_interval_sec = default_ctlog_request_interval_sec
        return last_ping_time, ping_interval_sec, ctlog_request_interval_sec
    return last_ping_time, default_ping_seconds, default_ctlog_request_interval_sec

def sleep_with_stop_check(seconds: int, stop_event: threading.Event = None):
    """
    Sleep for the specified number of seconds, but return immediately if stop_event is set.
    This wrapper ensures immediate termination on Ctrl+C, etc.
    """
    if stop_event is None:
        stop_event = get_stop_event()
    for _ in range(seconds):
        if stop_event and stop_event.is_set():
            break
        time.sleep(1)

def get_my_ip():
    return None
    ## Removed because of the privacy
    # try:
    #     resp = requests.get("https://ifconfig.io/ip", timeout=5)
    #     if resp.status_code == 200:
    #         return resp.text.strip()
    #     else:
    #         return "unknown"
    # except Exception:
    #     return "unknown"



# --- Startup manager API connectivity check ---
"""
When the API is stopped, prevent the worker from continuing to access the CT Log API unnecessarily.
This switch is triggered when the API's DNS record is deleted.
"""
def wait_for_manager_api_ready(manager_url):
    INTERVAL = 180
    parsed = urllib.parse.urlparse(manager_url)
    while True:
        try:
            # DNS resolution
            socket.gethostbyname(parsed.hostname)
        except Exception as e:
            logger.warning(f"[startup-check] The manager API seems unreachable. Retrying in 180s.")
            time.sleep(INTERVAL)
            continue
        logger.debug(f"[startup-check] Manager API DNS resolution succeeded.")
        break



global_tasks = {}
command_description = '''CT Log Fetcher

Project details:
TBD

Worker Ranking
http://ctlog-fetcher.tplinkdns.com/

Each CT Log API applies rate limits per public IP address.
Adding proxies can speed things up, but it costs money and puts a load on the CT Log API, so please don't overdo it.
PYTHONPATH=. python worker.py --proxy http://<your-proxy-url-1> --proxy http://<your-proxy-url-2> --worker-name <your-nick-name>
'''
def get_args():
    # Get default values from environment variables
    proxies_env = os.environ.get('PROXIES')
    worker_name_env = os.environ.get('WORKER_NAME')
    manager_url_env = os.environ.get('MANAGER_URL', 'http://ctlog-fetcher.tplinkdns.com:1173')
    debug_env = os.environ.get('DEBUG')
    max_threads_env = os.environ.get('MAX_THREADS', 10)  # Increasing threads increases worker traffic, so be careful

    parser = argparse.ArgumentParser(description=command_description)
    parser.add_argument(
        '--proxies',
        default=None,
        help='Proxy URL (comma-separated for multiple) ENV: PROXIES'
    )
    parser.add_argument(
        '--worker-name',
        default=worker_name_env if worker_name_env else default_worker_name(),
        help='Worker name (default: Japanese-style nickname. You can specify your own) ENV: WORKER_NAME'
    )
    parser.add_argument(
        '--manager',
        default=manager_url_env,
        help='Manager API base url ENV: MANAGER_URL'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        default=(str(debug_env).lower() in ['1', 'true', 'yes']),
        help='Enable debug logging ENV: DEBUG (1/true/yes)'
    )
    parser.add_argument(
        '--max-threads',
        type=int,
        default=int(max_threads_env),
        help='Maximum number of ThreadPoolExecutor workers (default: 10) ENV: MAX_THREADS'
    )
    args = parser.parse_args()

    # If --proxies is not specified, split PROXIES env var by comma into a list
    if args.proxies is not None:
        args.proxies = [p.strip() for p in args.proxies.split(',') if p.strip()]
    elif proxies_env:
        args.proxies = [p.strip() for p in proxies_env.split(',') if p.strip()]
    else:
        args.proxies = None
    return args


def validate_worker_name(worker_name):
    import re
    if worker_name is None or (isinstance(worker_name, str) and worker_name.strip() == ""):
        logger.warning("worker_name is empty or None. Using default_worker_name().")
        return default_worker_name()
    if not isinstance(worker_name, str):
        logger.warning("worker_name is not a string. Using default_worker_name().")
        return default_worker_name()
    if re.search(r"[ \t\n\r\'\";\\\\/]", worker_name):
        logger.warning("worker_name contains forbidden characters (whitespace, quotes, semicolon, slash, backslash, etc.). Using default_worker_name().")
        return default_worker_name()
    return worker_name

if __name__ == '__main__':
    args = get_args()

    # worker_name validation
    args.worker_name = validate_worker_name(args.worker_name)

    # Print args line by line
    for k, v in vars(args).items():
        print(f"{k}: {v}")


    wait_for_manager_api_ready(args.manager)

    try:
        main(args)
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"[main] Unhandled exception:\n{tb}")
        report_worker_error(
            error_type="main_error",
            error_message=str(e),
            traceback_str=tb
        )
