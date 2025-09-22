import datetime
import os
import random
import uuid
from typing import Optional, List

import requests

from src.manager_api.base_models import WorkerNextTask, WorkerPingBaseModel, FailedResponse, NextTask
from src.share.job_status import JobStatus
from src.worker import logger

from src.worker.worker_base_models import WorkerArgs, PendingRequest
from src.worker.worker_common_funcs import sleep_with_stop_check, wait_for_manager_api_ready
from src.worker.worker_retry_job import PENDING_FILE_DIR


def report_worker_error(args: WorkerArgs, **kwargs):
    payload = dict(**kwargs)
    payload["args"] = str(args)
    print("payload")
    try:
        requests.post(f"{args.manager}/api/worker/error", json=payload, timeout=10)
    except Exception as post_e:
        logger.warning(f"[worker_error] failed to report error: {post_e}")


def send_failed(args, log_name, ct_log_url, task: WorkerNextTask, end, current, last_uploaded_index, worker_jp_count, worker_total_count, max_retry_after=0, total_retries=0):
    data = WorkerPingBaseModel(
        worker_name=args.worker_name,
        log_name=log_name,
        ct_log_url=ct_log_url,
        start=task.start,
        end=end,
        current=current,
        last_uploaded_index=last_uploaded_index,
        status=JobStatus.FAILED.value,
        jp_count=worker_jp_count,
        jp_ratio=(worker_jp_count / worker_total_count) if worker_total_count > 0 else 0,
        max_retry_after=max_retry_after,
        total_retries=total_retries
    )
    url = f"{args.manager}/api/worker/failed"
    try:
        resp = requests.post(url, json=data.dict(), timeout=80)
        resp.raise_for_status()
        logger.debug(f"[worker] failed api - successfully sent: {log_name} range={task.start}-{end}")
        return FailedResponse(**resp.json()).failed_sleep_sec
    except Exception as e:
        logger.debug(f"[worker] failed to send failed api: {e}")
    return 120


def handle_api_failure(
    category: str, fail_count, last_job: Optional[NextTask | WorkerNextTask], MAX_FAIL,
        task_ref: List[WorkerNextTask], args=None, force_wait=False
) -> (bool, int, NextTask):
    status = None
    jobkey = None
    if last_job:
        jobkey = f"{category}_{last_job.log_name}_{last_job.start}_{last_job.end}"
        global global_tasks
        if jobkey in global_tasks:
            status = global_tasks[jobkey].status
        else:
            status = last_job.status
    logger.debug(f"fail_count: {fail_count}/{MAX_FAIL}, jobkey: {jobkey}, status: {status}, force_wait: {force_wait}")
    if fail_count >= MAX_FAIL and last_job:
        # If force_wait is enabled (last response was "all completed"), don't generate autonomous tasks
        if force_wait:
            logger.info(f"{category}: API failure occurred but force_wait is enabled (last response was 'all completed'). Waiting for API recovery instead of autonomous task generation.")
            return False, fail_count, last_job
        
        batch_size = last_job.end - last_job.start + 1
        if status != JobStatus.COMPLETED:
            # If the job is incomplete, resume
            logger.warning(f"{category}: API failure/exception occurred {fail_count} times, resuming unfinished job (range: {last_job})")
            resume_task = WorkerNextTask(**last_job.dict())  # copy
            resume_task.current = resume_task.start
            resume_task.status = JobStatus.RUNNING
            task_ref[0] = resume_task
            return True, 0, resume_task
        else:
            # If the job is complete, perform DNS check before generating the next range job
            if args is not None:
                wait_for_manager_api_ready(args.manager)
            sth_end = last_job.sth_end | last_job.end
            if last_job.end + 1 >= sth_end:
                # when reach the end, wait for sth_end to be updated
                logger.warning(
                    f"{category}: API failure/exception occurred {fail_count} times, but end+1 >= sth_end ({last_job.end + 1} >= {sth_end}). Sleeping n seconds before retrying."
                )
                sleep_with_stop_check(60 * 10, None)  # 1分スリープ
                return False, fail_count, last_job
            else:
                # 通常通り、ランダムな値を選択
                next_start = random.randint(last_job.end + 1, sth_end) // 16000 * 16000  # pick a random start point aligned to 16000
            next_end = next_start + batch_size - 1
            if next_end > sth_end:
                next_end = sth_end
            logger.warning(
                f"{category}: API failure/exception occurred {fail_count} times, autonomously generating the next range job (next range: {next_start}-{next_end}): Autonomous recovery succeeded ✅")
            new_task = NextTask(**last_job.dict())   # copy()
            new_task.start = next_start
            new_task.current = next_start
            new_task.end = next_end
            new_task.status = JobStatus.RUNNING
            task_ref[0] = new_task
            return True, 0, new_task
    return False, fail_count, last_job


def save_pending_request(request_info: PendingRequest, prefix):
    """
    request_info: dict with keys: url, method, data
    prefix: e.g. 'pending_upload', 'pending_completed'
    """
    filename = pending_file_name(request_info.dict(), prefix)
    fname = os.path.join(PENDING_FILE_DIR, filename)

    with open(fname, "w") as f:
        f.write(request_info.json(indent=2))


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
