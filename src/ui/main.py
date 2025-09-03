# ui FastAPI entry point template
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

from src.ui.snapshot_utils import load_snapshot, save_snapshot

from src.config import CT_LOG_ENDPOINTS, MANAGER_API_URL_FOR_UI

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
logger = app.logger = getLogger("uvicorn")
# Setup template directory
TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=TEMPLATE_DIR)

@app.on_event("startup")
async def start_snapshot_job():
    async def snapshot_job():
        while True:
            try:
                # Wait until 9:30 JST
                JST = timezone(timedelta(hours=9))
                now = datetime.now(JST)
                target = now.replace(hour=9, minute=30, second=0, microsecond=0)
                if now >= target:
                    # If already past 9:30 today, schedule for tomorrow
                    target = target + timedelta(days=1)
                wait_sec = (target - now).total_seconds()
                await asyncio.sleep(wait_sec)
                # After waiting, update snapshot
                async with httpx.AsyncClient(timeout=60.0) as client:
                    resp = await client.get(f"{MANAGER_API_URL_FOR_UI}/api/worker_ranking")
                    if resp.status_code == 200:
                        save_snapshot(resp.json())
                        logger.info("snapshot.json updated at 9:30 JST")
            except Exception as e:
                logger.error(f"Snapshot job error: {e}")
            # Sleep 1 hour as fallback
            await asyncio.sleep(3600)

    # On startup: create snapshot.json if not exists
    snapshot_path = os.path.join(os.path.dirname(__file__), "snapshot.json")
    if not os.path.exists(snapshot_path):
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{MANAGER_API_URL_FOR_UI}/api/worker_ranking")
                if resp.status_code == 200:
                    save_snapshot(resp.json())
                    logger.info("snapshot.json created on startup")
        except Exception as e:
            logger.error(f"Initial snapshot creation failed: {e}")

    # Start background job
    asyncio.create_task(snapshot_job())

