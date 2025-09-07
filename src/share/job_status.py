from enum import Enum

class JobStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    RESUME_WAIT = "resume_wait"
    DEAD = "dead"
    SKIPPED = "skipped"  # when the CT Log has an issue