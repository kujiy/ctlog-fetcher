import pytest
import httpx
from httpx import ASGITransport
from src.manager_api.main import app
import json
import os
import asyncio
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_worker_upload2_success(monkeypatch):
    """Test successful upload of certificates using upload2 endpoint"""

    # Mock database session
    class _DummyResult:
        def scalars(self):
            class _S:
                def first(self):
                    return None
            return _S()
        def all(self):
            return []
        def scalar_one_or_none(self):
            return None

    class _DummySession:
        def __init__(self):
            self.added_items = []

        def add(self, item):
            self.added_items.append(item)

        def add_all(self, items):
            self.added_items.extend(items)

        async def commit(self):
            pass

        async def rollback(self):
            pass

        async def close(self):
            pass

        async def execute(self, *a, **k):
            return _DummyResult()

    async def fake_get_async_session():
        yield _DummySession()

    monkeypatch.setattr("src.manager_api.db.get_async_session", fake_get_async_session)

    # Mock certificate cache to return False for duplicates
    async def fake_is_duplicate(*a, **kw):
        return False

    async def fake_add(*a, **kw):
        return None

    async def fake_get_stats():
        return {
            'hit_rate': 0.85,
            'cache_size': 1000,
            'hit_count': 850,
            'miss_count': 150
        }

    monkeypatch.setattr("src.manager_api.certificate_cache.cert_cache.is_duplicate", fake_is_duplicate)
    monkeypatch.setattr("src.manager_api.certificate_cache.cert_cache.add", fake_add)
    monkeypatch.setattr("src.manager_api.certificate_cache.cert_cache.get_stats", fake_get_stats)

    # Test data from the provided sample
    payload = [
        {
            "ct_entry": "{\"leaf_input\":\"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\",\"extra_data\":\"AAhGAASuMIIEqjCCA5KgAwIBAgIQDeD/te5iy2EQn2CMnO1e0zANBgkqhkiG9w0BAQsFADBhMQswCQYDVQQGEwJVUzEVMBMGA1UEChMMRGlnaUNlcnQgSW5jMRkwFwYDVQQLExB3d3cuZGlnaWNlcnQuY29tMSAwHgYDVQQDExdEaWdpQ2VydCBHbG9iYWwgUm9vdCBHMjAeFw0xNzExMjcxMjQ2NDBaFw0yNzExMjcxMjQ2NDBaMG4xCzAJBgNVBAYTAlVTMRUwEwYDVQQKEwxEaWdpQ2VydCBJbmMxGTAXBgNVBAsTEHd3dy5kaWdpY2VydC5jb20xLTArBgNVBAMTJEVuY3J5cHRpb24gRXZlcnl3aGVyZSBEViBUTFMgQ0EgLSBHMjCCASIwDQYJKoZIhvcNAQEBBQADggEPADCCAQoCggEBAO8Uf46i/nr7pkgTDqnEeSIfCFqvPnUq3aF1tMJ5hh9MnO6Lmt5UdHfBGwC9Si+XjK12cjZgxObsL6Rg1njvNhAMJ4JunN0JGGRJGSevbJsA3sc68nbPQzuKp5Jc8vpryp2mts38pSCXorPR+schQisKA7OSQ1MjcFN0d7tbrceWFNbzgL2csJVQeogOBGSe/KZEIZw6gXLKeFe7mupnNYJROi2iC11+HuF79iAttMc32Cv6UOxixY/3ZV+LzpLnklFq98XORgwkIJL1HuvPha8yvb+W6JislZJL+HLFtidoxmI7Qm3ZyIV66W533DsGFimFJkz3y0GeHWuSVMbIlfsCAwEAAaOCAU8wggFLMB0GA1UdDgQWBBR435GQX+7erPbFdevVTFVT7yRKtjAfBgNVHSMEGDAWgBROIlQgGJXm427mD/r6uRLtBhePOTAOBgNVHQ8BAf8EBAMCAYYwHQYDVR0lBBYwFAYIKwYBBQUHAwEGCCsGAQUFBwMCMBIGA1UdEwEB/wQIMAYBAf8CAQAwNAYIKwYBBQUHAQEEKDAmMCQGCCsGAQUFBzABhhhodHRwOi8vb2NzcC5kaWdpY2VydC5jb20wQgYDVR0fBDswOTA3oDWgM4YxaHR0cDovL2NybDMuZGlnaWNlcnQuY29tL0RpZ2lDZXJ0R2xvYmFsUm9vdEcyLmNybDBMBgNVHSAERTBDMDcGCWCGSAGG/WwBAjAqMCgGCCsGAQUFBwIBFhxodHRwczovL3d3dy5kaWdpY2VydC5jb20vQ1BTMAgGBmeBDAECATANBgkqhkiG9w0BAQsFAAOCAQEAoBs1eCLKakLtVRPFRjBIJ9LJL0s8ZWum8U8/1TMVkQMBn+CPb5xnCD0GSA6L/V0ZFrMNqBirrr5B241OesECvxIi98bZ90h9+q/X5eMyOD35f8YTaEMpdnQCnawIwiHx06/0BfiTj+b/XQih+mqt3ZXexNCJqKexdiB2IWGSKcgahPacWkk/BAQFisKIFYEqHzV974S3FAz/8LIfD58xnsENGfzyIDkH3JrwYZ8caPTf6ZX9M1GrISN8HnWTtdNCH2xEajRa/h9ZBXjUyFKQrGk2n2hcLrfZSbynEC/pSw/ET7H5nWwckjmAJ1l9fcnbqkU/pf6uMQmnfl0JQjJNSgADkjCCA44wggJ2oAMCAQICEAM68eanEamguyhksR0J+uUwDQYJKoZIhvcNAQELBQAwYTELMAkGA1UEBhMCVVMxFTATBgNVBAoTDERpZ2lDZXJ0IEluYzEZMBcGA1UECxMQd3d3LmRpZ2ljZXJ0LmNvbTEgMB4GA1UEAxMXRGlnaUNlcnQgR2xvYmFsIFJvb3QgRzIwHhcNMTMwODAxMTIwMDAwWhcNMzgwMTE1MTIwMDAwWjBhMQswCQYDVQQGEwJVUzEVMBMGA1UEChMMRGlnaUNlcnQgSW5jMRkwFwYDVQQLExB3d3cuZGlnaWNlcnQuY29tMSAwHgYDVQQDExdEaWdpQ2VydCBHbG9iYWwgUm9vdCBHMjCCASIwDQYJKoZIhvcNAQEBBQADggEPADCCAQoCggEBALs3zTTce2vJsmiQrUp1/0a6IQoIjfUZVMn7iNvzrvI6iZE8euarBhprz6wt6F4JJES6Ypp+1qOofuBUdSAFrFC3nGMabDDc2h8Zsdce3v3X4MuUgzeu7B9DTt17LNK9LqUv5Km4rTrUmaS2JembawBgkmD/TyFJGPdnkKthBpyP8rrptOmSMmu181foXRvNjB2rlQSVSfM1LZbjSW3dd+P7SUu0rFUHqY+Vs7Qju0xtRfD2qbKVMLT9TFWMJ0pXFHyCnc1zktMWSgYMjFDRjx4Jvheh5iHK/YPlELyDpQrEZyj2cxQUPUZ2w4cUiSE0Ta8PRQymSaG6u5zFsTODKYUCAwEAAaNCMEAwDwYDVR0TAQH/BAUwAwEB/zAOBgNVHQ8BAf8EBAMCAYYwHQYDVR0OBBYEFE4iVCAYlebjbuYP+vq5Eu0GF485MA0GCSqGSIb3DQEBCwUAA4IBAQBgZyiUbw5IY+sx3epnGNWJfTzFi0p/6b7bKxffsF9zdyoyEzmBZ0KEI/JFZzXsiL/4j7BhDDSkriBMhMbb+DXhdtnfpkK7x0QIhn82dCRa2mwNFFk1vfJJ3bYfybMNRyo9mS+7XLu11CDhmV9TRhXbaJvw8zDVPjHijYSe44ra2pY+NROlX/D5cFBwR0ERVxlOwI+uBsSVExcvGyWfdfKxjpmhbxOxQXH+iCrITxAgVdfzFEXl4ET06oeVMpMO/lNG+iyd/4siuUvZCUWk3qS4mljdG31Sn45ZQ4iBpJ4m1W+t3Q3GN33tA5Ib5Xdfdu48jcRdVlui2WZuszU35TK2\"}",
            "ct_log_url": "https://wyvern.ct.digicert.com/2025h2/",
            "log_name": "wyvern2025h2",
            "worker_name": "ponk-doki-5230",
            "ct_index": 1216220,
        }
    ]

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/api/worker/upload2", json=payload)

    print("UPLOAD2 RESPONSE:", response.status_code, response.text)
    assert response.status_code == 200

    response_data = response.json()
    assert "inserted" in response_data
    assert "skipped_duplicates" in response_data
    assert isinstance(response_data["inserted"], int)
    assert isinstance(response_data["skipped_duplicates"], int)


