# FastAPI entry point template
import random
import logging
import os
import json

from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

# FastAPIエントリポイント雛形
from fastapi import FastAPI, Query, Depends
from typing import List
from .models import CTLogSTH, WorkerLogStat, WorkerStatus, Cert, UploadStat, UniqueCert
from src.share.cert_parser import JPCertificateParser
from sqlalchemy import func, and_, select
from sqlalchemy.exc import IntegrityError
from .db import get_async_session, init_engine
from datetime import datetime, timedelta, timezone
import asyncio
from src.share.job_status import JobStatus
from .certificate_cache import cert_cache
# --- バックグラウンドジョブ起動 ---
from .background_jobs.sth_fetcher import start_sth_fetcher
from .background_jobs.worker_liveness import start_worker_liveness_monitor
from .background_jobs.unique_certs_counter import start_unique_certs_counter, get_unique_certs_count
from .background_jobs.log_fetch_progress import start_log_fetch_progress
from ..config import CT_LOG_ENDPOINTS, BACKGROUND_JOBS_ENABLED, ETA_BASE_DATE, LOG_FETCH_PROGRESS_TTL, WORKER_CTLOG_REQUEST_INTERVAL_SEC, WORKER_PING_INTERVAL_SEC
from .base_models import WorkerPingModel, WorkerPingBaseModel, WorkerResumeRequestModel, UploadCertItem, WorkerErrorModel
import datetime as dt
from ..share.animal import get_worker_emoji
from cachetools import TTLCache
from asyncache import cached

# JST timezone
JST = timezone(timedelta(hours=9))

BATCH_SIZE = 16000

"""
# Interval (seconds) at which the worker accesses the CT log
If this value is set too high, the worker will be mostly idle, and instructions from the manager API will not be reflected to the worker.
Like communicating with a spaceship, it is desirable to set the interval to several minutes to several tens of minutes at most, so that communication can occur at a reasonable frequency.
"""

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
logger = app.logger = logging.getLogger("manager_api")

@app.middleware("http")
async def store_request_body(request: Request, call_next):
    body = b""
    async for chunk in request.stream():
        body += chunk
    request.state.body = body

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    request._receive = receive
    response = await call_next(request)
    return response

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    body = getattr(request.state, "body", b"")
    response_content = {"detail": exc.errors(), "body": exc.body}
    logger.warning(
        f"422 Unprocessable Entity: path={request.url.path}, body={body.decode('utf-8')}, response={response_content}"
    )
    return JSONResponse(
        status_code=422,
        content=response_content,
    )

lock = asyncio.Lock()


@app.on_event("startup")
async def on_startup():
    # Delayed initialization of DB engine
    init_engine()
    if BACKGROUND_JOBS_ENABLED:
        app.state.background_tasks = []
        app.state.background_tasks.append(start_sth_fetcher())
        app.state.background_tasks.append(start_worker_liveness_monitor())
        app.state.background_tasks.append(start_unique_certs_counter())
        app.state.background_tasks.append(start_log_fetch_progress())
        logger.info("Background jobs started and tasks stored in app.state.background_tasks")

@app.on_event("shutdown")
async def on_shutdown():
    tasks = getattr(app.state, "background_tasks", [])
    for t in tasks:
        if t is not None:
            t.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    logger.info("Background jobs cancelled on shutdown")

# launch_background_jobsは不要になるため削除


