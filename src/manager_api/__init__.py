import asyncio
from collections import defaultdict

"""
When `locks = defaultdict(asyncio.Lock)` is declared, accessing an unregistered key with `locks[lock_key]` will automatically generate an instance of `asyncio.Lock()` and associate it with that key.
This is due to the behavior of `collections.defaultdict`, where the function passed to the constructor (in this case, `asyncio.Lock`) is used as the "default factory.
"""
# 4-tuple key: (worker_name, log_name, start, end)
locks = defaultdict(asyncio.Lock)