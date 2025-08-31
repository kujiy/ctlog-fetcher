import os
import json
import glob
import shutil
import uuid
import pytest

from src.worker.worker import save_pending_request, process_pending_requests_files

def setup_module(module):
    # Create a temporary directory for testing and set as current
    module._old_cwd = os.getcwd()
    module._tmpdir = f"/tmp/test_pending_{uuid.uuid4().hex}"
    os.makedirs(module._tmpdir, exist_ok=True)
    os.chdir(module._tmpdir)
    os.makedirs("pending", exist_ok=True)

def teardown_module(module):
    os.chdir(module._old_cwd)
    shutil.rmtree(module._tmpdir)

def clear_pending_files():
    for f in glob.glob("pending/pending_*.json"):
        os.remove(f)

def test_save_pending_request_creates_file():
    clear_pending_files()
    req = {"url": "http://example.com", "method": "POST", "data": {"foo": "bar"}}
    save_pending_request(req, "pending_test")
    files = glob.glob("pending/pending_test_*.json")
    assert len(files) == 1
    with open(files[0]) as f:
        data = json.load(f)
    assert data == req

def test_process_pending_requests_files_removes_on_success(monkeypatch):
    clear_pending_files()
    req = {"url": "http://example.com", "method": "POST", "data": {"foo": "bar"}}
    save_pending_request(req, "pending_test")
    files = glob.glob("pending/pending_test_*.json")
    assert len(files) == 1
    # Patch to return a successful response
    class DummyResp:
        status_code = 200
    monkeypatch.setattr("requests.post", lambda *a, **k: DummyResp())
    process_pending_requests_files(None, file_glob="pending_test_*.json")
    files = glob.glob("pending/pending_test_*.json")
    assert len(files) == 0

def test_process_pending_requests_files_keeps_on_failure(monkeypatch):
    clear_pending_files()
    req = {"url": "http://example.com", "method": "POST", "data": {"foo": "bar"}}
    save_pending_request(req, "pending_test")
    files = glob.glob("pending/pending_test_*.json")
    assert len(files) == 1
    # Patch to return a failure response
    class DummyResp:
        status_code = 500
    monkeypatch.setattr("requests.post", lambda *a, **k: DummyResp())
    process_pending_requests_files(None, file_glob="pending_test_*.json")
    files = glob.glob("pending/pending_test_*.json")
    assert len(files) == 1