@app.get("/api/worker/next_task")
async def get_next_task(
    worker_name: str = Query(...),
    category: str = Query(...),
    db=Depends(get_async_session)
):
    async with lock:
        if category not in CT_LOG_ENDPOINTS:
            return {"message": f"Invalid category: {category}"}

        endpoints = CT_LOG_ENDPOINTS[category]
        # endpoints = [("xenon2022", "https://ct.googleapis.com/logs/xenon2022/")]  # debug

        logger.info(f"[next_task] category={category} endpoints={endpoints}")

        random.shuffle(endpoints)

        for log_name, ct_log_url in endpoints:
            logger.info(f"[next_task] checking log: {log_name}")

            tree_size = await get_tree_size(ct_log_url, db)
            if tree_size == 0:
                continue  # Skip logs with tree_size 0

            min_completed_end = await get_min_completed_end(db, log_name, category)
            if min_completed_end is not None:
                i = min_completed_end + BATCH_SIZE
            else:
                i = BATCH_SIZE - 1
            max_end = tree_size - 1

            end_list = await get_end_listby_lob_name_with_running_or_completed(db, log_name, min_completed_end)
            logger.info(f"[next_task] end_list for {log_name}: {end_list}")

            while i <= max_end:
                res = await find_next_task(ct_log_url, db, end_list, i, log_name, worker_name)
                if res:
                    return res
                i += BATCH_SIZE
            # end for log_name
        # If all logs are collected, return sleep instruction to worker
        return {"message": "all logs completed", "sleep_sec": 120}

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


_min_completed_end_cache = TTLCache(maxsize=256, ttl=LOG_FETCH_PROGRESS_TTL)

@cached(_min_completed_end_cache)
async def get_min_completed_end(db, log_name, category):
    from .models import LogFetchProgress
    stmt = select(LogFetchProgress.min_completed_end).where(
        LogFetchProgress.log_name == log_name,
        LogFetchProgress.category == category
    )
    row = (await db.execute(stmt)).first()
    return row[0] if row and row[0] is not None else None

async def get_end_listby_lob_name_with_running_or_completed(db, log_name, min_end=None):
    # Get distinct end values for this log (sorted ascending), optionally only those > min_end
    q = [
        WorkerStatus.log_name == log_name,
        WorkerStatus.status.in_([JobStatus.RUNNING.value, JobStatus.COMPLETED.value])
    ]
    if min_end is not None:
        q.append(WorkerStatus.end > min_end)
    end_stmt = select(WorkerStatus.end).where(
        and_(*q)
    ).distinct().order_by(WorkerStatus.end.asc())
    end_results = (await db.execute(end_stmt)).all()
    end_list = [row[0] for row in end_results]
    return end_list


async def find_next_task(ct_log_url, db, end_list, i, log_name, worker_name):
    if i in end_list:
        return None
    else:
        start = i - BATCH_SIZE + 1
        end = i
        if start < 0:
            start = 0

        logger.info(f"[next_task] assigning task: log_name={log_name} start={start} end={end}")

        ws = await save_worker_status(ct_log_url, db, end, log_name, start, worker_name)

        return {
            "log_name": log_name,
            "ct_log_url": ct_log_url,
            "start": start,
            "end": end,
            "ip_address": ws.ip_address,
            "ctlog_request_interval_sec": WORKER_CTLOG_REQUEST_INTERVAL_SEC
        }


async def save_worker_status(ct_log_url, db, end, log_name, start, worker_name):
    ws = WorkerStatus(
        worker_name=worker_name,
        log_name=log_name,
        ct_log_url=ct_log_url,
        start=start,
        end=end,
        current=start,
        status=JobStatus.RUNNING.value,
        last_ping=None,
        ip_address=None
    )
    db.add(ws)
    await db.commit()
    return ws



