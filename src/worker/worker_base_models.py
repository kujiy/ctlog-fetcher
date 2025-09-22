import threading
from typing import Dict, Tuple, Any
from typing import List, Optional

from pydantic import BaseModel, Field
from src.manager_api.base_models import UploadCertItem


class CertCompareModel(UploadCertItem):
    # Additional fields for internal duplicate checking (extends UploadCertItem)
    issuer: str
    serial_number: str
    certificate_fingerprint_sha256: str
    common_name: str = None

class PendingRequest(BaseModel):
    url: str
    method: str
    data: Any


class WorkerArgs(BaseModel):
    proxies: Optional[List[str]] = []
    worker_name: str
    manager: str
    debug: bool
    max_threads: int


class ThreadInfo(BaseModel):
    thread: Any = Field(..., description="The future object representing the running thread.")
    stop_event: threading.Event = Field(..., description="An event to signal the thread to stop.")

    class Config:
        arbitrary_types_allowed = True


class CategoryThreadInfo(BaseModel):
    data: Dict[Tuple[str, int], ThreadInfo] = Field(...,
                                                    description="A dictionary mapping a (category, index) tuple to a ThreadInfo object.")

