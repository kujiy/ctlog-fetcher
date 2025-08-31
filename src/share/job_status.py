from enum import Enum

class JobStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    RESUME_WAIT = "resume_wait"
    DEAD = "dead"