@app.post("/api/worker/upload")
async def upload_certificates(
    items: List[UploadCertItem],
    db=Depends(get_async_session)
):
    logger.debug(f"[upload_certificates] Received {len(items)} items for upload")
    inserted = 0
    skipped_duplicates = 0
    parser = JPCertificateParser()

    # List for batch processing
    certs_to_insert = []

    for item in items:
        # Extract only .jp certificates
        try:
            entry_dict = json.loads(item.ct_entry)
            cert_data = parser.parse_only_jp_cert(entry_dict)
        except Exception as e:
            logger.debug(f"[upload_certificates] Error parsing CT entry for item: {item}")
            continue
        if not cert_data:
            continue

        # Get values for duplicate check
        issuer = cert_data.get('issuer')
        serial_number = cert_data.get('serial_number')
        certificate_fingerprint_sha256 = cert_data.get('certificate_fingerprint_sha256')

        # Fast duplicate check with memory cache
        dup = await cert_cache.is_duplicate(issuer, serial_number, certificate_fingerprint_sha256)
        if dup:
            skipped_duplicates += 1
            continue  # Skip duplicates (no DB query)

        # Map to all fields of Cert model
        cert = Cert(
            serial_number=serial_number,
            issuer=issuer,
            not_before=cert_data.get('not_before'),
            not_after=cert_data.get('not_after'),
            common_name=cert_data.get('subject_common_name'),
            subject_alternative_names=cert_data.get('subject_alternative_names'),
            san_count=cert_data.get('san_count'),
            certificate_fingerprint_sha256=certificate_fingerprint_sha256,
            public_key_algorithm=cert_data.get('public_key_algorithm'),
            key_size=cert_data.get('key_size'),
            signature_algorithm=cert_data.get('signature_algorithm'),
            ct_log_timestamp=cert_data.get('ct_log_timestamp'),
            crl_urls=cert_data.get('crl_urls'),
            ocsp_urls=cert_data.get('ocsp_urls'),
            issued_on_weekend=cert_data.get('issued_on_weekend'),
            issued_at_night=cert_data.get('issued_at_night'),
            organization_type=cert_data.get('organization_type'),
            is_wildcard=cert_data.get('is_wildcard'),
            root_ca_issuer_name=cert_data.get('root_ca_issuer_name'),
            subject_public_key_hash=cert_data.get('subject_public_key_hash'),
            log_name=item.log_name,
            worker_name=item.worker_name,
            ct_log_url=item.ct_log_url,
            created_at=datetime.now(JST),
            ct_index=item.ct_index,
            ct_entry=item.ct_entry,
            is_precertificate=cert_data.get('is_precertificate'),
            vetting_level=cert_data.get('vetting_level')
        )
        certs_to_insert.append(cert)

    # Batch INSERT (prevent duplicates with DB constraints)
    if certs_to_insert:
        try:
            # Try batch insert
            db.add_all(certs_to_insert)
            await db.commit()
            inserted = len(certs_to_insert)

            # Register successfully inserted certificates in cache
            for cert in certs_to_insert:
                await cert_cache.add(cert.issuer, cert.serial_number, cert.certificate_fingerprint_sha256)

            logger.debug(f"[upload_certificates] Batch insert successful: {inserted} certs")

        except IntegrityError as e:
            # On duplicate error, process one by one
            logger.debug(f"[upload_certificates] Batch insert failed due to duplicates, falling back to individual inserts")
            await db.rollback()
            for cert in certs_to_insert:
                try:
                    db.add(cert)
                    await db.commit()
                    inserted += 1
                    # Register in cache only on success
                    await cert_cache.add(cert.issuer, cert.serial_number, cert.certificate_fingerprint_sha256)
                except IntegrityError:
                    # Duplicate error (if unique index exists)
                    await db.rollback()
                    skipped_duplicates += 1
                    # Add to cache as duplicate (for skipping next time)
                    await cert_cache.add(cert.issuer, cert.serial_number, cert.certificate_fingerprint_sha256)

    # Output cache statistics to log (for debugging)
    if logger.isEnabledFor(logging.DEBUG):
        cache_stats = await cert_cache.get_stats()
        logger.debug(f"[upload_certificates] Cache stats: hit_rate={cache_stats['hit_rate']:.2%}, "
                    f"size={cache_stats['cache_size']}, hits={cache_stats['hit_count']}, "
                    f"misses={cache_stats['miss_count']}")

    logger.debug(f"[upload_certificates] Result: inserted={inserted}, skipped_duplicates={skipped_duplicates}")
    return {"inserted": inserted, "skipped_duplicates": skipped_duplicates}




