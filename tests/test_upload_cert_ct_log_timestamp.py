import os
import json
import pytest
import asyncio
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from src.manager_api.models import Base, Cert

from src.manager_api.base_models import UploadCertItem
from src.manager_api.routers.worker_upload import upload_certificates


@pytest.mark.asyncio
async def test_upload_cert_ct_log_timestamp(monkeypatch, tmp_path):
    async_session = await setup(monkeypatch)

    # Load a CT entry from tests/resources/amazon/
    resource_dir = os.path.join(os.path.dirname(__file__), "resources", "amazon")
    files = [f for f in os.listdir(resource_dir) if f.endswith(".json")]
    assert files, "No test certificate files found in tests/resources/amazon/"
    resource_path = os.path.join(resource_dir, files[0])
    with open(resource_path, "r") as f:
        ct_entry_dict = json.load(f)

    # Prepare UploadCertItem
    payload = [
        UploadCertItem(
            log_name="dummy_log",
            worker_name="dummy_worker",
            ct_log_url="dummy_url",
            ct_index=1,
            ct_entry=json.dumps(ct_entry_dict)
        )
    ]

    # Call upload_certificates
    async with async_session() as session:
        result = await upload_certificates(payload, db=session)
        assert result["inserted"] == 1

        # Query the Cert table
        stmt = select(Cert).order_by(Cert.id.desc())
        cert_obj = (await session.execute(stmt)).scalars().first()
        assert cert_obj is not None
        print()
        print(f"cert_obj.ct_log_timestamp={cert_obj.ct_log_timestamp}")
        print(f"cert_obj.not_before={cert_obj.not_before}")
        print(f"cert_obj.issued_at_night={cert_obj.issued_at_night}")
        print(f"cert_obj.issued_on_weekend={cert_obj.issued_on_weekend}")
        assert cert_obj.ct_log_timestamp == datetime(2024, 12, 2, 0, 46, 8, 621000)
        assert cert_obj.not_before == datetime(2024, 12, 2, 0, 0)
        # Check that ct_log_timestamp and not_before are not equal
        assert cert_obj.ct_log_timestamp != cert_obj.not_before
        assert cert_obj.issued_at_night is False
        assert cert_obj.issued_on_weekend is False


async def setup(monkeypatch):
    # Setup in-memory SQLite DB
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    # Monkeypatch cert_cache to always return False for is_duplicate and do nothing for add
    class DummyCertCache:
        async def is_duplicate(self, *a, **kw): return False

        async def add(self, *a, **kw): return None

        async def get_stats(self): return {"hit_rate": 0, "cache_size": 0, "hit_count": 0, "miss_count": 0}

    monkeypatch.setattr("src.manager_api.certificate_cache.cert_cache", DummyCertCache())
    return async_session


@pytest.mark.asyncio
async def test_upload_cert_ct_log_timestamp__weekend(monkeypatch, tmp_path):
    async_session = await setup(monkeypatch)

    # Load a CT entry from tests/resources/amazon/
    resource_dir = os.path.join(os.path.dirname(__file__), "resources", "dv")
    files = [f for f in os.listdir(resource_dir) if f.endswith(".json")]
    assert files, "No test certificate files found in tests/resources/amazon/"
    resource_path = os.path.join(resource_dir, files[0])
    with open(resource_path, "r") as f:
        ct_entry_dict = json.load(f)

    # Prepare UploadCertItem
    payload = [
        UploadCertItem(
            log_name="dummy_log",
            worker_name="dummy_worker",
            ct_log_url="dummy_url",
            ct_index=1,
            ct_entry=json.dumps(ct_entry_dict)
        )
    ]

    # Call upload_certificates
    async with async_session() as session:
        result = await upload_certificates(payload, db=session)
        assert result["inserted"] == 1

        # Query the Cert table
        stmt = select(Cert).order_by(Cert.id.desc())
        cert_obj = (await session.execute(stmt)).scalars().first()
        assert cert_obj is not None
        print()
        print(f"cert_obj.ct_log_timestamp={cert_obj.ct_log_timestamp}")
        print(f"cert_obj.not_before={cert_obj.not_before}")
        print(f"cert_obj.issued_at_night={cert_obj.issued_at_night}")
        print(f"cert_obj.issued_on_weekend={cert_obj.issued_on_weekend}")
        assert cert_obj.issued_at_night is False
        assert cert_obj.issued_on_weekend is True






@pytest.mark.asyncio
async def test_upload_cert_ct_log_timestamp__night(monkeypatch, tmp_path):
    async_session = await setup(monkeypatch)

    # Load a CT entry from tests/resources/amazon/
    resource_dir = os.path.join(os.path.dirname(__file__), "resources", "night")
    files = [f for f in os.listdir(resource_dir) if f.endswith(".json")]
    assert files, "No test certificate files found in tests/resources/night/"
    resource_path = os.path.join(resource_dir, files[0])
    with open(resource_path, "r") as f:
        ct_entry_dict = json.load(f)

    # Prepare UploadCertItem
    payload = [
        UploadCertItem(
            log_name="dummy_log",
            worker_name="dummy_worker",
            ct_log_url="dummy_url",
            ct_index=1,
            ct_entry=json.dumps(ct_entry_dict)
        )
    ]

    # Call upload_certificates
    async with async_session() as session:
        result = await upload_certificates(payload, db=session)
        assert result["inserted"] == 1

        # Query the Cert table
        stmt = select(Cert).order_by(Cert.id.desc())
        cert_obj = (await session.execute(stmt)).scalars().first()
        assert cert_obj is not None
        print()
        print(f"cert_obj.ct_log_timestamp={cert_obj.ct_log_timestamp}")
        print(f"cert_obj.not_before={cert_obj.not_before}")
        print(f"cert_obj.issued_at_night={cert_obj.issued_at_night}")
        print(f"cert_obj.issued_on_weekend={cert_obj.issued_on_weekend}")
        assert cert_obj.issued_at_night is True
        assert cert_obj.issued_on_weekend is False
