import random

import requests

from src.worker import logger
from src.worker.worker_common_funcs import sleep_with_stop_check
from src.worker import NeedTreeSizeException


def fetch_ct_log(ct_log_url, start, end, proxies=None, retry_stats=None, stop_event=None):
    # Google CT log API: /ct/v1/get-entries?start={start}&end={end}
    base_url = ct_log_url.rstrip('/')
    url = f"{base_url}/ct/v1/get-entries?start={start}&end={end}"
    try:
        # If proxies is a list, select randomly
        if proxies and isinstance(proxies, list):
            proxy_url = random.choice(proxies)
            use_proxies = {"http": proxy_url, "https": proxy_url}
        else:
            use_proxies = proxies
        resp = requests.get(url, proxies=use_proxies, timeout=10)
        # logger.debug(f"Response body: {resp.text[:200]}")
        if resp.status_code == 200:
            return resp.json().get('entries', [])
        elif resp.status_code == 429:
            retry_after = resp.headers.get('Retry-After')
            logger.debug(f"[CtLogFetch] [WARN] CT log rate limited (429): {retry_after} seconds. url={url}")
            try:
                wait_sec = int(retry_after) if retry_after else 5
                # Update retry stats if provided
                if retry_stats is not None:
                    retry_stats['total_retries'] += 1
                    retry_stats['max_retry_after'] = max(retry_stats['max_retry_after'], wait_sec)
            except Exception:
                wait_sec = 5
            logger.debug(f"[CtLogFetch] CT log rate limited (429): waiting {wait_sec}s. url={url}")
            sleep_with_stop_check(wait_sec, stop_event)
            return []
        elif resp.status_code == 400 and "need tree size" in resp.text.lower():
            logger.debug(f"[CtLogFetch] NeedTreeSizeException: {resp.text} url={url}")
            raise NeedTreeSizeException(resp.text)
        else:
            logger.debug(f"[CtLogFetch] Failed to fetch CT log: {resp.status_code} url={url}")
            sleep_with_stop_check(5, stop_event)
            return []
    except Exception as e:
        logger.debug(f"[CtLogFetch] fetch_ct_log exception: [{type(e).__name__}] {e} url={url} retry_stats={retry_stats.json() if retry_stats else None}")
        if isinstance(e, NeedTreeSizeException):
            raise
        return []
