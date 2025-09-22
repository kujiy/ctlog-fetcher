# worker
import os
import sys
from typing import List, Optional, Dict

from src.manager_api.base_models import Categories, NextTaskCompleted, NextTask, WorkerNextTask
from src.worker import DEFAULT_CATEGORIES, NeedTreeSizeException, logger
from src.worker.worker_args import get_args
from src.worker.worker_base_models import CertCompareModel, WorkerArgs, CategoryThreadInfo, ThreadInfo
from src.worker.worker_common_funcs import stop_events, get_stop_event, sleep_with_stop_check, register_stop_event, \
    wait_for_manager_api_ready
from src.worker.worker_console import update_console_screen, update_console_message
from src.worker.worker_ctlog import fetch_ct_log
from src.worker.worker_error_handlings import report_worker_error, send_failed, handle_api_failure
from src.worker.worker_pings import send_ping, send_resume, send_completed
from src.worker.worker_retry_job import PENDING_FILE_DIR, retry_manager_unified
from src.worker.worker_upload import FAILED_FILE_DIR, upload_jp_certs, upload

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
import time
import requests
import threading
import logging
import sys
import random
import concurrent.futures
from src.share.job_status import JobStatus
import signal
import traceback
from src.config import WORKER_THREAD_MANAGER_INTERVAL_SEC
from collections import Counter

from dotenv import load_dotenv
load_dotenv()



os.makedirs(PENDING_FILE_DIR, exist_ok=True)
os.makedirs(FAILED_FILE_DIR, exist_ok=True)





