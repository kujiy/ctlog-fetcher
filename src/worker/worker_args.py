import argparse
import hashlib
import os
import socket
import urllib.parse

from src.config import DASHBOARD_URL, MANAGER_API_URL
from src.worker import logger
from src.worker.worker_base_models import WorkerArgs

# By default, the hostname is converted to two Japanese-style words plus a number. If a nickname is specified, it is used as is.
def default_worker_name():
    # By default, convert the hostname to two Japanese-style words plus a number. If a nickname is specified, use it as is.
    hostname = socket.gethostname()
    words = ["pin",   "pon",   "chin",  "kan",   "pafu",  "doki",  "bata",  "kero",  "piyo",  "goro",  "fuwu",  "zun",   "kyu",   "pata",  "ponk", "boon"]
    h = int(hashlib.sha256(hostname.encode()).hexdigest(), 16)
    w1 = words[h % len(words)]
    w2 = words[(h // len(words)) % len(words)]
    num = h % 10000
    return f"{w1}-{w2}-{num:04d}"


def validate_worker_name(worker_name):
    import re
    if worker_name is None or (isinstance(worker_name, str) and worker_name.strip() == ""):
        logger.warning("worker_name is empty or None. Using default_worker_name().")
        return default_worker_name()
    if not isinstance(worker_name, str):
        logger.warning("worker_name is not a string. Using default_worker_name().")
        return default_worker_name()
    if re.search(r"[ \t\n\r\'\";\\\\/]", worker_name):
        logger.warning("worker_name contains forbidden characters (whitespace, quotes, semicolon, slash, backslash, etc.). Using default_worker_name().")
        return default_worker_name()
    return worker_name


command_description = f'''CT Log Fetcher

Project details:
TBD

Worker Ranking
{DASHBOARD_URL}/worker_ranking

Each CT Log API applies rate limits per public IP address.
Adding proxies can speed things up, but it costs money and puts a load on the CT Log API, so please don't overdo it.
PYTHONPATH=. python worker.py --proxy http://<your-proxy-url-1> --proxy http://<your-proxy-url-2> --worker-name <your-nick-name>
'''


def get_args() -> WorkerArgs:
    # Get default values from environment variables
    proxies_env = os.environ.get('PROXIES')
    worker_name_env = os.environ.get('WORKER_NAME')
    manager_url_env = os.environ.get('MANAGER_URL', MANAGER_API_URL)
    debug_env = os.environ.get('DEBUG')
    max_threads_env = os.environ.get('MAX_THREADS', 10)  # Increasing threads increases worker traffic, so be careful

    parser = argparse.ArgumentParser(description=command_description)
    parser.add_argument(
        '--proxies',
        default=None,
        help='Proxy URL (comma-separated for multiple) ENV: PROXIES'
    )
    parser.add_argument(
        '--worker-name',
        default=worker_name_env if worker_name_env else default_worker_name(),
        help='Worker name (default: Japanese-style nickname. You can specify your own) ENV: WORKER_NAME'
    )
    parser.add_argument(
        '--manager',
        default=manager_url_env,
        help='Manager API base url ENV: MANAGER_URL'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        default=(str(debug_env).lower() in ['1', 'true', 'yes']),
        help='Enable debug logging ENV: DEBUG (1/true/yes)'
    )
    parser.add_argument(
        '--max-threads',
        type=int,
        default=int(max_threads_env),
        help='Maximum number of ThreadPoolExecutor workers (default: 10) ENV: MAX_THREADS'
    )
    args = parser.parse_args()
    args.worker_name = urllib.parse.quote(args.worker_name.strip())

    # If --proxies is not specified, split PROXIES env var by comma into a list
    if args.proxies is not None and isinstance(args.proxies, str):
        args.proxies = [p.strip() for p in args.proxies.split(',') if p.strip()]
    elif proxies_env:
        args.proxies = [p.strip() for p in proxies_env.split(',') if p.strip()]
    else:
        args.proxies = None


    # worker_name validation
    args.worker_name = validate_worker_name(args.worker_name)

    return WorkerArgs(
        proxies=args.proxies,
        worker_name=args.worker_name,
        manager=args.manager,
        debug=args.debug,
        max_threads=args.max_threads
    )
