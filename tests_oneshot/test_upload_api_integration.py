import requests
import json
import os
from src.share.logger import logger

def test_upload_api_integration():
    # パスはプロジェクトルートからの相対パス
    json_path = os.path.join(os.path.dirname(__file__), "./pending_upload_test.json")
    with open(json_path, "r", encoding="utf-8") as f:
        file_json = json.load(f)
    data = file_json["data"]

    url = "http://ctlog-fetcher.tplinkdns.com:1173/api/worker/upload"
    response = requests.post(url, json=data)
    logger.warning(f"status_code={response.status_code}")
    # assert response.status_code == 200
    res_json = response.json()
    logger.warning(res_json)
    # inserted/skipped_duplicatesのキーがあることを確認
    assert "inserted" in res_json
    assert "skipped_duplicates" in res_json


def test_completed_api_integration():
    # パスはプロジェクトルートからの相対パス
    json_path = os.path.join(os.path.dirname(__file__), "./pending_completed_test.json")
    with open(json_path, "r", encoding="utf-8") as f:
        file_json = json.load(f)
    data = file_json["data"]

    url = "http://ctlog-fetcher.tplinkdns.com:1173/api/worker/completed"
    response = requests.post(url, json=data)
    logger.warning(f"status_code={response.status_code}")
    # assert response.status_code == 200
    res_json = response.json()
    logger.warning(res_json)
    # inserted/skipped_duplicatesのキーがあることを確認
    assert "message" in res_json
