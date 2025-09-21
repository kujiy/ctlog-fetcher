import os
import time

import requests
from retry import retry

from src.manager_api.base_models import WorkerNextTask, WorkerPingBaseModel, WorkerResumeRequestModel
from src.share.job_status import JobStatus
from src.worker import logger
from src.worker.worker_error_handlings import save_pending_request
from src.worker.worker_upload import FAILED_FILE_DIR
from src.worker.worker_base_models import WorkerArgs, PendingRequest
from src.worker.worker_retry_job import PENDING_FILE_DIR


# --- send_ping: moved above worker_job_thread ---
# Send a ping to the manager API to report progress and get updated intervals
def send_ping(
        args: WorkerArgs, category, log_name, ct_log_url, task: WorkerNextTask, end, current, last_uploaded_index, worker_jp_count, worker_total_count, last_ping_time, status="running", default_ping_seconds=180, default_ctlog_request_interval_sec=1, max_retry_after=0, total_retries=0
) -> (int, int, int, int, int, int):
    """
    The interval for sending pings is controlled by the API response's ping_interval_sec/ctlog_request_interval_sec.
    The number of failed_files and pending_files is included as query parameters.
    """
    ping_interval_sec = default_ping_seconds
    ctlog_request_interval_sec = default_ctlog_request_interval_sec
    overdue_threshold_sec = 60 * 60  # 1 hour
    overdue_task_sleep_sec = 60 * 30
    kill_me_now_then_sleep_sec = 0
    now = time.time()
    if now - last_ping_time >= default_ping_seconds:
        jp_ratio = (worker_jp_count / worker_total_count) if worker_total_count > 0 else 0
        ping_data = WorkerPingBaseModel(
            worker_name=args.worker_name,
            log_name=log_name,
            ct_log_url=ct_log_url,
            start=task.start,
            end=end,
            current=current,
            last_uploaded_index=last_uploaded_index,
            status=status,
            jp_count=worker_jp_count,
            jp_ratio=jp_ratio,
            total_retries=total_retries,
            max_retry_after=max_retry_after,
        )
        failed_files = len([f for f in os.listdir(FAILED_FILE_DIR) if os.path.isfile(os.path.join(FAILED_FILE_DIR, f))])
        pending_files = len([f for f in os.listdir(PENDING_FILE_DIR) if os.path.isfile(os.path.join(PENDING_FILE_DIR, f))])
        url = f"{args.manager}/api/worker/ping?failed_files={failed_files}&pending_files={pending_files}"

        try:
            resp = requests.post(url, json=ping_data.dict())
            last_ping_time = now
            if resp.status_code == 200:
                try:
                    resp_json = resp.json()
                    ping_interval_sec = int(resp_json.get("ping_interval_sec", default_ping_seconds))
                    ctlog_request_interval_sec = int(resp_json.get("ctlog_request_interval_sec", default_ctlog_request_interval_sec))
                    overdue_task_sleep_sec = int(resp_json.get("overdue_task_sleep_sec", overdue_task_sleep_sec))
                    kill_me_now_then_sleep_sec = int(resp_json.get("kill_me_now_then_sleep_sec", 0))
                    overdue_threshold_sec = int(resp_json.get("overdue_threshold_sec", overdue_threshold_sec))
                except Exception:
                    ping_interval_sec = default_ping_seconds
                    ctlog_request_interval_sec = default_ctlog_request_interval_sec
        except Exception as e:
            logger.debug(f"[{category}] ping failed: {e}")
            ping_interval_sec = default_ping_seconds
            ctlog_request_interval_sec = default_ctlog_request_interval_sec
        return last_ping_time, ping_interval_sec, ctlog_request_interval_sec, overdue_task_sleep_sec, kill_me_now_then_sleep_sec, overdue_threshold_sec
    return last_ping_time, default_ping_seconds, default_ctlog_request_interval_sec, overdue_task_sleep_sec, kill_me_now_then_sleep_sec, overdue_threshold_sec


def send_resume(task: WorkerNextTask, kill_me_now_then_sleep_sec: int = 0, overdue=False):
    try:
        requests.post(
        f"{task.manager}/api/worker/resume_request?overdue={overdue}&kill_me_now_then_sleep_sec={kill_me_now_then_sleep_sec}",
            json=WorkerResumeRequestModel(
                worker_name=task.worker_name,
                log_name=task.log_name,
                ct_log_url=task.ct_log_url,
                start=task.start,
                end=task.end,
            ).dict(),
            timeout=10
        )
    except Exception as e:
        logger.debug(f"Failed to send resume_request: {e}")


@retry(tries=10, delay=20, jitter=(1, 10))
def send_completed(args, log_name, ct_log_url, task: WorkerNextTask, end, current, last_uploaded_index, worker_jp_count, worker_total_count, max_retry_after=0, total_retries=0):
    completed_data = WorkerPingBaseModel(
        worker_name=args.worker_name,
        log_name=log_name,
        ct_log_url=ct_log_url,
        start=task.start,
        end=end,
        current=current,
        last_uploaded_index=last_uploaded_index,
        status=JobStatus.COMPLETED.value,
        jp_count=worker_jp_count,
        jp_ratio=(worker_jp_count / worker_total_count) if worker_total_count > 0 else 0,
        max_retry_after=max_retry_after,
        total_retries=total_retries
    )
    url = f"{args.manager}/api/worker/completed"
    try:
        resp = requests.post(url, json=completed_data.dict(), timeout=1)
        resp.raise_for_status()
        logger.debug(f"[worker] completed api - successfully sent: {log_name} range={task.start}-{end}")
    except Exception as e:
        logger.debug(f"[worker] failed to send completed api: {e}")
        save_pending_request(PendingRequest(
            url=url,
            method="POST",
            data=completed_data.dict()
        ), prefix="pending_completed")
