import random
from datetime import datetime, timedelta
from fastapi import Query, Depends, APIRouter, Request
from sqlalchemy import and_, select, text
from src.config import JST, BATCH_SIZE, MAX_THREADS_PER_WORKER, MAX_COMPLETED_JOBS_PER_DDOS_ADJUST_INTERVAL, \
    MIN_THREADS_PER_WORKER, DDOS_ADJUST_INTERVAL_MINUTES
from src.manager_api.db import get_async_session
from src.manager_api import locks
from src.manager_api.db_query import get_completed_thread_count_last_min, too_slow_log_names
from src.manager_api.models import CTLogSTH, WorkerStatus, LogFetchProgress
from src.config import CT_LOG_ENDPOINTS, LOG_FETCH_PROGRESS_TTL, \
    WORKER_CTLOG_REQUEST_INTERVAL_SEC, ORDERED_CATEGORIES, STH_FETCH_INTERVAL_SEC
from src.share.job_status import JobStatus
from src.manager_api.base_models import WorkerResumeRequestModel, NextTask, Categories, NextTaskCompleted
from cachetools import TTLCache
from asyncache import cached
from src.share.logger import logger
from src.share.utils import probabilistic_round_to_int, extract_ip_address_hash
from collections import Counter

router = APIRouter()

# --- Category Array API ---
@router.get("/api/worker/categories")
async def get_worker_categories(
        worker_name: str = Query("default"),
):
    #TODO: Use worker_name for rate limit avoidance
    """
    Returns a dict with all_categories and ordered_categories for worker dynamic thread management.
    Example:
    {
        "all_categories": ["cloudflare", "google", "trustasia", "letsencrypt", "digicert"],
        "ordered_categories": ["google", "google", "google"]
    }
    """
    all_categories = list(CT_LOG_ENDPOINTS.keys())
    ordered_categories = ORDERED_CATEGORIES.copy()
    # e.g. google 3, digicert 1, cloudflare 1, letsencrypt 1, trustasia 1
    random.shuffle(ordered_categories)

    # """
    # remove digicert with 1/n probability due to the rate limit
    # https://groups.google.com/a/chromium.org/g/ct-policy/c/XpmIf5DhfTg
    # """
    # if "digicert" in ordered_categories and random.randint(1, 3):
    #     ordered_categories.remove("digicert")

    ## we had too many dead workers by this unstable ordered_categories adjustment, so we disable it for now.
    # ordered_categories = await ddos_adjuster(db, ordered_categories)

    return Categories(
        all_categories=all_categories,
        ordered_categories=ordered_categories
    )
#
# # DDoS adjuster: limit number of categories according to number of running workers
# async def ddos_adjuster(db, ordered_categories):
#     total_completed_thread_count = await get_completed_thread_count_last_min(db, DDOS_ADJUST_INTERVAL_MINUTES)   # 100
#     max_cat_count = calculate_threads(total_completed_thread_count, MAX_COMPLETED_JOBS_PER_DDOS_ADJUST_INTERVAL)
#     # reduce len(ordered_categories) according to threads
#     ordered_categories = ordered_categories[:max_cat_count - 1]
#     return ordered_categories


def calculate_threads(total_completed_thread_count: int, limit: int) -> int:
    if total_completed_thread_count > limit:
        return random.randint(MIN_THREADS_PER_WORKER, probabilistic_round_to_int(MAX_THREADS_PER_WORKER * 0.5))
    return MAX_THREADS_PER_WORKER


