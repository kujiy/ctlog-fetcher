"""
gunicornにも出るlogger
"""
import logging

logger = logging.getLogger("uvicorn")
logger.setLevel(logging.INFO)

# Gunicorn でも標準出力に出すように
handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)

logger.addHandler(handler)

