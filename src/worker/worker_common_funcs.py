import socket
import threading
import time
import urllib.parse
from typing import List
from pydantic import BaseModel
from src.worker import logger


def list_model_to_list_dict(lst: List[BaseModel]) -> List[dict]:
    return [item.dict() for item in lst]


stop_events = {}
def get_stop_event() -> threading.Event:
    return stop_events.get(threading.get_ident())


def sleep_with_stop_check(seconds: int, stop_event: threading.Event = None):
    """
    Sleep for the specified number of seconds, but return immediately if stop_event is set.
    This wrapper ensures immediate termination on Ctrl+C, etc.
    """
    if stop_event is None:
        stop_event = get_stop_event()
    for _ in range(seconds):
        if stop_event and stop_event.is_set():
            break
        time.sleep(1)

# Global management of stop_event for each thread
def register_stop_event(event=None):
    if event is None:
        event = threading.Event()
    stop_events[threading.get_ident()] = event


# --- Startup manager API connectivity check ---
"""
When the API is stopped, prevent the worker from continuing to access the CT Log API unnecessarily.
This switch is triggered when the API's DNS record is deleted.
"""
def wait_for_manager_api_ready(manager_url):
    INTERVAL = 180
    parsed = urllib.parse.urlparse(manager_url)
    while True:
        if is_dns_active(parsed):
            logger.debug(f"[startup-check] Manager API DNS resolution succeeded.")
            break
        else:
            logger.warning(f"[startup-check] The manager API seems unreachable. Retrying in 180s.")
            time.sleep(INTERVAL)


def is_dns_active(parsed):
    """
    Check if DNS is active for the given parsed URL.
    Returns True if DNS resolution succeeds, False otherwise.
    """
    try:
        # DNS resolution
        socket.gethostbyname(parsed.hostname)
        return True
    except Exception:
        return False