@router.get("/api/worker/next_task")
async def get_next_task(
    request: Request,
    worker_name: str = Query("default"),
    category: str = Query(...),
    db=Depends(get_async_session)
) -> NextTask | NextTaskCompleted:
    if not worker_name:
        worker_name = "default"  # somehow Query default doesn't work
    ip_address_hash = extract_ip_address_hash(request)
    if category == "googledigicert":  # somehow some workers request with this invalid category
        category = "google"

    # Lock per worker_name and category
    async with locks[(worker_name, category)]:
        if category not in CT_LOG_ENDPOINTS:
            return {"message": f"Invalid category: {category}"}

        endpoints = CT_LOG_ENDPOINTS[category]

        # Exclude log_name of completed past CT Logs or current CT Logs that have almost been retrieved
        exclude_log_names = await get_almost_completed_log_names(db, category)
        ## Exclude log_name that the worker has failed or dead recently(rate limit avoidance)
        exclude_log_names += await get_failed_log_names_by(db, worker_name)
        # exclude_log_names += await get_dead_log_names_by(db, worker_name)
        # exclude_log_names += await rate_limit_candidate_log_names(db, worker_name)
        exclude_log_names += await too_slow_log_names(db, ip_address_hash)
        endpoints = [e for e in endpoints if e[0] not in exclude_log_names]

        random.shuffle(endpoints)

        for log_name, ct_log_url in endpoints:
            # logger.info(f"[next_task] checking log: {log_name}")
            tree_size = await get_tree_size(ct_log_url, db)
            if tree_size == 0:
                continue  # Skip logs with tree_size 0

            min_completed_end = await get_min_completed_end(db, log_name, category)
            if min_completed_end is not None:
                i = min_completed_end + BATCH_SIZE
            else:
                i = BATCH_SIZE - 1
            max_end = tree_size - 1  # CT Log starts from zero, so it exists up to tree_size - 1 in get-sth. Specifying more than this will result in an error.

            end_set = await get_end_listby_lob_name_with_running_or_completed(db, log_name, min_completed_end)
            # logger.info(f"[next_task] end_set for {log_name}: {end_set}")

            while i <= max_end:
                res: NextTask = await find_next_task(ct_log_url, db, end_set, i, log_name, worker_name, tree_size, ip_address_hash)
                if res:
                    return res
                i += BATCH_SIZE
            # Returns tasks ending in tree_size if the last task (max_end) is not included in the end_set
            if 0 < i - max_end <= BATCH_SIZE and max_end not in end_set:
                res: NextTask = await find_next_task(ct_log_url, db, end_set, max_end, log_name, worker_name, tree_size, ip_address_hash)
                if res:
                    return res
        # If all logs are collected, return sleep instruction to worker
        return NextTaskCompleted(message="all logs completed", sleep_sec=60 * 60)

    # # Temporary hardcoded: list of ranges where .jp domains can be obtained
    # hardcoded_jobs = [
    #     {"log_name": "nimbus2025", "ct_log_url": "https://ct.cloudflare.com/logs/nimbus2025/", "start": 27632088, "end": 27632119},
    #     {"log_name": "nimbus2025", "ct_log_url": "https://ct.cloudflare.com/logs/nimbus2025/", "start": 27632824, "end": 27632855},
    #     {"log_name": "nimbus2025", "ct_log_url": "https://ct.cloudflare.com/logs/nimbus2025/", "start": 27632856, "end": 27632887},
    #     {"log_name": "eu1_xenon2025h1", "ct_log_url": "https://ct.googleapis.com/logs/eu1/xenon2025h1/", "start": 1500000, "end": 1500099},
    #     {"log_name": "eu1_xenon2025h1", "ct_log_url": "https://ct.googleapis.com/logs/eu1/xenon2025h1/", "start": 1500200, "end": 1500299},
    #     {"log_name": "eu1_xenon2025h1", "ct_log_url": "https://ct.googleapis.com/logs/eu1/xenon2025h1/", "start": 1500600, "end": 1500699},
    #     {"log_name": "eu1_xenon2025h1", "ct_log_url": "https://ct.googleapis.com/logs/eu1/xenon2025h1/", "start": 1500800, "end": 1500899},
    #     {"log_name": "eu1_xenon2025h1", "ct_log_url": "https://ct.googleapis.com/logs/eu1/xenon2025h1/", "start": 1800001000, "end": 1800001999},
    #     {"log_name": "eu1_xenon2025h1", "ct_log_url": "https://ct.googleapis.com/logs/eu1/xenon2025h1/", "start": 959904, "end": 969903},
    #     {"log_name": "log2024", "ct_log_url": "https://ct2024.trustasia.com/log2024/", "start": 66956122, "end": 66956153},
    #     {"log_name": "log2024", "ct_log_url": "https://ct2024.trustasia.com/log2024/", "start": 66956858, "end": 66956889},
    #     {"log_name": "log2024", "ct_log_url": "https://ct2024.trustasia.com/log2024/", "start": 66957274, "end": 66957305},
    #     {"log_name": "log2024", "ct_log_url": "https://ct2024.trustasia.com/log2024/", "start": 66957786, "end": 66957817},
    #     {"log_name": "log2024", "ct_log_url": "https://ct2024.trustasia.com/log2024/", "start": 66959546, "end": 66959577},
    #     {"log_name": "log2024", "ct_log_url": "https://ct2024.trustasia.com/log2024/", "start": 66960730, "end": 66960761},
    #     {"log_name": "log2024", "ct_log_url": "https://ct2024.trustasia.com/log2024/", "start": 66961338, "end": 66961369},
    #     {"log_name": "log2024", "ct_log_url": "https://ct2024.trustasia.com/log2024/", "start": 66962042, "end": 66962073},
    #     {"log_name": "log2024", "ct_log_url": "https://ct2024.trustasia.com/log2024/", "start": 66965338, "end": 66965369},
    #     {"log_name": "log2024", "ct_log_url": "https://ct2024.trustasia.com/log2024/", "start": 66965754, "end": 66965785},
    #     {"log_name": "log2024", "ct_log_url": "https://ct2024.trustasia.com/log2024/", "start": 66967546, "end": 66967577},
    # ]
    # # You can filter here if you want to branch by worker_name or category
    # # This time, simply return in order (can also branch by round robin or worker_name)
    # # Example: determine index by hash of worker_name
    # idx = 0
    # if worker_name:
    #     idx = abs(hash(worker_name)) % len(hardcoded_jobs)
    # job = hardcoded_jobs[idx]
    # job["ip_address"] = None
    # return job


