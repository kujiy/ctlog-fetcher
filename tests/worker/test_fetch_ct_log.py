import pytest
import unittest.mock as mock
import threading
import sys
import os
import time
import json
from requests.exceptions import RequestException

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# Import the functions we want to test
from src.worker.worker import fetch_ct_log, NeedTreeSizeException, sleep_with_stop_check


class TestFetchCtLog:
    """Test cases for the fetch_ct_log function."""

    def setup_method(self):
        """Setup for each test method."""
        # Create a threading.Event for stop_event parameter
        self.stop_event = threading.Event()
        
        # Default parameters for testing
        self.ct_log_url = "https://example.com"
        self.start = 0
        self.end = 10
        self.retry_stats = {'total_retries': 0, 'max_retry_after': 0}

    @mock.patch('src.worker.worker.requests.get')
    @mock.patch('src.worker.worker.sleep_with_stop_check')
    def test_successful_fetch(self, mock_sleep, mock_get):
        """Test successful fetch of CT log entries."""
        # Mock successful response
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'entries': ['entry1', 'entry2']}
        mock_get.return_value = mock_response

        # Call the function
        result = fetch_ct_log(
            self.ct_log_url, 
            self.start, 
            self.end, 
            proxies=None, 
            retry_stats=self.retry_stats, 
            stop_event=self.stop_event
        )

        # Assert results
        assert result == ['entry1', 'entry2']
        assert self.retry_stats['total_retries'] == 0
        assert self.retry_stats['max_retry_after'] == 0
        mock_sleep.assert_not_called()

    @mock.patch('src.worker.worker.requests.get')
    @mock.patch('src.worker.worker.sleep_with_stop_check')
    def test_rate_limit_retry_with_header(self, mock_sleep, mock_get):
        """Test handling of 429 rate limit with Retry-After header."""
        # Mock rate-limited response with Retry-After header
        mock_response = mock.Mock()
        mock_response.status_code = 429
        mock_response.headers = {'Retry-After': '10'}
        mock_get.return_value = mock_response

        # Call the function
        result = fetch_ct_log(
            self.ct_log_url, 
            self.start, 
            self.end, 
            proxies=None, 
            retry_stats=self.retry_stats, 
            stop_event=self.stop_event
        )

        # Assert results
        assert result == []
        assert self.retry_stats['total_retries'] == 1
        assert self.retry_stats['max_retry_after'] == 10
        mock_sleep.assert_called_once_with(10, self.stop_event)

    @mock.patch('src.worker.worker.requests.get')
    @mock.patch('src.worker.worker.sleep_with_stop_check')
    def test_rate_limit_retry_without_header(self, mock_sleep, mock_get):
        """Test handling of 429 rate limit without Retry-After header."""
        # Mock rate-limited response without Retry-After header
        mock_response = mock.Mock()
        mock_response.status_code = 429
        mock_response.headers = {}
        mock_get.return_value = mock_response

        # Call the function
        result = fetch_ct_log(
            self.ct_log_url, 
            self.start, 
            self.end, 
            proxies=None, 
            retry_stats=self.retry_stats, 
            stop_event=self.stop_event
        )

        # Assert results
        assert result == []
        assert self.retry_stats['total_retries'] == 1
        assert self.retry_stats['max_retry_after'] == 5  # Default is 5 seconds
        mock_sleep.assert_called_once_with(5, self.stop_event)

    @mock.patch('src.worker.worker.requests.get')
    @mock.patch('src.worker.worker.sleep_with_stop_check')
    def test_multiple_rate_limits(self, mock_sleep, mock_get):
        """Test handling of multiple rate limits with different wait times."""
        # Setup retry_stats
        self.retry_stats = {'total_retries': 0, 'max_retry_after': 0}
        
        # First call: rate limit with 5 seconds
        mock_response1 = mock.Mock()
        mock_response1.status_code = 429
        mock_response1.headers = {'Retry-After': '5'}
        
        # Second call: rate limit with 15 seconds
        mock_response2 = mock.Mock()
        mock_response2.status_code = 429
        mock_response2.headers = {'Retry-After': '15'}
        
        # Third call: rate limit with 8 seconds
        mock_response3 = mock.Mock()
        mock_response3.status_code = 429
        mock_response3.headers = {'Retry-After': '8'}
        
        # Set up mock to return different responses on subsequent calls
        mock_get.side_effect = [mock_response1, mock_response2, mock_response3]
        
        # Call the function three times
        for _ in range(3):
            fetch_ct_log(
                self.ct_log_url, 
                self.start, 
                self.end, 
                proxies=None, 
                retry_stats=self.retry_stats, 
                stop_event=self.stop_event
            )
        
        # Assert results
        assert self.retry_stats['total_retries'] == 3
        assert self.retry_stats['max_retry_after'] == 15  # Max should be 15
        assert mock_sleep.call_count == 3
        
        # Check sleep was called with correct durations
        mock_sleep.assert_has_calls([
            mock.call(5, self.stop_event),
            mock.call(15, self.stop_event),
            mock.call(8, self.stop_event),
        ])

    @mock.patch('src.worker.worker.requests.get')
    @mock.patch('src.worker.worker.sleep_with_stop_check')
    def test_need_tree_size_exception(self, mock_sleep, mock_get):
        """Test handling of 'need tree size' error (400)."""
        # Mock need tree size response
        mock_response = mock.Mock()
        mock_response.status_code = 400
        mock_response.text = "need tree size"
        mock_get.return_value = mock_response

        # Call the function and check for exception
        with pytest.raises(NeedTreeSizeException):
            fetch_ct_log(
                self.ct_log_url, 
                self.start, 
                self.end, 
                proxies=None, 
                retry_stats=self.retry_stats, 
                stop_event=self.stop_event
            )
        
        # Assert retry stats were not modified
        assert self.retry_stats['total_retries'] == 0
        assert self.retry_stats['max_retry_after'] == 0
        mock_sleep.assert_not_called()

    @mock.patch('src.worker.worker.requests.get')
    @mock.patch('src.worker.worker.sleep_with_stop_check')
    def test_other_error_codes(self, mock_sleep, mock_get):
        """Test handling of other error codes."""
        # Mock other error response
        mock_response = mock.Mock()
        mock_response.status_code = 500
        mock_get.return_value = mock_response

        # Call the function
        result = fetch_ct_log(
            self.ct_log_url, 
            self.start, 
            self.end, 
            proxies=None, 
            retry_stats=self.retry_stats, 
            stop_event=self.stop_event
        )

        # Assert results
        assert result == []
        assert self.retry_stats['total_retries'] == 0
        assert self.retry_stats['max_retry_after'] == 0
        mock_sleep.assert_called_once_with(5, self.stop_event)

    @mock.patch('src.worker.worker.requests.get')
    @mock.patch('src.worker.worker.sleep_with_stop_check')
    def test_request_exception(self, mock_sleep, mock_get):
        """Test handling of request exceptions."""
        # Mock request exception
        mock_get.side_effect = RequestException("Connection error")

        # Call the function
        result = fetch_ct_log(
            self.ct_log_url, 
            self.start, 
            self.end, 
            proxies=None, 
            retry_stats=self.retry_stats, 
            stop_event=self.stop_event
        )

        # Assert results
        assert result == []
        assert self.retry_stats['total_retries'] == 0
        assert self.retry_stats['max_retry_after'] == 0
        mock_sleep.assert_not_called()

    @mock.patch('src.worker.worker.requests.get')
    def test_proxy_handling_single(self, mock_get):
        """Test handling of a single proxy."""
        # Set up a single proxy
        proxy = "http://proxy.example.com:8080"
        
        # Mock successful response
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'entries': []}
        mock_get.return_value = mock_response

        # Call the function
        fetch_ct_log(
            self.ct_log_url, 
            self.start, 
            self.end, 
            proxies=proxy, 
            retry_stats=self.retry_stats, 
            stop_event=self.stop_event
        )

        # Assert proxy was used correctly
        mock_get.assert_called_once()
        args, kwargs = mock_get.call_args
        assert kwargs['proxies'] == proxy

    @mock.patch('src.worker.worker.random.choice')
    @mock.patch('src.worker.worker.requests.get')
    def test_proxy_handling_multiple(self, mock_get, mock_choice):
        """Test handling of multiple proxies."""
        # Set up multiple proxies
        proxies = ["http://proxy1.example.com:8080", "http://proxy2.example.com:8080"]
        
        # Mock random choice to return the first proxy
        mock_choice.return_value = proxies[0]
        
        # Mock successful response
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'entries': []}
        mock_get.return_value = mock_response

        # Call the function
        fetch_ct_log(
            self.ct_log_url, 
            self.start, 
            self.end, 
            proxies=proxies, 
            retry_stats=self.retry_stats, 
            stop_event=self.stop_event
        )

        # Assert random choice was called with proxies list
        mock_choice.assert_called_once_with(proxies)
        
        # Assert selected proxy was used correctly
        mock_get.assert_called_once()
        args, kwargs = mock_get.call_args
        assert kwargs['proxies'] == {"http": proxies[0], "https": proxies[0]}


# Test for sleep_with_stop_check function
class TestSleepWithStopCheck:
    """Test cases for the sleep_with_stop_check function."""
    
    def setup_method(self):
        """Setup for each test method."""
        self.stop_event = threading.Event()
    
    @mock.patch('src.worker.worker.time.sleep')
    def test_normal_sleep(self, mock_sleep):
        """Test normal sleep without interruption."""
        sleep_with_stop_check(3, self.stop_event)
        assert mock_sleep.call_count == 3
        mock_sleep.assert_called_with(1)
    
    @mock.patch('src.worker.worker.time.sleep')
    def test_interrupted_sleep(self, mock_sleep):
        """Test sleep with interruption."""
        # Set up mock to set the stop event after the first sleep
        def set_stop_event(*args, **kwargs):
            self.stop_event.set()
        
        mock_sleep.side_effect = set_stop_event
        
        sleep_with_stop_check(5, self.stop_event)
        
        # Should only sleep once before breaking out
        assert mock_sleep.call_count == 1