# --- Overall Progress API ---
@app.get("/api/logs_summary")
async def get_logs_summary(db=Depends(get_async_session)):

    # --- Total tree size ---
    sth_rows_stmt = select(
        CTLogSTH.log_name, func.max(CTLogSTH.fetched_at).label('max_fetched_at')
    ).group_by(CTLogSTH.log_name).subquery()
    total_tree_stmt = select(func.sum(CTLogSTH.tree_size)).join(
        sth_rows_stmt,
        (CTLogSTH.log_name == sth_rows_stmt.c.log_name) & (CTLogSTH.fetched_at == sth_rows_stmt.c.max_fetched_at)
    )
    total_tree_size = (await db.execute(total_tree_stmt)).scalar() or 0

    # --- Fetched tree size (from summary table) ---
    fetched_tree_stmt = select(func.sum(WorkerLogStat.worker_total_count))
    fetched_tree_size = (await db.execute(fetched_tree_stmt)).scalar() or 0
    if fetched_tree_size < 0:
        fetched_tree_size = 0

    # --- Fetched rate ---
    fetched_rate = (fetched_tree_size / total_tree_size) if total_tree_size > 0 else 0

    # --- ETA (days) ---
    today = ETA_BASE_DATE
    now = dt.datetime.now(JST).date()
    days_elapsed = (now - today).days if (now - today).days > 0 else 1
    eta_days = None
    if fetched_rate > 0 and fetched_rate < 1:
        eta_days = int(days_elapsed * (1 - fetched_rate) / fetched_rate)
    elif fetched_rate >= 1:
        eta_days = 0

    # --- .jp count and ratio (from summary table) ---
    total_jp_stmt = select(func.sum(WorkerLogStat.jp_count_sum))
    total_jp = (await db.execute(total_jp_stmt)).scalar() or 0
    jp_ratio = (total_jp / fetched_tree_size) if fetched_tree_size > 0 else 0

    # --- Unique .jp count ---
    unique_jp_count = get_unique_certs_count()

    # --- Unique .jp ratio ---
    unique_jp_ratio = (unique_jp_count / fetched_tree_size) if isinstance(unique_jp_count, int) and fetched_tree_size > 0 else 0

    return {
        "total_tree_size": total_tree_size,
        "fetched_tree_size": fetched_tree_size,
        "fetched_rate": fetched_rate,
        "eta_days": eta_days,
        "total_jp": total_jp,
        "jp_ratio": jp_ratio,
        "unique_jp_count": unique_jp_count,
        "unique_jp_ratio": unique_jp_ratio
    }



# Progress information per log
@app.get("/api/logs_progress")
async def get_logs_progress(db=Depends(get_async_session)):
    # Get the latest tree_size for each log_name
    sth_map = {}
    subq = select(
        CTLogSTH.log_name,
        func.max(CTLogSTH.fetched_at).label('max_fetched_at')
    ).group_by(CTLogSTH.log_name).subquery()
    sth_stmt = select(CTLogSTH.log_name, CTLogSTH.tree_size).join(
        subq,
        and_(CTLogSTH.log_name == subq.c.log_name, CTLogSTH.fetched_at == subq.c.max_fetched_at)
    )
    sth_rows = (await db.execute(sth_stmt)).all()
    for log_name, tree_size in sth_rows:
        sth_map[log_name] = tree_size

    # Enumerate all combinations of log_name/ct_log_url
    all_logs = []
    for cat, endpoints in CT_LOG_ENDPOINTS.items():
        for log_name, ct_log_url in endpoints:
            all_logs.append((log_name, ct_log_url))

    logs = []
    for log_name, ct_log_url in all_logs:
        stat_stmt = select(WorkerLogStat).where(WorkerLogStat.log_name==log_name)
        stat_rows = (await db.execute(stat_stmt)).scalars().all()
        total_fetched = sum([s.worker_total_count or 0 for s in stat_rows])
        jp_count = sum([s.jp_count_sum or 0 for s in stat_rows])
        jp_ratio = (jp_count / total_fetched) if total_fetched > 0 else 0
        tree_size = sth_map.get(log_name)
        logs.append({
            "log_name": log_name,
            "total_fetched": total_fetched,
            "jp_count": jp_count,
            "jp_ratio": jp_ratio,
            "tree_size": tree_size,
            "ct_log_url": ct_log_url
        })
    total = sum([l["total_fetched"] for l in logs])
    return {
        "summary": {"total": total, "logs": len(logs)},
        "logs": logs
    }

