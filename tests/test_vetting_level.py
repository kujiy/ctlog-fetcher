import json
import os
import pytest

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.share.cert_parser2 import JPCertificateParser2, VettingLevel

@pytest.mark.parametrize(
    "json_path,expected",
    [
        ("tests/resources/ev/recruit.json", VettingLevel.EV.value),
        ("tests/resources/ov/www.toyo-integration.co.jp.json", VettingLevel.OV.value),
        ("tests/resources/dv/pckk.json", VettingLevel.DV.value),
    ]
)
def test_vetting_level(json_path, expected):
    parser = JPCertificateParser2()
    with open(json_path, "r") as f:
        ct_entry = json.load(f)
    cert_data = parser.parse_ct_entry_to_cert2_data(ct_entry)
    assert cert_data is not None
    assert cert_data.vetting_level == expected
