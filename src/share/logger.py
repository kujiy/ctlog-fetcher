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

