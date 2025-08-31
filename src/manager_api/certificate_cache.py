import asyncio
from typing import Set, Tuple, Optional
from datetime import datetime
import logging

logger = logging.getLogger("certificate_cache")

class CertificateCache:
    """
    In-memory cache for certificate duplicate checking.
    Duplicates are determined by the combination of issuer, serial_number, and certificate_fingerprint_sha256.
    """
    
    def __init__(self, max_size: int = 50000):
        self._cache: Set[Tuple[str, str, str]] = set()
        self._max_size = max_size
        self._lock = asyncio.Lock()
        self._hit_count = 0
        self._miss_count = 0
    
    def _create_key(self, issuer: str, serial_number: str, certificate_fingerprint_sha256: str) -> Tuple[str, str, str]:
        """Create cache key"""
        # Convert None values to empty strings
        issuer = issuer or ""
        serial_number = serial_number or ""
        certificate_fingerprint_sha256 = certificate_fingerprint_sha256 or ""
        
        return (issuer, serial_number, certificate_fingerprint_sha256)
    
    async def is_duplicate(self, issuer: str, serial_number: str, certificate_fingerprint_sha256: str) -> bool:
        """
        Duplicate check. Returns True if found in cache.
        
        Args:
            issuer: Issuer
            serial_number: Serial number
            certificate_fingerprint_sha256: SHA-256 fingerprint of the certificate
            
        Returns:
            bool: True if duplicate
        """
        key = self._create_key(issuer, serial_number, certificate_fingerprint_sha256)
        
        async with self._lock:
            is_dup = key in self._cache
            if is_dup:
                self._hit_count += 1
            else:
                self._miss_count += 1
            return is_dup
    
    async def add(self, issuer: str, serial_number: str, certificate_fingerprint_sha256: str):
        """
        Add to cache
        
        Args:
            issuer: Issuer
            serial_number: Serial number
            certificate_fingerprint_sha256: SHA-256 fingerprint of the certificate
        """
        key = self._create_key(issuer, serial_number, certificate_fingerprint_sha256)
        
        async with self._lock:
            # Cache size limit
            if len(self._cache) >= self._max_size:
                # LRU-like deletion (delete half for simplicity)
                cache_list = list(self._cache)
                self._cache = set(cache_list[self._max_size//2:])
                logger.debug(f"Certificate cache size limit reached, cleared {self._max_size//2} entries")
            
            self._cache.add(key)
    
    async def get_stats(self) -> dict:
        """Get cache statistics"""
        async with self._lock:
            total_requests = self._hit_count + self._miss_count
            hit_rate = (self._hit_count / total_requests) if total_requests > 0 else 0
            
            return {
                "cache_size": len(self._cache),
                "max_size": self._max_size,
                "hit_count": self._hit_count,
                "miss_count": self._miss_count,
                "hit_rate": hit_rate,
                "total_requests": total_requests
            }
    
    async def clear(self):
        """Clear cache"""
        async with self._lock:
            self._cache.clear()
            self._hit_count = 0
            self._miss_count = 0
            logger.info("Certificate cache cleared")

# Global cache instance
cert_cache = CertificateCache()