# Status information per worker
@app.get("/api/workers_status")
async def get_workers_status(db=Depends(get_async_session)):
    workers = []
    # Sort by last_ping desc, then limit to 100 records
    stmt = select(WorkerStatus).order_by(WorkerStatus.last_ping.desc()).limit(100)
    last_100 = (await db.execute(stmt)).scalars().all()
    for w in last_100:
        expected_total_count = (w.end - w.start + 1) if w.end and w.start is not None else 1
        progress = (w.current - w.start) / expected_total_count if expected_total_count > 0 else 0
        workers.append({
            "worker_name": f"{get_worker_emoji(w.worker_name)} {w.worker_name}",
            "log_name": w.log_name,
            "current": w.current,
            "progress": progress,
            "last_ping": w.last_ping.isoformat() if w.last_ping else None,
            "status": w.status,
            "worker_fetched_count": w.current - w.start,
            "last_uploaded_index": getattr(w, 'last_uploaded_index', None),
            "jp_count": w.jp_count,
            "jp_ratio": w.jp_ratio,
            "ip_address": w.ip_address,
            "start": w.start,
            "end": w.end
        })
    return {
        "summary": {
            "workers": len(workers),
            "recent_worker_names": len(set(w['worker_name'] for w in workers)),
            "last_updated": last_100[0].last_ping.isoformat() if last_100 else "-",
        },
        "workers": workers
    }


# ワーカーごとのランキングAPI
@app.get("/api/worker_ranking")
async def get_worker_ranking(db=Depends(get_async_session)):
    stmt = select(
        WorkerLogStat.worker_name,
        func.sum(WorkerLogStat.worker_total_count).label('worker_total_count'),
        func.sum(WorkerLogStat.jp_count_sum).label('jp_count_sum')
    ).group_by(WorkerLogStat.worker_name)
    rows = (await db.execute(stmt)).all()
    worker_total_count_ranking = []
    jp_ranking = []
    for r in rows:
        worker_name = f"{get_worker_emoji(r[0])} {r[0]}"
        worker_total_count = r[1]
        jp_count = r[2] or 0
        jp_ratio = (jp_count / worker_total_count) if worker_total_count > 0 else 0
        worker_total_count_ranking.append({
            "worker_name": worker_name,
            "worker_total_count": worker_total_count,
            "jp_count": jp_count,
            "jp_ratio": jp_ratio
        })
        jp_ranking.append({
            "worker_name": worker_name,
            "jp_count": jp_count,
            "jp_ratio": jp_ratio
        })
    worker_total_count_ranking = sorted(worker_total_count_ranking, key=lambda x: x["worker_total_count"], reverse=True)
    jp_ranking = sorted(jp_ranking, key=lambda x: x["jp_count"], reverse=True)
    return {
        "worker_total_count_ranking": worker_total_count_ranking,
        "jp_count_ranking": jp_ranking
    }




async def update_worker_status_and_summary(data: WorkerPingModel | WorkerPingBaseModel, db, status_value):
    async with lock:
        ws_stmt = select(WorkerStatus).where(
            WorkerStatus.log_name==data.log_name,
            WorkerStatus.start==data.start,
            WorkerStatus.end==data.end
        )
        ws = (await db.execute(ws_stmt)).scalars().first()
        if ws:
            ws.worker_name = data.worker_name
            ws.current = data.current
            ws.status = status_value
            ws.last_ping = datetime.now(JST)
            ws.ip_address = data.ip_address
            ws.last_uploaded_index = data.last_uploaded_index
            ws.jp_count = data.jp_count
            ws.jp_ratio = data.jp_ratio
            await db.commit()
            # --- サマリーテーブル更新 ---
            stat_stmt = select(WorkerLogStat).where(
                WorkerLogStat.log_name==ws.log_name,
                WorkerLogStat.worker_name==ws.worker_name
            )
            stat = (await db.execute(stat_stmt)).scalars().first()
            if not stat:
                stat = WorkerLogStat(log_name=ws.log_name, worker_name=ws.worker_name)
                db.add(stat)
            # completed APIのみでjp_count_sumを加算する
            if status_value == JobStatus.COMPLETED.value:
                stat.worker_total_count = (stat.worker_total_count or 0) + (data.end - data.start + 1)
                stat.jp_count_sum = (stat.jp_count_sum or 0) + (ws.jp_count or 0)
            stat.last_updated = datetime.now(JST)
            await db.commit()
    return {"message": "ok"}


