import os
import json
import types
from src.worker.worker import extract_jp_certs

def test_extract_jp_certs_worker():
    resource_path = os.path.join(os.path.dirname(__file__), 'resources', 'ct.googleapis.com_logs_eu1_xenon2025h1_ct_v1_get-entries_start_959904_end_969903_jp.json')
    with open(resource_path, 'r') as f:
        data = json.load(f)
    entries = data['entries']
    # Dummy args object with required attributes
    class DummyArgs:
        worker_name = 'dummy_worker'
        manager = 'http://localhost:8000'
    args = DummyArgs()
    log_name = 'eu1_xenon2025h1'
    ct_log_url = 'https://ct.googleapis.com/logs/eu1/xenon2025h1/'
    my_ip = '127.0.0.1'
    current = 0
    jp_certs = extract_jp_certs(entries, log_name, ct_log_url, args, my_ip, current)
    assert isinstance(jp_certs, list)
    batch_jp_count = len(jp_certs)
    batch_total_count = len(entries)
    assert batch_jp_count > 0
    assert batch_total_count == len(entries)
    for cert in jp_certs:
        assert cert['common_name'].endswith('.jp')
    print(f"Extracted {batch_jp_count} .jp certs from {batch_total_count} entries.")
