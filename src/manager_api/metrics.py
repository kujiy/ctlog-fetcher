import os
import random
import time
from typing import Callable

from prometheus_client import Histogram
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


SAMPLE_RATE = float(os.getenv("SAMPLE_RATE", "0.1"))  # 10%だけ記録
ALWAYS_RECORD_OVER = float(os.getenv("ALWAYS_RECORD_OVER_SECONDS", "10"))  # 10秒以上は必ず記録

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
LATENCY_BUCKETS = tuple(  # 粗めのバケットでオーバーヘッド低減
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

            # サンプリング判定：閾値超は必ず記録、その他はSAMPLE_RATEで記録
            should_record = (elapsed >= ALWAYS_RECORD_OVER) or (random.random() < SAMPLE_RATE)
            if should_record:
                # ラベル作成は必要になったときだけ（微小だけどオーバーヘッド削減）
                route = request.scope.get("route")
                path_template = getattr(route, "path", raw_path)

                REQUEST_LATENCY.labels(request.method, path_template).observe(elapsed)

            return response