def worker_job_thread(
    category: str, task: WorkerNextTask, args: WorkerArgs, global_tasks: Dict[str, WorkerNextTask], ctlog_request_interval_sec
) -> Optional[WorkerNextTask]:
    global status_lines
    proxies = args.proxies if args.proxies else None
    failed_uploads = []
    failed_lock = threading.Lock()

    task = WorkerNextTask(**task.dict())  # copy
    log_name = task.log_name
    current = task.start
    end = task.end
    ct_log_url = task.ct_log_url

    logger.debug(f"[DEBUG] Start job: category={category} log_name={log_name} start={current} end={end}")
    jobkey = f"{category}_{log_name}_{current}_{end}"
    global_tasks[jobkey] = task

    omikuji_list = ["大吉", "中吉", "小吉", "吉", "末吉", "凶"]
    req_count = 0
    last_ping_time = time.time()
    last_uploaded_index = None
    empty_entries_count = 0
    worker_jp_count = 0
    worker_total_count = 0

    # start time
    start_time = time.time()
    overdue_threshold_sec = 60 * 60  # 60 minutes
    overdue_task_sleep_sec = 60 * 30
    kill_me_now_then_sleep_sec = 0
    overdue = False

    # Add retry statistics tracking
    retry_stats = {
        'total_retries': 0,
        'max_retry_after': 0
    }

    need_tree_size = False

    my_stop_event = get_stop_event()

    try:
        jp_certs_buffer: List[CertCompareModel] = []
        ping_interval_sec = 60
        while current <= end and not my_stop_event.is_set():
            # if this job takes over 60 mins, break
            if time.time() - start_time > overdue_threshold_sec:
                overdue = True
                logger.warning(f"[WARN] Job exceeded 60 minutes, terminating... It seems you're facing the rate limit, so sleep {overdue_task_sleep_sec} secs... category={category} log_name={log_name} current={current} end={end}")
                # sleep 30 mins for allowing other workers to get through the rate limit
                sleep_with_stop_check(overdue_task_sleep_sec, my_stop_event)
                break
            if kill_me_now_then_sleep_sec:
                logger.warning(f"[WARN] kill_me flag is set, terminating job... Sleeping {kill_me_now_then_sleep_sec} sec... category={category} log_name={log_name} current={current} end={end}")
                sleep_with_stop_check(kill_me_now_then_sleep_sec, my_stop_event)
                break


            # logger.debug(f"[DEBUG] Loop: category={category} log_name={log_name} current={current} end={end}")
            omikuji = random.choice(omikuji_list)
            with failed_lock:
                retry_count = len(failed_uploads)
            update_console_message(status_lines, category, log_name, req_count, current, worker_jp_count,
                                   worker_total_count, end, task, start_time, omikuji, retry_count)

            # Check stop_event before API call
            if my_stop_event.is_set():
                logger.debug(f"[DEBUG] Stop event detected in worker_job_thread for {category}")
                break

            try:
                # Fetch a CT LOG API: always request up to end, but only process as many as returned
                entries = fetch_ct_log(ct_log_url, current, end, proxies, retry_stats, my_stop_event)
            except NeedTreeSizeException as e:
                logger.info(f"[{category}] NeedTreeSizeException caught: {e}. Completing job.")
                need_tree_size = True
                break

            req_count += 1
            actual_entry_size = len(entries)
            # logger.debug(f"[DEBUG] Fetched entries: {actual_entry_size} (current={current})")

            if empty_entries_count > 10:  # 1 + 2 + 4 + 8 + 16 + 32 + 60 + 60 + 60 + 60 = 303 seconds max wait(5 min)
                logger.warning(f"[WARN] Entries were empty 10 times in a row: category={category} log_name={log_name} current={current} end={end}")
                failed_sleep_sec = send_failed(args, log_name, ct_log_url, task, end, current,
                                               last_uploaded_index, worker_jp_count, worker_total_count,
                                               retry_stats['max_retry_after'], retry_stats['total_retries'])
                sleep_with_stop_check(failed_sleep_sec, my_stop_event)
                break
            if not entries:
                empty_entries_count += 1

                # Ping: some workers may take a long time to get entries, so ping here too
                last_ping_time, ping_interval_sec, ctlog_request_interval_sec, overdue_task_sleep_sec, kill_me_now_then_sleep_sec, overdue_threshold_sec = send_ping(
                    args, category, log_name, ct_log_url, task, end, current, last_uploaded_index,
                    worker_jp_count, worker_total_count, last_ping_time, status="running",
                    default_ping_seconds=ping_interval_sec, default_ctlog_request_interval_sec=ctlog_request_interval_sec,
                    max_retry_after=retry_stats['max_retry_after'], total_retries=retry_stats['total_retries']
                )

                # exponential backoff with max 60 seconds
                sleep_time = min(2 ** empty_entries_count, 60)
                sleep_with_stop_check(sleep_time, my_stop_event)
                continue
            else:
                empty_entries_count = 0

            # Check stop_event before processing
            if my_stop_event.is_set():
                logger.debug(f"[DEBUG] Stop event detected before processing for {category}")
                break

            # upload
            jp_certs_buffer, last_uploaded_index, worker_jp_count = upload(args, category, ct_log_url, current, entries,
                                                                           failed_lock, jp_certs_buffer,
                                                                           last_uploaded_index, log_name,
                                                                           worker_jp_count)

            worker_total_count += actual_entry_size

            # Ping
            last_ping_time, ping_interval_sec, ctlog_request_interval_sec, overdue_task_sleep_sec, kill_me_now_then_sleep_sec, overdue_threshold_sec = send_ping(
                args, category, log_name, ct_log_url, task, end, current, last_uploaded_index,
                worker_jp_count, worker_total_count, last_ping_time, status="running",
                default_ping_seconds=ping_interval_sec, default_ctlog_request_interval_sec=ctlog_request_interval_sec,
                max_retry_after=retry_stats['max_retry_after'], total_retries=retry_stats['total_retries']
            )

            # Use sleep_with_stop_check instead of time.sleep
            # logger.debug(f"ctlog_request_interval_sec: {ctlog_request_interval_sec}")
            sleep_with_stop_check(ctlog_request_interval_sec, my_stop_event)

            # if the entry is empty, it may loop infinitely, but it will break with empty_entries_count, so it's okay
            current += actual_entry_size
            task.current = current

        # Upload the remaining jp_certs anyway at the end of the job
        if jp_certs_buffer:
            last_uploaded_index = upload_jp_certs(args, category, current, jp_certs_buffer, failed_lock)
    except Exception as e:
        _tb = traceback.format_exc()
        _exc = sys.exc_info()

        logger.error(f"[{category}] Exception in worker_job_thread:\n{_tb}")
        report_worker_error(
            args=args,
            error_type="worker_job_thread_error",
            error_message=str(e),
            traceback_str=_tb + "---\n" + str(_exc),
            task=task.json(),
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
        task.status = JobStatus.COMPLETED
        global_tasks[jobkey].status = JobStatus.COMPLETED
        send_completed(args, log_name, ct_log_url, task, end, current, last_uploaded_index, worker_jp_count, worker_total_count,
                       retry_stats['max_retry_after'], retry_stats['total_retries'])
        expect_total_count = end - task.start + 1
        fetched_rate = worker_total_count / expect_total_count
        status_lines[status_key] = (
            f"[{category}] {console_msg} Commited {fetched_rate*100:.1f}% ({worker_total_count}/{expect_total_count}) | Range: {task.start} - {task.end}  | 🇯🇵 Domain: {worker_jp_count} | {random.choice(omikuji_list)}"
        )
    else:
        # Show "❌ Failed." only for abnormal termination(including Ctrl+C)
        console_msg = "❌ Failed."
        send_resume(task, overdue, kill_me_now_then_sleep_sec)
        expect_total_count = end - task.start + 1
        fetched_rate = worker_total_count / expect_total_count
        status_lines[status_key] = (
            f"[{category}] {console_msg} Commited {fetched_rate*100:.1f}% ({worker_total_count}/{expect_total_count}) | Range: {task.start} - {task.end}  | 🇯🇵 Domain: {worker_jp_count} | {random.choice(omikuji_list)}"
        )

    logger.debug(f"[DEBUG] Exit job: category={category} log_name={log_name} current={current} end={end}")
    return WorkerNextTask(**task.dict())  # task.copy()



def category_job_manager(category: str, args: WorkerArgs, global_tasks: Dict[str, WorkerNextTask], my_stop_event):
    logger.debug(f"category_job_manager: {category} ident={threading.get_ident()}")
    """Manager to sequentially fetch and execute jobs for each category (ThreadPoolExecutor version)"""
    last_job: WorkerNextTask = None
    fail_count = 0
    MAX_FAIL = 6
    task: NextTask | NextTaskCompleted = None
    ctlog_request_interval_sec = 1
    force_wait = False  # Flag to force waiting when last response was "all completed"

    try:
        while not my_stop_event.is_set():
            try:
                url = f"{args.manager}/api/worker/next_task?category={category}&worker_name={args.worker_name}"
                # logger.debug(url)
                resp = requests.get(url)
                # logger.debug(f"status_code: {resp.status_code}, body: {resp.text[:200]}")
                if resp.status_code == 200:
                    task_dict = resp.json()
                    # when the job is completed
                    if not task_dict or "start" not in task_dict:
                        # support the case where the API returns {"message": "all logs completed", "sleep_sec": ...}
                        if isinstance(task_dict, dict):
                            task = NextTaskCompleted(**task_dict)
                            if task.message == "all logs completed":
                                force_wait = True  # Set force_wait flag when all logs completed
                                sleep_sec = int(task.sleep_sec)
                                logger.info(f"{category}: collected all log_names, sleeping for {sleep_sec} seconds")
                                sleep_with_stop_check(sleep_sec, my_stop_event)
                            else:
                                force_wait = False  # Reset force_wait for other responses
                                logger.info(f"{category}: unexpected API response: no next job, waiting 60 seconds")
                                sleep_with_stop_check(60, my_stop_event)
                        else:
                            force_wait = False  # Reset force_wait for unexpected responses
                            logger.info(f"{category}: unexpected API response: no next job, waiting 60 seconds")
                            sleep_with_stop_check(60, my_stop_event)
                        continue

                    # normal next task
                    force_wait = False  # Reset force_wait when receiving a normal task
                    task = WorkerNextTask(
                        **task_dict,
                        manager=args.manager,
                        worker_name=args.worker_name,
                        status=JobStatus.RUNNING.value,
                    )
                    # Reset fail_count on successful retrieval
                    fail_count = 0
                    # Get ctlog_request_interval_sec from the next_task API (default to 1 if not present)
                    ctlog_request_interval_sec = int(task.ctlog_request_interval_sec)
                    last_job = WorkerNextTask(**task.dict())  # copy
                else:
                    logger.debug(f"{category}: failed to get next_task: {resp.status_code}")
                    fail_count += 1
                    # Wait for 2 seconds, but return immediately if stop_event is set
                    sleep_with_stop_check(10, my_stop_event)

                    # Try several times, and if it still fails, generate the task autonomously
                    result, fail_count, last_job = handle_api_failure(category, fail_count, last_job, MAX_FAIL, [task], args, force_wait)
                    if result:
                        # task autonomous generation
                        task = WorkerNextTask(**last_job.dict())  # copy
                    else:
                        continue
            except requests.exceptions.RequestException as e:
                # Communication errors are expected
                logger.debug(f"[{category}] Communication error getting next_task. The manager api might have been down. : {e}")
                fail_count += 1
                sleep_with_stop_check(1, my_stop_event)
                result, fail_count, last_job = handle_api_failure(category, fail_count, last_job, MAX_FAIL, [task], args, force_wait)
                if result:
                    task = WorkerNextTask(**last_job.dict())  # copy
                else:
                    continue
            except Exception as e:
                _tb = traceback.format_exc()
                _exc = sys.exc_info()
                logger.error(f"[{category}] Exception getting next_task (moving to the fail-safe mode):\n{_tb}")
                data = dict(
                    args=args,
                    error_type="category_job_manager_error",
                    error_message=str(e),
                    traceback_str=_tb + "---\n" + str(_exc)
                )
                if "task" in locals():
                    data["task"] = task
                report_worker_error(**data)

                fail_count += 1
                sleep_with_stop_check(1, my_stop_event)
                result, fail_count, last_job = handle_api_failure(category, fail_count, last_job, MAX_FAIL, [task], args, force_wait)
                if result:
                    task = WorkerNextTask(**last_job.dict())  # copy
                else:
                    continue

            if my_stop_event.is_set():
                break

            # # debug
            # task = WorkerNextTask(**{'ct_log_url': 'https://ct.googleapis.com/logs/us1/argon2025h1/', 'ctlog_request_interval_sec': 1,
            # 'ip_address': '12ca17b', 'log_name': 'argon2025h1', 'start': 1420256000, 'end': 1420271999, 'sth_end': 1602372213},
            #                       manager=args.manager,
            #                       worker_name=args.worker_name,
            #                       status=JobStatus.RUNNING.value)

            # Generate a worker_job_thread for each category
            try:
                completed_task = worker_job_thread(category, task, args, global_tasks, ctlog_request_interval_sec)
            except Exception as e:
                _tb = traceback.format_exc()
                _exc = sys.exc_info()

                logger.error(f"[{category}] Exception in job thread:\n{_tb}")
                report_worker_error(
                    args=args,
                    error_type="category_job_manager_jobthread_error",
                    error_message=str(e),
                    traceback_str=_tb + "---\n" + str(_exc),
                    task=task.json(),
                )
                completed_task = None
            if completed_task is not None:
                last_job = completed_task
            if not my_stop_event.is_set():
                logger.debug(f"{category}: job completed. Fetching next job")
    except Exception as e:
        _tb = traceback.format_exc()
        _exc = sys.exc_info()
        logger.error(f"[{category}] Exception in category_job_manager:\n{_tb}")
        data = dict(
            args=args,
            error_type="category_job_manager_fatal",
            error_message=str(e),
            traceback_str=_tb + "---\n" + str(_exc)
        )
        if "task" in locals():
            data["task"] = task
        print("task!")
        report_worker_error(**data)

    logger.debug(f"Exiting category job manager for {category}")



def category_job_manager_with_wrapper(category: str, args: WorkerArgs, global_tasks: Dict[str, WorkerNextTask], stop_event):
    register_stop_event(stop_event)
    category_job_manager(category, args, global_tasks, stop_event)


# --- Category Watcher Thread ---
def category_thread_manager(args: WorkerArgs, executor, category_thread_info: CategoryThreadInfo):
    """
    Periodically call /api/worker/categories and manage the increase/decrease of category threads.
    category_thread_info: { (category, idx): {"thread": future, "stop_event": event} }
    """
    register_stop_event()

    my_stop_event = get_stop_event()
    last_desired_counts: Counter = DEFAULT_CATEGORIES.copy()
    last_all_categories: List[str] = list(DEFAULT_CATEGORIES.keys())
    while not my_stop_event.is_set():
        try:
            desired_counts, all_categories = fetch_categories(args.manager, args.worker_name)
            # Only update if fetch_categories succeeded (i.e., did not fall back to DEFAULT_CATEGORIES)
            if desired_counts != DEFAULT_CATEGORIES:
                last_desired_counts = desired_counts
                last_all_categories = all_categories
        except Exception:
            # On any error, keep using last successful values
            pass

        # Use last successful values
        desired_counts: Counter = last_desired_counts
        all_categories: List[str] = last_all_categories

        # Get the current state of threads
        running_counts = {}
        info: ThreadInfo
        for (cat, idx), info in list(category_thread_info.data.items()):
            # info["thread"] is the return value of ThreadPoolExecutor.submit (Future)
            if info.thread.done():
                # Remove finished threads
                del category_thread_info.data[(cat, idx)]
                continue
            running_counts[cat] = running_counts.get(cat, 0) + 1

        # Immediately stop and remove threads for categories not in all_categories
        for (cat, idx), info in list(category_thread_info.data.items()):
            if cat not in all_categories:
                info.stop_event.set()
                del category_thread_info.data[(cat, idx)]

        # Thread scaling
        # 1. Increase
        for cat, desired in desired_counts.items():    # e.g. google, digicert...
            running = running_counts.get(cat, 0)      # e.g. google needs 3 threads
            for i in range(running, desired):        # Start new threads as needed
                # Start new threads for categories such as google, digicert, etc.
                stop_evt = threading.Event()
                future = executor.submit(category_job_manager_with_wrapper, cat, args, global_tasks, stop_evt)
                category_thread_info.data[(cat, i)] = ThreadInfo(thread=future, stop_event=stop_evt)
                time.sleep(1)

        # 2. Decrease
        for (cat, idx), info in list(category_thread_info.data.items()):
            desired = desired_counts.get(cat, 0)
            if idx >= desired:
                # Stop instruction
                info.stop_event.set()
                # No join (managed by ThreadPoolExecutor future)

        sleep_with_stop_check(WORKER_THREAD_MANAGER_INTERVAL_SEC)

def fetch_categories(domain: str, worker_name: str) -> (Counter, List[str]):
    global ordered_categories
    url = f"{domain}/api/worker/categories?worker_name={worker_name}"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            cats = Categories(**resp.json())
            # current API: {"all_categories": [...], "ordered_categories": [...]}
            all_categories = cats.all_categories
            ordered_categories = cats.ordered_categories
            desired_counts = Counter(ordered_categories)
            return desired_counts, all_categories
        # error
        desired_counts = DEFAULT_CATEGORIES
        all_categories = list(DEFAULT_CATEGORIES.keys())
    except Exception:
        desired_counts = DEFAULT_CATEGORIES
        all_categories = list(DEFAULT_CATEGORIES.keys())
    return desired_counts, all_categories


def main(args: WorkerArgs):
    global status_lines, global_tasks
    status_lines = {}
    executor = None
    futures = {}

    # --- Category thread management ---
    # Dictionary for managing category threads: (category, idx): {"thread": future, "stop_event": event}
    category_thread_info = CategoryThreadInfo(data={})  # (category, idx): {"thread": future, "stop_event": event}

    def handle_terminate(_signum, _frame):
        if getattr(handle_terminate, '_called', False):
            logger.debug("handle_terminate: already called, skipping duplicate execution.")
            return
        handle_terminate._called = True

        # Set stop_event for all threads
        for ev in list(stop_events.values()):
            ev.set()

        # Send resume requests for running jobs
        for category, task in global_tasks.items():
            if task.status == JobStatus.RUNNING and task.current | task.start < task.end:
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


global_tasks: Dict[str, WorkerNextTask] = {}


if __name__ == '__main__':
    args = get_args()

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
            args=args,
            error_type="main_error",
            error_message=str(e),
            traceback_str=tb
        )
