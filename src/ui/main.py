# ui FastAPI entry point template
import time
from logging import getLogger

from asyncache import cached
from cachetools import TTLCache
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import os
from typing import Any
import asyncio
import httpx
from datetime import datetime, timedelta, timezone
import traceback
from src.ui.background_jobs.snapshot_job import background_snapshot_job, load_snapshot
from src.config import CT_LOG_ENDPOINTS, MANAGER_API_URL_FOR_UI, METRICS_URL



app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
logger = app.logger = getLogger("uvicorn")
# Setup template directory
TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=TEMPLATE_DIR)

JST = timezone(timedelta(hours=9))
logger.warning(f"MANAGER_API_URL: {MANAGER_API_URL_FOR_UI}")



@app.on_event("startup")
async def start_snapshot_job():
    asyncio.create_task(background_snapshot_job())


# Static files (CSS, etc.)
static_dir = os.path.join(os.path.dirname(__file__), 'static')
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Publish assets such as favicon
assets_dir = os.path.join(os.path.dirname(__file__), 'assets')
if os.path.exists(assets_dir):
    app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")



dashboard_cache: dict[str, dict[str, Any]] = {}

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    cache_key = "dashboard"
    now = datetime.now()
    cache = dashboard_cache.get(cache_key)
    if cache and (now - cache["timestamp"]).total_seconds() < 60:
        # Return cache if within n seconds
        cached_context = cache["context"]
        cached_context["request"] = request
        return templates.TemplateResponse("dashboard.html", cached_context)


    # Get data from APIs
    log_progress_list, logs_summary, worker_ranking, workers, round_trip_time, summary = await get_dashboard_apis()

    # Convert last_ping to datetime (used in template)
    await _dashboard_convert_ping_to_datetime(workers)

    # Display running workers at the top
    workers_sorted = sorted(
        workers,
        key=lambda w: (
            w.get("status") != "running",
            w.get("log_name") or "",
            w.get("worker_name") or ""
        )
    )

    # --- Worker Ranking Diff Logic ---
    context = await _dashboard_worker_ranking_diff([], log_progress_list, logs_summary, request, round_trip_time, summary,
                                                   worker_ranking, workers_sorted)
    if worker_ranking:
        # Update cache
        dashboard_cache[cache_key] = {
            "timestamp": now,
            "context": {**context, "request": None}  # Do not cache request
        }
    return templates.TemplateResponse("dashboard.html", context)


async def _dashboard_worker_ranking_diff(logs, log_progress_list, logs_summary, request, round_trip_time, summary,
                                         worker_ranking, workers_sorted):
    ranking_diff, snapshot_time = await get_snapshot_diff(worker_ranking)
    context = {
        "request": request,
        "summary": summary,
        "logs": logs,
        "log_progress_list": log_progress_list,
        "workers": workers_sorted,
        "round_trip_time": round_trip_time,
        "worker_ranking": worker_ranking,
        "logs_summary": logs_summary,
        "ranking_diff": ranking_diff,
        "snapshot_time": snapshot_time
    }
    return context


async def get_snapshot_diff(worker_ranking):
    snapshot = load_snapshot()
    ranking_diff = {}
    if worker_ranking and snapshot:
        # Build {worker_name: rank, count, jp_count} for snapshot and current
        snap_map = {r["worker_name"]: {"rank": i + 1, "worker_total_count": r["worker_total_count"],
                                       "jp_count": r.get("jp_count", 0)}
                    for i, r in enumerate(snapshot.get("worker_total_count_ranking", []))}
        curr_map = {r["worker_name"]: {"rank": i + 1, "worker_total_count": r["worker_total_count"],
                                       "jp_count": r.get("jp_count", 0)}
                    for i, r in enumerate(worker_ranking.get("worker_total_count_ranking", []))}
        for name, curr in curr_map.items():
            prev = snap_map.get(name)
            if prev:
                rank_diff = prev["rank"] - curr["rank"]
                count_diff = curr["worker_total_count"] - prev["worker_total_count"]
                jp_diff = curr["jp_count"] - prev["jp_count"]
                ranking_diff[name] = {
                    "rank_diff": rank_diff,
                    "count_diff": count_diff,
                    "jp_diff": jp_diff
                }
            else:
                ranking_diff[name] = {
                    "rank_diff": 0,
                    "count_diff": 0,
                    "jp_diff": 0
                }
    snapshot_time = None
    if snapshot and "timestamp" in snapshot:
        snapshot_time = datetime.fromisoformat(snapshot["timestamp"])
    return ranking_diff, snapshot_time


