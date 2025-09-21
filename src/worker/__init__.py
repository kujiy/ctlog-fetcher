import logging
from collections import Counter

# --- Settings ---
MAX_CONSOLE_LINES = 8
DEFAULT_CATEGORIES = Counter(["google", "google", "google", "cloudflare", "letsencrypt", "digicert", "trustasia"])
ordered_categories = []

logger = logging.getLogger("ct_worker")

PENDING_FILE_DIR = "pending"
FAILED_FILE_DIR = "tests/resources/failed"

class NeedTreeSizeException(Exception):
    pass