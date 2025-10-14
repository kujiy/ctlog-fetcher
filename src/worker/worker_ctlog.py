import random

import httpx

from src.worker import logger
from src.worker.worker_common_funcs import sleep_with_stop_check
from src.worker import NeedTreeSizeException


def fetch_ct_log(ct_log_url, start, end, client=None, proxies=None, retry_stats=None, stop_event=None):
    # Google CT log API: /ct/v1/get-entries?start={start}&end={end}
    base_url = ct_log_url.rstrip('/')
    url = f"{base_url}/ct/v1/get-entries?start={start}&end={end}"
    
    # Create a temporary client if none provided (fallback for backwards compatibility)
    use_temp_client = False
    if client is None:
        # If proxies is a list, select randomly
        if proxies and isinstance(proxies, list):
            proxy_url = random.choice(proxies)
            use_proxies = proxy_url
        else:
            use_proxies = proxies
        
        # httpx uses different proxy format than requests
        client_kwargs = {
            'http2': True,  # Force HTTP/2
            'timeout': 10.0
        }
        if use_proxies:
            client_kwargs['proxies'] = use_proxies
        
        client = httpx.Client(**client_kwargs)
        use_temp_client = True
    
    try:
        resp = client.get(url)
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
        logger.debug(f"[CtLogFetch] fetch_ct_log exception: [{type(e).__name__}] {e} url={url} retry_stats={retry_stats if retry_stats else None}")
        if isinstance(e, NeedTreeSizeException):
            raise
        return []
    finally:
        # Close temporary client if we created it
        if use_temp_client and client:
            client.close()
