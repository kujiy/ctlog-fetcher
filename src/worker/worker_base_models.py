import hashlib
import urllib
from typing import Any, List, Optional

from pydantic import BaseModel, validator, Field, HttpUrl


class CertCompareModel(BaseModel):
    ct_entry: str
    ct_log_url: str
    log_name: str
    worker_name: str
    ct_index: int
    issuer: str
    serial_number: str
    certificate_fingerprint_sha256: str
    common_name: str

class PendingRequest(BaseModel):
    url: str
    method: str
    data: Any

class CompletedJob(BaseModel):
    worker_name: str
    log_name: str
    ct_log_url: str
    start: int
    end: int
    current: int
    worker_total_count: int = 0
    last_uploaded_index: int = 0
    status: str
    jp_count: int = 0
    jp_ratio: float = 0
    max_retry_after: int = 0
    total_retries: int = 0



class WorkerArgs(BaseModel):
    proxies: Optional[List[str]] = []
    worker_name: str
    manager: HttpUrl
    debug: bool
    max_threads: int