@pytest.mark.asyncio
async def test_worker_upload2_with_duplicates(monkeypatch):
    """Test upload2 endpoint when certificates are duplicates"""

    # Mock database session
    class _DummySession:
        def __init__(self):
            self.added_items = []

        def add(self, item):
            self.added_items.append(item)

        def add_all(self, items):
            self.added_items.extend(items)

        async def commit(self):
            pass

        async def rollback(self):
            pass

        async def close(self):
            pass

    async def fake_get_async_session():
        yield _DummySession()

    monkeypatch.setattr("src.manager_api.db.get_async_session", fake_get_async_session)

    # Mock certificate cache to return True for duplicates (all certificates are duplicates)
    async def fake_is_duplicate(*a, **kw):
        return True

    async def fake_add(*a, **kw):
        return None

    async def fake_get_stats():
        return {
            'hit_rate': 1.0,
            'cache_size': 1000,
            'hit_count': 1000,
            'miss_count': 0
        }

    monkeypatch.setattr("src.manager_api.certificate_cache.cert_cache.is_duplicate", fake_is_duplicate)
    monkeypatch.setattr("src.manager_api.certificate_cache.cert_cache.add", fake_add)
    monkeypatch.setattr("src.manager_api.certificate_cache.cert_cache.get_stats", fake_get_stats)

    # Same test data as above
    payload = [
        {
            "ct_entry": "{\"leaf_input\":\"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\",\"extra_data\":\"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\"}",
            "ct_log_url": "https://wyvern.ct.digicert.com/2025h2/",
            "log_name": "wyvern2025h2",
            "worker_name": "ponk-doki-5230",
            "ct_index": 1216220,
        }
    ]

