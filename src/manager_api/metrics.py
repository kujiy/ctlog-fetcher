import os
import random
import time
from typing import Callable

from prometheus_client import Histogram
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from src.share.logger import logger

SAMPLE_RATE = float(os.getenv("SAMPLE_RATE", "0.1"))  # Record only 10%
ALWAYS_RECORD_OVER = float(os.getenv("ALWAYS_RECORD_OVER_SECONDS", "10"))  # Always record if over 10 seconds

EXCLUDE_PATHS = (
    "/metrics",
    "/healthz",
    # "/api/worker/next_task",
    "/api/logs_summary",
    "/api/logs_progress",
    "/api/workers_status",
    "/api/worker_ranking",
    # "/api/worker/categories",
    "/api/unique_certs",
    "/api/fetched_certs",
    "/api/cache/stats",
    "/api/worker_stats",
)
LATENCY_BUCKETS = tuple(  # Coarse buckets to reduce overhead
    float(x) for x in os.getenv("LATENCY_BUCKETS", "2,5,10,20,30,45,60").split(",")
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "Latency of HTTP requests in seconds",
    ["method", "path"],
    buckets=LATENCY_BUCKETS,
)


class LatencySamplingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        raw_path = request.url.path
        if raw_path.startswith(EXCLUDE_PATHS):
            return await call_next(request)

        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            elapsed = time.perf_counter() - start

            # Sampling decision: always record if over threshold, otherwise record by SAMPLE_RATE
            should_record = (elapsed >= ALWAYS_RECORD_OVER) or (random.random() < SAMPLE_RATE)
            if should_record:
                # Create label only when needed (minimally reduces overhead)
                route = request.scope.get("route")
                path_template = getattr(route, "path", raw_path)

                REQUEST_LATENCY.labels(request.method, path_template).observe(elapsed)

            if "response" in locals():
                return response
            # logger.warning(f"Please ignore {raw_path} from the metrics")
            return await call_next(request)
