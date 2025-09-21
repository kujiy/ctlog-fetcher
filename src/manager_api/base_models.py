from pydantic import BaseModel, Field, validator
from typing import List, Optional
from src.share.job_status import JobStatus

 # --- Pydantic models for endpoints ---

# Base model with default values
class WorkerPingBaseModel(BaseModel):
    """
    The worker adds the number of failed_files and pending_files as query parameters.
    These query parameters are not processed at all by the API server. They are only for access log purposes.
    """
    worker_name: str = Field("default", min_length=1, max_length=64)
    log_name: str = Field(..., min_length=1, max_length=64)
    ct_log_url: str = Field(..., min_length=5, max_length=256)
    start: int
    end: int
    current: int = 0
    last_uploaded_index: int | None = None
    status: JobStatus = Field(...)
    jp_count: int = 0
    jp_ratio: float = 0.0
    ip_address: str | None = Field(None, max_length=64)
    total_retries: int | None = None
    max_retry_after: int | None = None

    @validator("worker_name", pre=True, always=True)
    def validate_worker_name(cls, v):
        import re
        if v is None or (isinstance(v, str) and v.strip() == ""):
            return "default"
        if not isinstance(v, str):
            raise ValueError("worker_name must be a string")
        # Forbidden: whitespace, quotes, semicolon, backslash, slash, newline, tab
        if re.search(r"[ \t\n\r\'\";\\\\/]", v):
            raise ValueError("worker_name contains forbidden characters (whitespace, quotes, semicolon, slash, backslash, etc.)")
        return v


class WorkerPingModel(WorkerPingBaseModel):
    status: JobStatus = Field(...)


class WorkerResumeRequestModel(BaseModel):
    worker_name: str = Field("default", min_length=1, max_length=64)
    log_name: str = Field(..., min_length=1, max_length=64)
    ct_log_url: str = Field(..., min_length=5, max_length=256)
    start: int
    end: int
    ip_address: str | None = Field(None, max_length=64)

    @validator("worker_name", pre=True, always=True)
    def validate_worker_name(cls, v):
        import re
        if not v:
            return "default"
        if v is None or (isinstance(v, str) and v.strip() == ""):
            return "default"
        if not isinstance(v, str):
            raise ValueError("worker_name must be a string")
        if re.search(r"[ \t\n\r\'\";\\\\/]", v):
            raise ValueError("worker_name contains forbidden characters (whitespace, quotes, semicolon, slash, backslash, etc.)")
        return v

class UploadCertItem(BaseModel):
    ct_entry: str = Field(..., min_length=10, max_length=1000000, description="CT log entry as JSON string")
    ct_log_url: str = Field(..., min_length=5, max_length=256)
    log_name: str = Field(..., min_length=1, max_length=64)
    worker_name: str = Field("default", min_length=1, max_length=64)
    ct_index: Optional[int]
    ip_address: Optional[str] = Field(None, max_length=64)

    @validator('ct_entry')
    def validate_json(cls, v):
        import json
        try:
            json.loads(v)
        except Exception:
            raise ValueError('ct_entry must be valid JSON string')
        return v

    @validator("worker_name", pre=True, always=True)
    def validate_worker_name(cls, v):
        import re
        if v is None or (isinstance(v, str) and v.strip() == ""):
            return "default"
        if not isinstance(v, str):
            raise ValueError("worker_name must be a string")
        if re.search(r"[ \t\n\r\'\";\\\\/]", v):
            raise ValueError("worker_name contains forbidden characters (whitespace, quotes, semicolon, slash, backslash, etc.)")
        return v

class WorkerErrorModel(BaseModel):
    worker_name: str = Field("default", min_length=1, max_length=64)
    log_name: str = Field(..., min_length=1, max_length=64)
    ct_log_url: str = Field(..., min_length=5, max_length=256)
    ct_index: int | None = None
    error_type: str = Field(..., min_length=1, max_length=64, description="Type of error, e.g. 'parse_error', 'upload_error', etc.")
    error_message: str = Field(..., min_length=1, max_length=2048)
    traceback: str = Field(...)
    entry: str = Field(..., description="CT log entry as JSON string")

    @validator("worker_name", pre=True, always=True)
    def validate_worker_name(cls, v):
        import re
        if not v:
            return "default"
        if v is None or (isinstance(v, str) and v.strip() == ""):
            return "default"
        if not isinstance(v, str):
            raise ValueError("worker_name must be a string")
        if re.search(r"[ \t\n\r\'\";\\\\/]", v):
            raise ValueError("worker_name contains forbidden characters (whitespace, quotes, semicolon, slash, backslash, etc.)")
        return v


class NextTask(BaseModel):
    log_name: str = Field(..., min_length=1, max_length=64)
    ct_log_url: str = Field(..., min_length=5, max_length=256)
    start: int = 0
    end: int = 0
    sth_end: int = 0
    ip_address: Optional[str] = Field(None, max_length=64)
    ctlog_request_interval_sec: int = Field(..., gt=0)  # 1 sec to 1 hour

class WorkerNextTask(NextTask):
    manager: str
    worker_name: str
    status: JobStatus
    current: int = 0

class NextTaskCompleted(BaseModel):
    message: str
    sleep_sec: int = 1

class Categories(BaseModel):
    all_categories: List[str]
    ordered_categories: List[str]

class PingResponse(BaseModel):
    """
     {
        "ping_interval_sec": WORKER_PING_INTERVAL_SEC,
        "ctlog_request_interval_sec": await get_ctlog_request_interval_sec(db, data.log_name, extract_ip_address_hash(request)),
        "overdue_threshold_sec": 60 * 60,  # worker time limit: 60 minutes
        "overdue_task_sleep_sec": 60 * 30,  # 30 minutes
        "kill_me_now_then_sleep_sec": 0,# >0 means the worker should exit right now, then sleep this seconds before exit
    }
    """
    ping_interval_sec: int
    ctlog_request_interval_sec: int
    overdue_threshold_sec: int
    overdue_task_sleep_sec: int
    kill_me_now_then_sleep_sec: int


class SimpleResponse(BaseModel):
    message: str

class FailedResponse(BaseModel):
    failed_sleep_sec: int = 120


class UploadResponse(BaseModel):
    inserted: int
    skipped_duplicates: int