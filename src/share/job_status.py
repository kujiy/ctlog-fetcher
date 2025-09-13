from enum import Enum

class JobStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    RESUME_WAIT = "resume_wait"
    DEAD = "dead"
    SKIPPED = "skipped"  # when the CT Log has an issue
    FAILED = "failed"  # the workerw gave up when CT LOG API repeated errors

ALL_JOB_STATUS = [
    JobStatus.RUNNING.value,
    JobStatus.COMPLETED.value,
    JobStatus.RESUME_WAIT.value,
    JobStatus.DEAD.value,
    JobStatus.SKIPPED.value,
    JobStatus.FAILED.value,
]