"""
workerはfailed_filesとpending_filesの数をクエリパラメータとして付与します。
これらのクエリパラメータはAPIサーバ側では一切処理されません。アクセスログ用途のみです。
"""
# ping: runningのみ
@app.post("/api/worker/ping")
async def worker_ping(data: WorkerPingModel, db=Depends(get_async_session)):
    await update_worker_status_and_summary(data, db, JobStatus.RUNNING.value)
    return {
        "ping_interval_sec": WORKER_PING_INTERVAL_SEC,
        "ctlog_request_interval_sec": WORKER_CTLOG_REQUEST_INTERVAL_SEC
    }

# completed: job完了時のみ
@app.post("/api/worker/completed")
async def worker_completed(data: WorkerPingBaseModel, db=Depends(get_async_session)):
    return await update_worker_status_and_summary(data, db, JobStatus.COMPLETED.value)

# resume_request: 異常終了時のみ
@app.post("/api/worker/resume_request")
async def worker_resume_request(data: WorkerResumeRequestModel, db=Depends(get_async_session)):
    async with lock:
        ws_stmt = select(WorkerStatus).where(
            WorkerStatus.log_name==data.log_name,
            WorkerStatus.start==data.start,
            WorkerStatus.end==data.end
        )
        ws = (await db.execute(ws_stmt)).scalars().first()
        if ws:
            ws.status = JobStatus.RESUME_WAIT.value
            ws.last_ping = datetime.now(JST)
            await db.commit()
    return {"message": "ok"}




@app.post("/api/worker/error")
async def worker_error(data: WorkerErrorModel):
    # worker_errors.logに追記（JSON Lines形式）
    log_path = os.path.join(os.path.dirname(__file__), "worker_errors.log")
    try:
        with open(log_path, "a") as f:
            f.write(json.dumps(data.model_dump(), ensure_ascii=False) + "\n")
    except Exception as e:
        logging.getLogger("worker_error_api").error(f"Failed to write worker error: {e}")
    return {"message": "ok"}




# --- Category Array API ---
@app.get("/api/worker/categories")
async def get_worker_categories():
    """
    Returns a dict with all_categories and ordered_categories for worker dynamic thread management.
    Example:
    {
        "all_categories": ["cloudflare", "google", "trustasia", "letsencrypt", "digicert"],
        "ordered_categories": ["google", "google", "google"]
    }
    """
    all_categories = list(CT_LOG_ENDPOINTS.keys())

    # 例: google3本, 他1本ずつ
    ordered_categories = []
    ordered_categories.extend(["google"] * 3)
    ordered_categories.extend(["digicert"] * 1)
    ordered_categories.extend(["cloudflare"] * 1)
    ordered_categories.extend(["letsencrypt"] * 1)
    ordered_categories.extend(["trustasia"] * 1)
    random.shuffle(ordered_categories)
    return {
        "all_categories": all_categories,
        "ordered_categories": ordered_categories
    }

