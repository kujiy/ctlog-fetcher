import pytest
from datetime import datetime
from src.manager_api.background_jobs.sth_fetcher import fetch_sth_no_retry
from src.config import CT_LOG_ENDPOINTS

# Test only for 2025h1 and later
letsencrypt_targets = [
    (log_name, ct_log_url)
    for log_name, ct_log_url in CT_LOG_ENDPOINTS["letsencrypt"]
    if log_name >= "2025h1"
]

import pytest

@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize("log_name,ct_log_url", letsencrypt_targets)
async def test_fetch_sth_no_retry_letsencrypt(log_name, ct_log_url):
    now = datetime.utcnow()
    tree_size, sth_dt = await fetch_sth_no_retry(log_name, ct_log_url, now)
    assert tree_size is not None and tree_size > 0, f"tree_size should be positive for {log_name}"
    assert sth_dt is not None, f"sth_dt should not be None for {log_name}"
