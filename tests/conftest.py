# conftest.py
import pytest

@pytest.fixture(autouse=True)
def _reset_db_engines():
    from src.manager_api.db import dispose_engines
    dispose_engines()
    yield
    dispose_engines()

