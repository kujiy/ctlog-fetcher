import pytest
import httpx
from httpx import ASGITransport
from src.manager_api.main import app
import json
import os
import asyncio
from src.share.job_status import JobStatus


@pytest.mark.asyncio
async def test_worker_resume_request(monkeypatch):
    # Patch DB logic in endpoint
    monkeypatch.setattr("src.manager_api.locks", asyncio.Lock())

    # Mock get_async_session
    class _DummyResult:
        def scalars(self):
            class _S:
                def first(self):  # SELECT ... .scalars().first()
                    return None
            return _S()
        def all(self):  # SELECT ... .all()
            return []
        def scalar_one_or_none(self):
            return None

    class _DummySession:
        async def execute(self, *a, **k):  # Corresponds to any SELECT
            return _DummyResult()
        async def commit(self): pass
        async def rollback(self): pass
        async def close(self): pass

    async def fake_get_async_session():
        yield _DummySession()

    monkeypatch.setattr("src.manager_api.db.get_async_session", fake_get_async_session)

    payload = {
        "worker_name": "dummy_worker",
        "log_name": "dummy_log",
        "ct_log_url": "dummy_url",
        "start": 0,
        "end": 10,
        "ip_address": "127.0.0.1"
    }
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/api/worker/resume_request", json=payload)
    print("RESUME RESPONSE:", response.status_code, response.text)
    assert response.status_code == 200
    assert response.json()["message"] == "ok"



@pytest.mark.asyncio
async def test_worker_upload(monkeypatch):
    # Use the actual CT entry as dict from the resource file
    resource_path = os.path.join(os.path.dirname(__file__), "resources/ov/www.toyo-integration.co.jp.json")
    with open(resource_path, "r") as f:
        ct_entry_dict = json.load(f)
    payload = [{
        "log_name": "dummy_log",
        "worker_name": "dummy_worker",
        "ct_log_url": "dummy_url",
        "ct_index": 1,
        "ct_entry": json.dumps(ct_entry_dict)
    }]
    # Patch cert_cache to always return False for is_duplicate (async)
    async def fake_is_duplicate(*a, **kw):
        return False
    async def fake_add(*a, **kw):
        return None
    monkeypatch.setattr("src.manager_api.certificate_cache.cert_cache.is_duplicate", fake_is_duplicate)
    monkeypatch.setattr("src.manager_api.certificate_cache.cert_cache.add", fake_add)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/api/worker/upload", json=payload)
    print("UPLOAD RESPONSE:", response.status_code, response.text)
    assert response.status_code == 200
    assert "inserted" in response.json()

@pytest.mark.asyncio
async def test_worker_ping(monkeypatch):
    # Patch update_worker_status_and_summary to avoid DB
    async def fake_update_worker_status_and_summary(data, db, status):
        return {"message": "ok"}
    monkeypatch.setattr("src.manager_api.routers.worker_pings.update_worker_status_and_summary", fake_update_worker_status_and_summary)
    payload = {
        "worker_name": "dummy_worker",
        "log_name": "dummy_log",
        "ct_log_url": "dummy_url",
        "start": 0,
        "end": 10,
        "current": 5,
        "last_uploaded_index": 5,
        "status": JobStatus.RUNNING.value,
        "jp_count": 1,
        "jp_ratio": 0.1,
        "ip_address": "127.0.0.1"
    }
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/api/worker/ping", json=payload)
    print("PING RESPONSE:", response.status_code, response.text)
    assert response.status_code == 200
    assert "ping_interval_sec" in response.json()

@pytest.mark.asyncio
async def test_worker_completed(monkeypatch):
    async def fake_update_worker_status_and_summary(data, db, status):
        return {"message": "ok"}
    monkeypatch.setattr("src.manager_api.routers.worker_pings.update_worker_status_and_summary", fake_update_worker_status_and_summary)
    payload = {
        "worker_name": "dummy_worker",
        "log_name": "dummy_log",
        "ct_log_url": "dummy_url",
        "start": 0,
        "end": 10,
        "current": 10,
        "last_uploaded_index": 10,
        "status": JobStatus.COMPLETED.value,
        "jp_count": 1,
        "jp_ratio": 0.1,
        "ip_address": "127.0.0.1"
    }
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/api/worker/completed", json=payload)
    print("COMPLETED RESPONSE:", response.status_code, response.text)
    assert response.status_code == 200
    assert response.json()["message"] == "ok"




@pytest.mark.asyncio
async def test_worker_error(monkeypatch, tmp_path):
    # Patch log path to tmp_path
    import os
    resource_path = os.path.join(os.path.dirname(__file__), "resources/ov/www.toyo-integration.co.jp.json")
    with open(resource_path, "r") as f:
        ct_entry_dict = json.load(f)
    orig_dir = os.path.dirname
    os.path.dirname = lambda _: str(tmp_path)
    payload = {
        "worker_name": "dummy_worker",
        "log_name": "dummy_log",
        "ct_log_url": "dummy_url",
        "ct_index": 1,
        "error_type": "upload_error",
        "error_message": "dummy error",
        "traceback": "traceback info",
        "entry": json.dumps(ct_entry_dict)
    }
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/api/worker/error", json=payload)
    print("ERROR RESPONSE:", response.status_code, response.text)
    assert response.status_code == 200
    assert response.json()["message"] == "ok"
    os.path.dirname = orig_dir
