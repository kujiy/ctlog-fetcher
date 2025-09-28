#!/usr/bin/env python3
"""
Test script to verify HTTP/2 usage with httpx client for CT log fetching.
"""
import httpx
import random
import time

def test_httpx_http2_connection():
    """Test that httpx client uses HTTP/2 and connection reuse."""
    # Create httpx client with HTTP/2 enabled
    client = httpx.Client(
        http2=True,  # Force HTTP/2 usage
        timeout=10.0,
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20)
    )
    
    # Test URLs - Google CT logs
    test_urls = [
        "https://ct.googleapis.com/logs/us1/argon2025h1/ct/v1/get-entries?start=1000&end=1010",
        "https://ct.googleapis.com/logs/us1/argon2025h1/ct/v1/get-entries?start=1011&end=1021",
        "https://ct.googleapis.com/logs/us1/argon2025h1/ct/v1/get-entries?start=1022&end=1032",
    ]
    
    try:
        print("Testing HTTP/2 connection and session reuse with CT logs...")
        
        for i, url in enumerate(test_urls):
            start_time = time.time()
            
            try:
                resp = client.get(url)
                end_time = time.time()
                
                # Check HTTP version
                http_version = resp.http_version
                print(f"Request {i+1}:")
                print(f"  URL: {url}")
                print(f"  HTTP Version: {http_version}")
                print(f"  Status Code: {resp.status_code}")
                print(f"  Response Time: {end_time - start_time:.3f}s")
                
                if resp.status_code == 200:
                    data = resp.json()
                    entries_count = len(data.get('entries', []))
                    print(f"  Entries Retrieved: {entries_count}")
                elif resp.status_code == 429:
                    retry_after = resp.headers.get('Retry-After', 'unknown')
                    print(f"  Rate Limited - Retry After: {retry_after}s")
                
                print()
                
                # Small delay between requests to avoid rate limiting
                time.sleep(1)
                
            except Exception as e:
                print(f"Request {i+1} failed: {e}")
                print()
    
    finally:
        # Clean up the client
        client.close()
        print("HTTP client closed.")

if __name__ == "__main__":
    test_httpx_http2_connection()