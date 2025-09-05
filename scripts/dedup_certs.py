"""
Certs table has many duplicates and processing has become heavy, so this script deletes duplicates.
Deletes records with the same combination of issuer, serial_number, and certificate_fingerprint_sha256.
"""
#!/usr/bin/env python3
import sys
import os
import time
import asyncio

# Add path to import src/manager_api/db.py and models.py
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.manager_api.db import get_async_session
from src.manager_api.models import Cert
from sqlalchemy import delete

def get_state_path():
    return os.path.join(os.path.dirname(__file__), "dedup_certs.state")

async def main():
    batch_size = 500
    start_id = 1
    print(f"Processing certs.id from {start_id} in batches of {batch_size} (LIMIT)")
    async for session in get_async_session():
        while True:
            start_time = time.time()
            result = await session.execute(
                Cert.__table__.select()
                .with_only_columns(
                    Cert.id, Cert.issuer, Cert.serial_number, Cert.certificate_fingerprint_sha256
                )
                .where(Cert.id >= start_id)
                .order_by(Cert.id)
                .limit(batch_size)
            )
            certs = result.fetchall()
            if not certs:
                print("No more records to process.")
                break
            seen = set()
            ids_to_delete = []
            for cert_id, issuer, serial_number, fingerprint in certs:
                key = (issuer, serial_number, fingerprint)
                if key in seen:
                    ids_to_delete.append(cert_id)
                    print(f"Deleted id={cert_id} key={key}")
                else:
                    seen.add(key)
            if ids_to_delete:
                await session.execute(
                    delete(Cert).where(Cert.id.in_(ids_to_delete))
                )
                await session.commit()
            end_id = certs[-1][0]
            elapsed = time.time() - start_time
            print(f"Processed id {start_id}-{end_id} (elapsed: {elapsed:.2f} sec)")
            start_id = end_id + 1
        print("Deduplication finished.")

if __name__ == "__main__":
    asyncio.run(main())
