# FastAPI entry point template
import asyncio
import logging

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from prometheus_client import CollectorRegistry, multiprocess, generate_latest, CONTENT_TYPE_LATEST
from starlette.requests import ClientDisconnect

from src.manager_api.routers.ui_individual_pages import router as ui_individuals_router
from src.manager_api.routers.ui_logs import router as ui_logs_router
# routers
from src.manager_api.routers.ui_status import router as ui_status_router
from src.manager_api.routers.worker_pings import router as worker_pings_router
from src.manager_api.routers.worker_tasks import router as worker_tasks_router
from src.manager_api.routers.worker_upload import router as worker_upload_router
from src.manager_api.routers.worker_upload2 import router as worker_upload2_router
from .background_jobs.log_fetch_progress import start_log_fetch_progress
from .background_jobs.log_fetch_snapshot_job import start_log_fetch_snapshot_job
from .background_jobs.pending_failure_uploader import start_pending_failure_uploader
# background jobs
from .background_jobs.sth_fetcher import start_sth_fetcher
from .background_jobs.worker_liveness import start_worker_liveness_monitor
from .background_jobs.worker_status_aggs import start_worker_status_aggs
from .certificate_cache import cert_cache
from .db import init_engine
from .metrics import LatencySamplingMiddleware
from ..config import BACKGROUND_JOBS_ENABLED
from ..share.logger import logger

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(LatencySamplingMiddleware)
app.include_router(ui_status_router)
app.include_router(ui_individuals_router)
app.include_router(ui_logs_router)
app.include_router(worker_upload_router)
app.include_router(worker_upload2_router)
app.include_router(worker_pings_router)
app.include_router(worker_tasks_router)

@app.get("/metrics")
def metrics() -> Response:
    """
    Output metrics compatible with multiprocess.
    When using `uvicorn --workers N`, always aggregate with MultiProcessCollector.
    """
    registry = CollectorRegistry()
    multiprocess.MultiProcessCollector(registry)
    return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)


@app.middleware("http")
async def store_request_body(request: Request, call_next):
    body = b""
    try:
        async for chunk in request.stream():
            body += chunk
    except ClientDisconnect:
        ## This error occurs when the client disconnects while reading the body. Nothing we can do.
        # Log metadata and partial data received before disconnection for debugging.
        logger.warning(
            f"[ErrorReadingBody:ClientDisconnect] Client disconnected: path={request.url.path}, client={request.client.host}, "
            f"headers={dict(request.headers)}, params={dict(request.query_params)}, total_received={len(body)}"
        )
        # FastAPI cannot send a response because the TCP session is closed, but FastAPI requires a Response to be returned, so return a dummy response.
        return JSONResponse(
            {"detail": "Client disconnected during request processing."}, status_code=400
        )
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


@app.on_event("startup")
async def on_startup():
    # Delayed initialization of DB engine
    init_engine()
    if BACKGROUND_JOBS_ENABLED:
        from filelock import FileLock, Timeout
        import random, time
        lock_file_path = "/tmp/ct_background_jobs.lock"
        lock = FileLock(lock_file_path)
        try:
            # reduce conflicts by random sleep before acquiring the lock
            sleep_sec = random.uniform(0, 3)
            time.sleep(sleep_sec)
            lock.acquire(timeout=0.1)

            app.state.background_tasks = []
            app.state.background_tasks.append(start_sth_fetcher())  # 1️⃣
            app.state.background_tasks.append(start_worker_liveness_monitor())  # 2️⃣
            app.state.background_tasks.append(start_log_fetch_progress())  # 4️⃣
            app.state.background_tasks.append(start_log_fetch_snapshot_job())  # 5️⃣
            app.state.background_tasks.append(start_worker_status_aggs())  # 6️⃣
            app.state.background_tasks.append(start_pending_failure_uploader())  # 7️⃣
            logger.info("✅ Background jobs started and tasks stored in app.state.background_tasks")
            app.state.background_jobs_lock = lock
        except Timeout:
            logger.warning(f"▶️ Background jobs already running in another process (lock file: {lock_file_path})")

@app.on_event("shutdown")
async def on_shutdown():
    tasks = getattr(app.state, "background_tasks", [])
    for t in tasks:
        if t is not None:
            t.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    # Release filelock if held
    lock = getattr(app.state, "background_jobs_lock", None)
    if lock is not None:
        try:
            lock.release()
        except Exception:
            pass
    logger.info("Background jobs cancelled on shutdown")




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
