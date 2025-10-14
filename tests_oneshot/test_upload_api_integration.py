import requests
import json
import os
import pytest
from src.share.logger import logger

def test_upload_api_integration():
    # The path is relative to the project root
    json_path = os.path.join(os.path.dirname(__file__), "./pending_upload_test.json")
    with open(json_path, "r", encoding="utf-8") as f:
        file_json = json.load(f)
    data = file_json["data"]

    url = "http://localhost:1173/api/worker/upload"
    try:
        response = requests.post(url, json=data, timeout=5)
        logger.warning(f"status_code={response.status_code}")
        # assert response.status_code == 200
        res_json = response.json()
        logger.warning(res_json)
        # Check that the keys 'inserted' and 'skipped_duplicates' exist
        assert "inserted" in res_json
        assert "skipped_duplicates" in res_json
    except requests.exceptions.ConnectionError:
        pytest.skip("Server not running on localhost:1173 - skipping integration test")

def test_completed_api_integration():
    # The path is relative to the project root
    json_path = os.path.join(os.path.dirname(__file__), "./pending_completed_test.json")
    with open(json_path, "r", encoding="utf-8") as f:
        file_json = json.load(f)
    data = file_json["data"]

    url = "http://localhost:1173/api/worker/completed"
    try:
        response = requests.post(url, json=data, timeout=5)
        logger.warning(f"status_code={response.status_code}")
        # assert response.status_code == 200
        res_json = response.json()
        logger.warning(res_json)
        # Check that the key 'message' exists
        assert "message" in res_json
    except requests.exceptions.ConnectionError:
        pytest.skip("Server not running on localhost:1173 - skipping integration test")