async def _dashboard_convert_ping_to_datetime(workers):
    for w in workers:
        if isinstance(w.get("last_ping"), str):
            try:
                w["last_ping"] = datetime.fromisoformat(w["last_ping"])
            except Exception:
                w["last_ping"] = w["last_ping"]



@cached(TTLCache(maxsize=1, ttl=120))
async def get_dashboard_apis():
    round_trip_time = []
    summary = {"total": 0, "workers": 0}
    log_progress_list = []
    workers = []
    worker_ranking = None
    logs_summary = None
    async with httpx.AsyncClient(timeout=15.0) as client:
        log_progress_list = await _dashboard_logs_progress(client, log_progress_list, round_trip_time, summary)

        # workers_status
        workers = await _dashboard_workers_status(client, round_trip_time, summary, workers)

        # worker_ranking
        worker_ranking = await _dashboard_worker_ranking(client, round_trip_time, summary, worker_ranking)

        # logs_summary
        logs_summary = await _dashboard_logs_summary(client, logs_summary, round_trip_time, summary)
    return log_progress_list, logs_summary, worker_ranking, workers, round_trip_time, summary


async def _dashboard_logs_summary(client, logs_summary, round_trip_time, summary):
    try:
        start_time = time.perf_counter()
        summary_resp = await client.get(f"{MANAGER_API_URL_FOR_UI}/api/logs_summary")
        round_trip_time.append({"api_name": "logs_summary", "rtt": time.perf_counter() - start_time})
        if summary_resp.status_code == 200:
            logs_summary = summary_resp.json()
    except Exception as e:
        round_trip_time.append({"api_name": "logs_summary", "rtt": None, "error": str(e)})
        summary["logs_summary_error"] = str(e)
    return logs_summary


async def _dashboard_worker_ranking(client, round_trip_time, summary, worker_ranking):
    try:
        start_time = time.perf_counter()
        ranking_resp = await client.get(f"{MANAGER_API_URL_FOR_UI}/api/worker_ranking")
        round_trip_time.append({"api_name": "worker_ranking", "rtt": time.perf_counter() - start_time})
        if ranking_resp.status_code == 200:
            worker_ranking = ranking_resp.json()
            summary['cumulative_worker_names'] = len(worker_ranking['worker_total_count_ranking'])
    except Exception as e:
        round_trip_time.append({"api_name": "worker_ranking", "rtt": None, "error": str(e)})
        summary["worker_ranking_error"] = str(e)
    return worker_ranking


async def _dashboard_workers_status(client, round_trip_time, summary, workers):
    try:
        start_time = time.perf_counter()
        workers_resp = await client.get(f"{MANAGER_API_URL_FOR_UI}/api/workers_status")
        round_trip_time.append({"api_name": "workers_status", "rtt": time.perf_counter() - start_time})
        if workers_resp.status_code == 200:
            workers_data = workers_resp.json()
            workers = workers_data.get("workers", [])
            summary.update(workers_data.get("summary", {}))
            summary["workers"] = sum(1 for w in workers if w.get("status") == "running")
    except Exception as e:
        round_trip_time.append({"api_name": "workers_status", "rtt": None, "error": str(e)})
        summary["workers_status_error"] = str(e)
    return workers


async def _dashboard_logs_progress(client, log_progress_list, round_trip_time, summary):
    # logs_progress
    try:
        start_time = time.perf_counter()
        logs_resp = await client.get(f"{MANAGER_API_URL_FOR_UI}/api/logs_progress")
        round_trip_time.append({"api_name": "logs_progress", "rtt": time.perf_counter() - start_time})
        if logs_resp.status_code == 200:
            log_progress_list = logs_resp.json()
            summary["total"] = sum([log["min_completed_end"] for log in log_progress_list])
    except Exception as e:
        round_trip_time.append({"api_name": "logs_progress", "rtt": None, "error": str(e)})
        summary["logs_progress_error"] = str(e) # + str(traceback.format_exc())
    return log_progress_list


