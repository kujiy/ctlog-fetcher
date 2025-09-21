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


class WorkerArgs(BaseModel):
    proxies: Optional[List[str]] = []
    worker_name: str
    manager: HttpUrl
    debug: bool
    max_threads: int