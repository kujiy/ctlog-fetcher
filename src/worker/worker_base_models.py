from typing import Any

from pydantic import BaseModel


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