@app.get("/unique_certs", response_class=HTMLResponse)
async def unique_certs_page(request: Request):
    unique_certs_data, error_message = await _unique_certs_with_cache()
    return templates.TemplateResponse("unique_certs.html", {
        "request": request,
        "unique_certs_data": unique_certs_data,
        "error_message": error_message
    })


@cached(TTLCache(maxsize=1, ttl=300))
async def _unique_certs_with_cache():
    """
    Fetches unique certificate data from the manager API with caching.
    Returns a rendered template with the data or error message.
    """
    unique_certs_data = None
    error_message = None
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{MANAGER_API_URL_FOR_UI}/api/unique_certs")
            if response.status_code == 200:
                unique_certs_data = response.json()
            else:
                error_message = f"API returned status code: {response.status_code}"
    except Exception as e:
        error_message = str(e)
        logger.error(f"_unique_certs_with_cache error: {e}")
    return unique_certs_data, error_message


@app.get("/fetched-certs/{worker_name}", response_class=HTMLResponse)
async def fetched_certs_page(request: Request, worker_name: str):
    error_message, fetched_certs_data = await _fetched_certs_by_worker_name(worker_name)
    return templates.TemplateResponse("fetched_certs.html", {
        "request": request,
        "worker_name": worker_name,
        "fetched_certs_data": fetched_certs_data,
        "error_message": error_message
    })


@cached(TTLCache(maxsize=128, ttl=300))
async def _fetched_certs_by_worker_name(worker_name):
    """
    Fetches fetched certificate data for a given worker from the manager API with caching.
    Returns a rendered template with the data or error message.
    """
    fetched_certs_data = None
    error_message = None
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{MANAGER_API_URL_FOR_UI}/api/fetched_certs/{worker_name}")
            if response.status_code == 200:
                fetched_certs_data = response.json()
            else:
                error_message = f"API returned status code: {response.status_code}"
    except Exception as e:
        error_message = str(e)
        logger.error(f"_fetched_certs_with_cache error: {e}")
    return error_message, fetched_certs_data


@app.get("/worker-stats/{worker_name}", response_class=HTMLResponse)
async def worker_stats_page(request: Request, worker_name: str):
    stats_data, error_message = await get_worker_stats(worker_name)
    return templates.TemplateResponse("worker_stats.html", {
        "request": request,
        "worker_name": worker_name,
        "log_stats": stats_data["log_stats"] if stats_data else [],
        "status_stats": stats_data["status_stats"] if stats_data else [],
        "error_message": error_message
    })


@cached(TTLCache(maxsize=128, ttl=300))
async def get_worker_stats(worker_name):
    stats_data = None
    error_message = None
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{MANAGER_API_URL_FOR_UI}/api/worker_stats/{worker_name}")
            if response.status_code == 200:
                stats_data = response.json()
            else:
                error_message = f"API returned status code: {response.status_code}"
    except Exception as e:
        error_message = str(e)
    return stats_data, error_message

from src.ui.metrics_utils import parse_metrics_text

@app.get("/metrics", response_class=HTMLResponse)
async def metrics_page(request: Request):
    """
    Fetches and parses Prometheus metrics, displays as table.
    """
    metrics = []
    error_message = None
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{METRICS_URL}/metrics")
            if resp.status_code == 200:
                text = resp.text
                metrics = parse_metrics_text(text)
            else:
                error_message = f"API returned status code: {resp.status_code}"
    except Exception as e:
        error_message = str(e)
    return templates.TemplateResponse("metrics.html", {
        "request": request,
        "metrics": metrics,
        "error_message": error_message
    })

# API example: Get collection status
@app.get("/api/ui/status")
def get_status():
    # TODO: Call manager_api's API and return aggregated data
    return {"message": "not implemented"}