logger.warning(f"MANAGER_API_URL: {MANAGER_API_URL_FOR_UI}")

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
    import time
    cache_key = "dashboard"
    now = datetime.now()
    cache = dashboard_cache.get(cache_key)
    if cache and (now - cache["timestamp"]).total_seconds() < 60:
        # Return cache if within n seconds
        cached_context = cache["context"]
        cached_context["request"] = request
        return templates.TemplateResponse("dashboard.html", cached_context)


    logs = []
    workers = []
    round_trip_time = []
    summary = {"total": 0, "workers": 0}
    worker_ranking = None
    logs_summary = None

    # Get data from APIs
    async with httpx.AsyncClient(timeout=5.0) as client:
        # logs_progress
        try:
            start_time = time.perf_counter()
            logs_resp = await client.get(f"{MANAGER_API_URL_FOR_UI}/api/logs_progress")
            round_trip_time.append({"api_name": "logs_progress", "rtt": time.perf_counter() - start_time})
            if logs_resp.status_code == 200:
                logs_data = logs_resp.json()
                logs = logs_data.get("logs", [])
                summary["total"] = logs_data.get("summary", {}).get("total", 0)
        except Exception as e:
            round_trip_time.append({"api_name": "logs_progress", "rtt": None, "error": str(e)})
            summary["logs_progress_error"] = str(e)

        # workers_status
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

        # worker_ranking
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

        # logs_summary
        try:
            start_time = time.perf_counter()
            summary_resp = await client.get(f"{MANAGER_API_URL_FOR_UI}/api/logs_summary")
            round_trip_time.append({"api_name": "logs_summary", "rtt": time.perf_counter() - start_time})
            if summary_resp.status_code == 200:
                logs_summary = summary_resp.json()
        except Exception as e:
            round_trip_time.append({"api_name": "logs_summary", "rtt": None, "error": str(e)})
            summary["logs_summary_error"] = str(e)

    # Split by category
    categories = list(CT_LOG_ENDPOINTS.keys())
    logs_by_cat = {cat: [] for cat in categories}
    # Categorize by ct_log_url domain
    for log in logs:
        url = log.get("ct_log_url", "").lower()
        if "cloudflare.com" in url:
            logs_by_cat["cloudflare"].append(log)
        elif "googleapis.com" in url:
            logs_by_cat["google"].append(log)
        elif "trustasia.com" in url:
            logs_by_cat["trustasia"].append(log)
        elif "digicert.com" in url:
            logs_by_cat["digicert"].append(log)
        elif "letsencrypt.org" in url:
            logs_by_cat["letsencrypt"].append(log)
        else:
            logs_by_cat["other"].append(log)

    # Convert last_ping to datetime (used in template)
    for w in workers:
        if isinstance(w.get("last_ping"), str):
            try:
                w["last_ping"] = datetime.fromisoformat(w["last_ping"])
            except Exception:
                w["last_ping"] = w["last_ping"]

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
    snapshot = load_snapshot()
    ranking_diff = {}
    if worker_ranking and snapshot:
        # Build {worker_name: rank, count, jp_count} for snapshot and current
        snap_map = {r["worker_name"]: {"rank": i+1, "worker_total_count": r["worker_total_count"], "jp_count": r.get("jp_count", 0)}
                    for i, r in enumerate(snapshot.get("worker_total_count_ranking", []))}
        curr_map = {r["worker_name"]: {"rank": i+1, "worker_total_count": r["worker_total_count"], "jp_count": r.get("jp_count", 0)}
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
    context = {
        "request": request,
        "summary": summary,
        "logs": logs,
        "logs_by_cat": logs_by_cat,
        "workers": workers_sorted,
        "round_trip_time": round_trip_time,
        "worker_ranking": worker_ranking,
        "logs_summary": logs_summary,
        "ranking_diff": ranking_diff,
        "snapshot_time": snapshot_time
    }
    if worker_ranking:
        # Update cache
        dashboard_cache[cache_key] = {
            "timestamp": now,
            "context": {**context, "request": None}  # Do not cache request
        }
    return templates.TemplateResponse("dashboard.html", context)

@app.get("/unique_certs", response_class=HTMLResponse)
async def unique_certs_page(request: Request):

    unique_certs_data = None
    error_message = None

    # Get data from unique_certs API
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{MANAGER_API_URL_FOR_UI}/api/unique_certs")
            if response.status_code == 200:
                unique_certs_data = response.json()
            else:
                error_message = f"API returned status code: {response.status_code}"
    except Exception as e:
        error_message = str(e)

    return templates.TemplateResponse("unique_certs.html", {
        "request": request,
        "unique_certs_data": unique_certs_data,
        "error_message": error_message
    })

@app.get("/fetched-certs/{worker_name}", response_class=HTMLResponse)
async def fetched_certs_page(request: Request, worker_name: str):

    fetched_certs_data = None
    error_message = None

    # Get data from fetched_certs API
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{MANAGER_API_URL_FOR_UI}/api/fetched_certs/{worker_name}")
            if response.status_code == 200:
                fetched_certs_data = response.json()
            else:
                error_message = f"API returned status code: {response.status_code}"
    except Exception as e:
        error_message = str(e)

    return templates.TemplateResponse("fetched_certs.html", {
        "request": request,
        "worker_name": worker_name,
        "fetched_certs_data": fetched_certs_data,
        "error_message": error_message
    })

@app.get("/worker-stats/{worker_name}", response_class=HTMLResponse)
async def worker_stats_page(request: Request, worker_name: str):
    return await _worker_stats_page_with_cache(request, worker_name)


_worker_stats_cache = TTLCache(maxsize=128, ttl=300)
@cached(_worker_stats_cache)
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

async def _worker_stats_page_with_cache(request, worker_name):
    stats_data, error_message = await get_worker_stats(worker_name)
    return templates.TemplateResponse("worker_stats.html", {
        "request": request,
        "worker_name": worker_name,
        "log_stats": stats_data["log_stats"] if stats_data else [],
        "status_stats": stats_data["status_stats"] if stats_data else [],
        "error_message": error_message
    })


# API example: Get collection status
@app.get("/api/ui/status")
def get_status():
    # TODO: Call manager_api's API and return aggregated data
    return {"message": "not implemented"}