# --- Unique Certs API ---
@app.get("/api/unique_certs")
async def get_unique_certs(db=Depends(get_async_session)):
    stmt = select(Cert).order_by(Cert.id.desc()).limit(100)
    certs = (await db.execute(stmt)).scalars().all()

    result = []
    for cert in certs:
        result.append({
            "id": cert.id,
            "issuer": cert.issuer,
            "common_name": cert.common_name,
            "not_before": cert.not_before.isoformat() if cert.not_before else None,
            "not_after": cert.not_after.isoformat() if cert.not_after else None,
            "serial_number": cert.serial_number,
            "subject_alternative_names": cert.subject_alternative_names,
            "certificate_fingerprint_sha256": cert.certificate_fingerprint_sha256,
            "subject_public_key_hash": cert.subject_public_key_hash,
            "public_key_algorithm": cert.public_key_algorithm,
            "key_size": cert.key_size,
            "signature_algorithm": cert.signature_algorithm,
            "ct_log_timestamp": cert.ct_log_timestamp,
            "crl_urls": cert.crl_urls,
            "ocsp_urls": cert.ocsp_urls,
            "vetting_level": cert.vetting_level,
            "san_count": cert.san_count,
            "issued_on_weekend": cert.issued_on_weekend,
            "issued_at_night": cert.issued_at_night,
            "organization_type": cert.organization_type,
            "is_wildcard": cert.is_wildcard,
            "root_ca_issuer_name": cert.root_ca_issuer_name,
            "is_precertificate": cert.is_precertificate,
            "log_name": cert.log_name,
            "ct_index": cert.ct_index,
            "ct_log_url": cert.ct_log_url,
            "worker_name": cert.worker_name,
            "created_at": cert.created_at.isoformat() if cert.created_at else None,
            "ct_entry": cert.ct_entry,
        })

    return {
        "count": len(result),
        "unique_certs": result
    }


# --- Fetched Certs by Worker API ---
@app.get("/api/fetched_certs/{worker_name}")
async def get_fetched_certs_by_worker(worker_name: str, db=Depends(get_async_session)):
    stmt = select(Cert).where(Cert.worker_name == worker_name).order_by(Cert.id.desc()).limit(100)
    certs = (await db.execute(stmt)).scalars().all()

    result = []
    for cert in certs:
        result.append({
            "id": cert.id,
            "issuer": cert.issuer,
            "common_name": cert.common_name,
            "not_before": cert.not_before.isoformat() if cert.not_before else None,
            "not_after": cert.not_after.isoformat() if cert.not_after else None,
            "serial_number": cert.serial_number,
            "subject_alternative_names": cert.subject_alternative_names,
            "certificate_fingerprint_sha256": cert.certificate_fingerprint_sha256,
            "subject_public_key_hash": cert.subject_public_key_hash,
            "public_key_algorithm": cert.public_key_algorithm,
            "key_size": cert.key_size,
            "signature_algorithm": cert.signature_algorithm,
            "ct_log_timestamp": cert.ct_log_timestamp,
            "crl_urls": cert.crl_urls,
            "ocsp_urls": cert.ocsp_urls,
            "vetting_level": cert.vetting_level,
            "san_count": cert.san_count,
            "issued_on_weekend": cert.issued_on_weekend,
            "issued_at_night": cert.issued_at_night,
            "organization_type": cert.organization_type,
            "is_wildcard": cert.is_wildcard,
            "root_ca_issuer_name": cert.root_ca_issuer_name,
            "is_precertificate": cert.is_precertificate,
            "log_name": cert.log_name,
            "ct_index": cert.ct_index,
            "ct_log_url": cert.ct_log_url,
            "worker_name": cert.worker_name,
            "created_at": cert.created_at.isoformat() if cert.created_at else None,
            "ct_entry": cert.ct_entry
        })

    return {
        "count": len(result),
        "certs": result
    }


# --- Cache Statistics API ---
@app.get("/api/cache/stats")
def get_cache_stats():
    """Get memory cache statistics"""
    return asyncio.run(cert_cache.get_stats())

@app.post("/api/cache/clear")
def clear_cache():
    """Clear memory cache (for debugging)"""
    asyncio.run(cert_cache.clear())
    return {"message": "Cache cleared successfully"}


# --- get_tree_size with 1-minute cache ---
_tree_size_cache = TTLCache(maxsize=100, ttl=60)

@cached(_tree_size_cache)
async def get_tree_size(ct_log_url, db):
    stmt = select(CTLogSTH.tree_size).where(CTLogSTH.ct_log_url == ct_log_url).order_by(CTLogSTH.fetched_at.desc())
    row = (await db.execute(stmt)).first()
    value = row[0] if row and row[0] is not None else 0
    return value
