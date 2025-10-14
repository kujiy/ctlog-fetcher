"""
Test parse_ct_entry_to_certificate_data function with specific failed entry.

This test focuses on testing the parse_ct_entry_to_certificate_data function directly
with a specific failed entry to ensure it can handle problematic certificate data gracefully.
"""

import json
import os
import sys
import unittest
from unittest.mock import Mock

# Add the project root to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.share.cert_parser import JPCertificateParser


class TestParseCTEntryToCertificateData(unittest.TestCase):
    """Test parse_ct_entry_to_certificate_data with specific failed entry."""

    def setUp(self):
        """Set up test fixtures."""
        self.parser = JPCertificateParser()

        # Load the specific failed entry
        self.failed_entry_file = os.path.join(
            os.path.dirname(__file__),
            'resources',
            'invalid_certs',
            'path-length.json'
        )

    def test_print_exception_on_failed_entry(self):
        """Test that exception is raised and printed for problematic CT entry."""
        with open(self.failed_entry_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        ct_entry = data["entry"]
        try:
            d = self.parser.parse_ct_entry_to_certificate_data(ct_entry)
        except Exception as e:
            print(e)
        assert d is None


def test_parse_issuer_null():
    from src.share.cert_parser import JPCertificateParser
    import json
    parser = JPCertificateParser()
    with open("tests/resources/issuer/issuer_null.json", "r", encoding="utf-8") as f:
        ct_entry = json.load(f)
    result = parser.parse_ct_entry_to_certificate_data(ct_entry)
    # when issuer CN is missing, the issuer DN string is returned, so we check for the DN string
    assert result.get("issuer") == 'OU=Public Certification Authority - G2,O=Chunghwa Telecom Co.\\, Ltd.,C=TW'


if __name__ == '__main__':
    # Run the tests
    unittest.main(verbosity=2)
