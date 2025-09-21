"""
Test extract_jp_certs function with failed entries from tests/resources/failed directory.

This test loads failed certificate entries that were saved during actual worker execution
and verifies that extract_jp_certs properly handles these problematic entries.
"""

import json
import os
import sys
import glob
import unittest
import tempfile
import shutil
import logging
import io
from unittest.mock import Mock, patch

# Add the project root to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.worker.worker_upload import extract_jp_certs


class TestExtractJpCertsFailed(unittest.TestCase):
    """Test extract_jp_certs with failed entries."""

    def setUp(self):
        """Set up test fixtures."""
        self.failed_dir = os.path.join(os.path.dirname(__file__), 'resources', 'failed')

        # Mock args object
        self.mock_args = Mock()
        self.mock_args.worker_name = "test_worker"

        # Test parameters
        self.log_name = "test_log"
        self.ct_log_url = "https://test.ct.log/"
        self.my_ip = "127.0.0.1"
        self.current = 1000


    def test_extract_jp_certs_with_specific_asn1_error(self):
        """Test extract_jp_certs with the specific ASN.1 parsing error from the provided file."""
        # Load the specific failed entry file
        specific_file = os.path.join(self.failed_dir, "failed_entry_log2026b_1558_7d21b257.json")

        if not os.path.exists(specific_file):
            self.skipTest(f"Specific failed entry file not found: {specific_file}")

        with open(specific_file, 'r') as f:
            failed_data = json.load(f)

        # Verify this is the expected ASN.1 error
        expected_error_patterns = [
            "error parsing asn1 value",
            "ParseError",
            "UnexpectedTag"
        ]

        error_message = failed_data['error_message']
        for pattern in expected_error_patterns:
            self.assertIn(pattern, error_message,
                         f"Expected error pattern '{pattern}' not found in: {error_message}")

        # Test the entry with error capture
        original_entry = failed_data['entry']
        entries = [original_entry]

        # Capture the actual error that occurs during extract_jp_certs execution
        captured_error = None
        captured_traceback = None

        def capture_error(*args, **kwargs):
            nonlocal captured_error, captured_traceback
            captured_error = kwargs.get('error_message') or (args[2] if len(args) > 2 else None)
            captured_traceback = kwargs.get('traceback_str') or (args[3] if len(args) > 3 else None)
            # Print to console for pytest visibility
            print(f"\n🎯 SPECIFIC ASN.1 ERROR CAPTURED: {captured_error}")
            if captured_traceback:
                print(f"📋 SPECIFIC TRACEBACK:\n{captured_traceback}")

        # Patch the report_worker_error function to capture errors
        with patch('src.worker.worker.report_worker_error', side_effect=capture_error):
            jp_certs = extract_jp_certs(
                entries=entries,
                log_name=log_name,
                ct_log_url=ct_log_url,
                args=args,
                my_ip=my_ip,
                current=current
            )
            batch_jp_count = len(jp_certs)
            batch_total_count = len(entries)

        # Verify the function handles the error gracefully
        self.assertEqual(jp_certs, [])
        self.assertEqual(batch_jp_count, 0)
        self.assertEqual(batch_total_count, 0)

        # Detailed error comparison for the specific file
        print(f"\n🎯 DETAILED ASN.1 ERROR ANALYSIS:")
        print(f"📁 Expected error: {error_message}")
        if captured_error:
            print(f"🔍 Captured error: {captured_error}")

            # Verify that the same error patterns are present
            matches = 0
            for pattern in expected_error_patterns:
                if pattern in error_message and pattern in captured_error:
                    print(f"✅ Pattern '{pattern}' matches in both errors")
                    matches += 1
                elif pattern in error_message:
                    print(f"⚠️  Pattern '{pattern}' found in expected but not captured")
                elif pattern in captured_error:
                    print(f"⚠️  Pattern '{pattern}' found in captured but not expected")

            print(f"📊 Pattern match score: {matches}/{len(expected_error_patterns)}")

            # Check if errors are essentially the same
            if matches == len(expected_error_patterns):
                print(f"🎉 ERROR REPRODUCTION SUCCESSFUL: Same error reproduced!")
            else:
                print(f"⚠️  ERROR REPRODUCTION PARTIAL: Some differences detected")
        else:
            print(f"❌ No error was captured - this may indicate a problem")

        print(f"\n✅ Successfully handled ASN.1 parsing error")
        print(f"📈 Entry processed without crashing the function")




if __name__ == '__main__':
    # Run the tests
    unittest.main(verbosity=2)
