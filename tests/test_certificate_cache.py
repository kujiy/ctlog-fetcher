#!/usr/bin/env python3
"""
Test script for Certificate Cache
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from datetime import datetime
from src.manager_api.certificate_cache import CertificateCache

import pytest

@pytest.mark.asyncio
async def test_certificate_cache():
    """Basic operation test for certificate cache"""
    print("=== Certificate Cache Test ===")
    
    # Create cache for testing
    cache = CertificateCache(max_size=10)
    
    # Test data (issuer, serial_number, certificate_fingerprint_sha256)
    test_certs = [
        ("Issuer1", "Serial1", "abc123def456"),
        ("Issuer2", "Serial2", "def456ghi789"),
        ("Issuer1", "Serial1", "abc123def456"),  # Duplicate
        ("Issuer3", "Serial3", "ghi789jkl012"),
    ]
    
    print("1. Check initial state")
    stats = await cache.get_stats()
    print(f"   Cache size: {stats['cache_size']}")
    print(f"   Hit rate: {stats['hit_rate']:.2%}")
    
    print("\n2. Certificate duplicate check test")
    for i, (issuer, serial, fingerprint) in enumerate(test_certs):
        is_dup = await cache.is_duplicate(issuer, serial, fingerprint)
        print(f"   Cert {i+1}: {issuer}/{serial} -> {'Duplicate' if is_dup else 'New'}")
        
        if not is_dup:
            await cache.add(issuer, serial, fingerprint)
            print(f"   -> Added to cache")
    
    print("\n3. Final statistics")
    stats = await cache.get_stats()
    print(f"   Cache size: {stats['cache_size']}")
    print(f"   Hit count: {stats['hit_count']}")
    print(f"   Miss count: {stats['miss_count']}")
    print(f"   Hit rate: {stats['hit_rate']:.2%}")
    
    print("\n4. Retest with same certificates (check cache hit)")
    for i, (issuer, serial, fingerprint) in enumerate(test_certs):
        is_dup = await cache.is_duplicate(issuer, serial, fingerprint)
        print(f"   Cert {i+1}: {issuer}/{serial} -> {'Duplicate' if is_dup else 'New'}")
    
    print("\n5. Final statistics")
    stats = await cache.get_stats()
    print(f"   Cache size: {stats['cache_size']}")
    print(f"   Hit count: {stats['hit_count']}")
    print(f"   Miss count: {stats['miss_count']}")
    print(f"   Hit rate: {stats['hit_rate']:.2%}")
    
    print("\n=== Test Completed ===")

@pytest.mark.asyncio
async def test_cache_size_limit():
    """Test for cache size limit"""
    print("\n=== Cache Size Limit Test ===")
    
    cache = CertificateCache(max_size=5)
    
    # Add 10 certificates (limit is 5)
    for i in range(10):
        issuer = f"Issuer{i}"
        serial = f"Serial{i}"
        fingerprint = f"fingerprint{i:03d}"
        
        await cache.add(issuer, serial, fingerprint)
        stats = await cache.get_stats()
        print(f"   Added cert {i+1}: cache_size={stats['cache_size']}")
    
    final_stats = await cache.get_stats()
    print(f"\n   Final cache size: {final_stats['cache_size']} (max: 5)")
    print("=== Size Limit Test Completed ===")

# No need for __main__ block (run with pytest)