_min_completed_end_cache = TTLCache(maxsize=1024, ttl=LOG_FETCH_PROGRESS_TTL)

@cached(_min_completed_end_cache)
async def get_min_completed_end(db, log_name, category):
    stmt = select(LogFetchProgress.min_completed_end).where(
        LogFetchProgress.category == category,
        LogFetchProgress.log_name == log_name
    )
    row = (await db.execute(stmt)).first()
    return row[0] if row and row[0] is not None else None

async def get_end_listby_lob_name_with_running_or_completed(db, log_name, min_end=None):
    # Get distinct end values for this log (sorted ascending), optionally only those > min_end
    q = [
        WorkerStatus.log_name == log_name,
        WorkerStatus.status.in_([JobStatus.RUNNING.value, JobStatus.COMPLETED.value, JobStatus.SKIPPED.value])
    ]
    if min_end is not None:
        q.append(WorkerStatus.end > min_end)
    end_stmt = select(WorkerStatus.end).where(
        and_(*q)
    ).distinct().order_by(WorkerStatus.end.asc())
    end_results = (await db.execute(end_stmt)).all()
    end_set = set(row[0] for row in end_results)
    return end_set


async def find_next_task(ct_log_url, db, end_set, i, log_name, worker_name, tree_size, ip_address_hash) -> NextTask:
    if i in end_set:
        return None
    else:
        start = i - BATCH_SIZE + 1
        end = i
        if start < 0:
            start = 0

        # logger.info(f"[next_task] assigning task: log_name={log_name} start={start} end={end}")

        ws = await save_worker_status(ct_log_url, db, end, log_name, start, worker_name, ip_address_hash)

        return NextTask(
            log_name=log_name,
            ct_log_url=ct_log_url,
            start=start,
            end=end,
            sth_end=tree_size,
            ip_address=ws.ip_address,
            ctlog_request_interval_sec=WORKER_CTLOG_REQUEST_INTERVAL_SEC
        )


async def save_worker_status(ct_log_url, db, end, log_name, start, worker_name, ip_address_hash):
    now = datetime.now(JST)
    ws = WorkerStatus(
        worker_name=worker_name,
        log_name=log_name,
        ct_log_url=ct_log_url,
        start=start,
        end=end,
        current=start,
        status=JobStatus.RUNNING.value,
        last_ping=now,
        created_at=now,
        ip_address=ip_address_hash
    )
    db.add(ws)
    await db.commit()
    return ws


# resume_request: only when abnormal termination
@router.post("/api/worker/resume_request")
async def worker_resume_request(data: WorkerResumeRequestModel, db=Depends(get_async_session)):
    lock_key = (data.worker_name, data.log_name, data.start, data.end)
    async with locks[lock_key]:
        ws_stmt = select(WorkerStatus).where(
            WorkerStatus.log_name == data.log_name,
            WorkerStatus.worker_name == data.worker_name,
            WorkerStatus.status == JobStatus.RUNNING.value,
            WorkerStatus.start == data.start,
            WorkerStatus.end == data.end,
        )
        ws = (await db.execute(ws_stmt)).scalars().first()
        if ws:
            ws.status = JobStatus.RESUME_WAIT.value
            ws.last_ping = datetime.now(JST)
            ws.duration_sec = (datetime.now(JST) - ws.created_at.astimezone(JST)).total_seconds()
            await db.commit()
    return {"message": "ok"}



