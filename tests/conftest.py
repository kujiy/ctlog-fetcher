# conftest.py
import pytest

@pytest.fixture(autouse=True)
def _reset_db_engines():
    from src.manager_api.db import dispose_engines_sync
    dispose_engines_sync()
    yield
    dispose_engines_sync()
