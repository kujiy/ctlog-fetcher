"""
A logger that also outputs to gunicorn
"""
import logging

logger = logging.getLogger("uvicorn")
logger.setLevel(logging.INFO)

# output to standard output for Gunicorn as well
handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)

logger.addHandler(handler)


## Uvicorn
# Ensure uvicorn.access logger also outputs datetime
_uvicorn_access_logger = logging.getLogger("uvicorn.access")
for h in _uvicorn_access_logger.handlers:
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
    #h.setFormatter(logging.Formatter("%(asctime)s [pid=%(process)d] [thread=%(threadName)s] %(levelname)s: %(message)s"))