_tree_size_cache = TTLCache(maxsize=100, ttl=300)
@cached(_tree_size_cache)
async def get_tree_size(ct_log_url, db):
    stmt = select(CTLogSTH.tree_size).where(CTLogSTH.ct_log_url == ct_log_url).order_by(CTLogSTH.fetched_at.desc())
    row = (await db.execute(stmt)).first()
    value = row[0] if row and row[0] is not None else 0
    return value


@cached(TTLCache(maxsize=100, ttl=STH_FETCH_INTERVAL_SEC))
async def get_almost_completed_log_names(db, category):
    # Get all log_names and their fetch_rate for the category
    stmt = select(LogFetchProgress.log_name).where(
        LogFetchProgress.category == category,
        LogFetchProgress.fetch_rate == 1
    )
    rows = (await db.execute(stmt)).all()
    return [row[0] for row in rows]


@cached(TTLCache(maxsize=256, ttl=60*10))
async def get_failed_log_names_by(db, worker_name):
    # 30 minutes ago
    threshold = datetime.now(JST) - timedelta(minutes=30)
    # Get all log_names and their fetch_rate for the category
    stmt = select(WorkerStatus.log_name).where(
        WorkerStatus.status == JobStatus.FAILED.value,
        WorkerStatus.worker_name == worker_name,
        WorkerStatus.last_ping > threshold
    )
    rows = (await db.execute(stmt)).all()
    log_names = [row[0] for row in rows]
    if log_names and random.random() > 0.9:
        # remove random one element
        key = random.randint(0, len(log_names) - 1)
        log_names = log_names[:key] + log_names[key+1:]
    return log_names

# dead can also be triggered by Ctrl+C, so do not use it for rate limit determination.
@cached(TTLCache(maxsize=256, ttl=60*10))
async def get_dead_log_names_by(db, worker_name):
    # 30 minutes ago
    threshold = datetime.now(JST) - timedelta(minutes=30)
    # Get all log_names and their fetch_rate for the category
    stmt = select(WorkerStatus.log_name).where(
        WorkerStatus.status == JobStatus.DEAD.value,
        WorkerStatus.worker_name == worker_name,
        WorkerStatus.last_ping > threshold
    )
    rows = (await db.execute(stmt)).all()
    log_names = [row[0] for row in rows]  # ['nimbus2026', 'nimbus2025', 'nimbus2025', 'nimbus2025', 'nimbus2025', 'nimbus2025', 'nimbus2025']
    count = Counter(log_names)  # Counter({'nimbus2025': 6, 'nimbus2026': 1})
    return [log_name for log_name, c in count.items() if c > 10]  # if failed less than n times in the last 30 minutes



@cached(TTLCache(maxsize=256, ttl=60*10))
async def rate_limit_candidate_log_names(db, worker_name):
    """
    Return log_names that have high unsuccessful rate (dead + failed rate > 0.1)
    with 80% probability for each log to be included in the result.

    This helps avoid rate limiting by spreading the load and avoiding problematic logs.

    Uses raw SQL for better performance compared to multiple subqueries.
    """
    # n hours ago
    threshold = datetime.now(JST) - timedelta(hours=2)
    threshold_str = threshold.strftime("%Y-%m-%d %H:%M:%S")

    # Use raw SQL for better performance
    raw_sql = """
    SELECT
        log_name,
        ROUND((SUM(CASE WHEN status = 'dead' THEN 1 ELSE 0 END) + 
               SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END)) / 
              COUNT(*) * 1.0, 2) AS unsuccessful_rate
    FROM worker_status
    WHERE last_ping > :threshold
        AND status != :running_status
        AND worker_name = :worker_name
    GROUP BY worker_name, log_name
    """

    params = {
        "threshold": threshold_str,
        "running_status": JobStatus.RUNNING.value,
        "worker_name": worker_name
    }

    rows = (await db.execute(text(raw_sql), params)).all()

    # Filter logs with unsuccessful_rate > 0.1 and include with n% probability
    rate_limited_logs = []
    for row in rows:
        log_name, unsuccessful_rate = row
        # Include logs with unsuccessful_rate > 0.1 with n% probability
        if unsuccessful_rate > 0.1 and random.random() < 0.9:
            rate_limited_logs.append(log_name)

    return rate_limited_logs