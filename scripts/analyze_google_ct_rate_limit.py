import asyncio
import aiohttp
import argparse
import logging
import time

async def fetch(session, url, logger, idx):
    start_time = time.time()
    try:
        async with session.get(url) as resp:
            status = resp.status
            headers = dict(resp.headers)
            text = await resp.text()
            logger.info(f"[{idx}] GET {url} | Status: {status}")
            if status == 429:
                retry_after = headers.get("Retry-After")
                logger.warning(f"[{idx}] 429 Rate Limited! Retry-After: {retry_after}")
                logger.warning(f"[{idx}] Headers: {headers}")
                logger.warning(f"[{idx}] Body: {text}")
                return (status, retry_after)
            elif status != 200:
                logger.warning(f"[{idx}] Non-200 Status: {status}")
                logger.warning(f"[{idx}] Headers: {headers}")
                logger.warning(f"[{idx}] Body: {text}")
            return (status, None)
    except Exception as e:
        logger.error(f"[{idx}] Exception: {e}")
        return (None, None)
    finally:
        elapsed = time.time() - start_time
        logger.info(f"[{idx}] Finished in {elapsed:.2f}s")

async def main():
    parser = argparse.ArgumentParser(description="Async analyze Google CT log API rate limiting.")
    parser.add_argument("--base_url", type=str, default="https://ct.googleapis.com/logs/xenon2023/ct/v1/get-entries", help="Base URL for CT log API")
    parser.add_argument("--start", type=int, default=0, help="Start index")
    parser.add_argument("--end", type=int, default=31, help="End index (inclusive)")
    parser.add_argument("--increment", type=int, default=32, help="Increment for start/end")
    parser.add_argument("--max_requests", type=int, default=100, help="Maximum number of requests to send")
    parser.add_argument("--concurrency", type=int, default=10, help="Number of concurrent requests")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    logger = logging.getLogger(__name__)

    logger.info(f"Starting async analysis: increment={args.increment}, concurrency={args.concurrency}, max_requests={args.max_requests}")

    start = args.start
    end = args.end
    increment = args.increment
    max_requests = args.max_requests
    concurrency = args.concurrency

    urls = []
    for i in range(max_requests):
        url = f"{args.base_url}?start={start}&end={end}"
        urls.append((url, i+1))
        start += increment
        end += increment

    rate_limit_hits = 0
    retry_after_values = []

    semaphore = asyncio.Semaphore(concurrency)

    async def sem_fetch(session, url, logger, idx):
        async with semaphore:
            status, retry_after = await fetch(session, url, logger, idx)
            if status == 429:
                nonlocal rate_limit_hits
                nonlocal retry_after_values
                rate_limit_hits += 1
                retry_after_values.append(retry_after)
            return status

    async with aiohttp.ClientSession() as session:
        tasks = [sem_fetch(session, url, logger, idx) for url, idx in urls]
        await asyncio.gather(*tasks)

    logger.info("=== Analysis Summary ===")
    logger.info(f"Total requests: {max_requests}")
    logger.info(f"Rate limit (429) hits: {rate_limit_hits}")
    logger.info(f"Retry-After values seen: {retry_after_values}")

if __name__ == "__main__":
    asyncio.run(main())
