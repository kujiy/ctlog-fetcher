import os
import sys
import pytest

# src/ui/main.py の parse_metrics_text をimport
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src/ui")))
from metrics_utils import parse_metrics_text

def test_parse_metrics_text_sample():
    sample_path = os.path.join(os.path.dirname(__file__), "resources/metrics/sample_metrics.txt")
    with open(sample_path, encoding="utf-8") as f:
        text = f.read()
    metrics = parse_metrics_text(text)

    # print all and average values
    for m in metrics:
        avg = m["sum"] / m["count"] if m["count"] > 0 else 0
        print(f'{m["method"]} {m["path"]}: sum={m["sum"]}, count={m["count"]}, avg={avg}')

    # 主要なpath/methodの平均値を検証
    d = {(m["method"], m["path"]): (m["sum"], m["count"]) for m in metrics}
    # 例: /api/worker/next_task GET
    assert ("GET", "/api/worker/next_task") in d
    s, c = d[("GET", "/api/worker/next_task")]
    assert abs(s - 585644.6176117758) < 1e-6
    assert abs(c - 10883.0) < 1e-6
    # 平均値
    avg = s / c
    assert 53.8 < avg < 53.9

    # /api/worker/ping POST
    s2, c2 = d[("POST", "/api/worker/ping")]
    assert abs(s2 - 641559.9814630151) < 1e-6
    assert abs(c2 - 26224.0) < 1e-6
    avg2 = s2 / c2
    assert 24.4 < avg2 < 24.5

    # /api/worker/resume_request POST
    s3, c3 = d[("POST", "/api/worker/resume_request")]
    assert abs(s3 - 33.302948357002606) < 1e-6
    assert abs(c3 - 2.0) < 1e-6
    avg3 = s3 / c3
    assert 16.6 < avg3 < 16.7

    # metrics数が期待通り
    assert len(metrics) >= 6
