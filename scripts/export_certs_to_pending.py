#!/usr/bin/env python3
"""
Script to export MySQL "certs" table data in batches of 32 records
and save them as JSON files in "pending/upload_failure/" directory.
After successful save, the processed records are deleted from the database.
"""

import os
import sys
import json
import asyncio
from typing import List
from pathlib import Path

# Add the src directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from src.manager_api.db import get_async_session, init_engine
from src.manager_api.models import Cert
from src.manager_api.base_models import UploadCertItem
from pydantic import BaseModel

BATCH_SIZE = 32
SLEEP_INTERVAL = 1.5  # seconds
OUTPUT_DIR = "pending/upload_failure"

class CertBatchResponse(BaseModel):
    """Pydantic model for cert batch response."""
    cert_items: List[UploadCertItem]
    record_ids: List[int]
    min_id: int
    max_id: int

class CertExporter:
    def __init__(self):
        self.output_dir = Path(OUTPUT_DIR)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.last_processed_id = 0  # Track the last processed ID
        init_engine()

    async def get_cert_batch(self, session: AsyncSession) -> CertBatchResponse | None:
        """Fetch a batch of certificates from the database."""
        # Query to get only the necessary fields for JSON output and ID for deletion
        # Filter by ID greater than the last processed ID to avoid duplicates
        query = select(
            Cert.id,
            Cert.ct_entry,
            Cert.ct_log_url,
            Cert.log_name,
            Cert.worker_name,
            Cert.ct_index
        ).where(Cert.id > self.last_processed_id).order_by(Cert.id.asc()).limit(BATCH_SIZE)

        result = await session.execute(query)
        rows = result.fetchall()

        if not rows:
            return None

        # Convert to Pydantic models
        cert_items = []
        record_ids = []

        for row in rows:
            cert_item = UploadCertItem(
                ct_entry=row.ct_entry,
                ct_log_url=row.ct_log_url,
                log_name=row.log_name,
                worker_name=row.worker_name,
                ct_index=row.ct_index
            )
            cert_items.append(cert_item)
            record_ids.append(row.id)

        batch_response = CertBatchResponse(
            cert_items=cert_items,
            record_ids=record_ids,
            min_id=min(record_ids),
            max_id=max(record_ids)
        )

        # Update the last processed ID to prevent selecting the same records again
        self.last_processed_id = batch_response.max_id

        return batch_response

    async def delete_processed_records(self, session: AsyncSession, record_ids: List[int]) -> bool:
        """Delete the processed records from the database."""
        try:
            if not record_ids:
                return True

            # Use SQLAlchemy ORM delete with Cert model
            query = delete(Cert).where(Cert.id.in_(record_ids))

            await session.execute(query)
            await session.commit()

            print(f"Deleted {len(record_ids)} records from database: IDs {record_ids}")
            return True

        except Exception as e:
            print(f"Error deleting records: {e}")
            await session.rollback()
            return False

    def generate_filename(self, min_id: int, max_id: int) -> str:
        """Generate a filename using cert table IDs."""
        return f"upload_failure2_20250923_certs_model_{min_id}_to_{max_id}.json"

    def save_batch_to_file(self, batch_response: CertBatchResponse) -> bool:
        """Save the batch data to a JSON file using atomic write operation."""
        try:
            filename = self.generate_filename(batch_response.min_id, batch_response.max_id)
            filepath = self.output_dir / filename
            temp_filepath = filepath.with_suffix('.tmp')

            # Convert Pydantic models to dict for JSON serialization
            batch_data = [item.dict() for item in batch_response.cert_items]

            # Write to temporary file first
            with open(temp_filepath, 'w', encoding='utf-8') as f:
                json.dump(batch_data, f, indent=2, ensure_ascii=False)

            # Atomic rename operation - this prevents race conditions
            temp_filepath.rename(filepath)

            print(f"Saved {len(batch_data)} records to {filepath}")
            return True

        except Exception as e:
            print(f"Error saving batch to file: {e}")
            # Clean up temporary file if it exists
            try:
                if 'temp_filepath' in locals() and temp_filepath.exists():
                    temp_filepath.unlink()
            except:
                pass
            return False

    async def export_batch(self, session: AsyncSession) -> bool:
        """Export one batch of certificates."""
        try:
            # Fetch batch data
            batch_response = await self.get_cert_batch(session)
            if not batch_response:
                print("No more records to process")
                return False

            # Save to file
            if not self.save_batch_to_file(batch_response):
                print("Failed to save batch to file, skipping deletion")
                return False

            # Delete processed records
            if not await self.delete_processed_records(session, batch_response.record_ids):
                print("Failed to delete processed records")
                return False

            print(f"Success: batch of {len(batch_response.cert_items)} records (IDs {batch_response.min_id}-{batch_response.max_id})")
            return True

        except Exception as e:
            print(f"Error in export_batch: {e}")
            await session.rollback()
            return False

    async def run(self):
        """Main export loop."""
        print(f"Starting certificate export to {self.output_dir}")
        print(f"Batch size: {BATCH_SIZE}, Sleep interval: {SLEEP_INTERVAL}s")

        batch_count = 0
        total_exported = 0

        while True:
            try:
                # Use async session management
                async for session in get_async_session():
                    # Export one batch with the session
                    success = await self.export_batch(session)

                    if not success:
                        print("Export completed - no more records to process")
                        return

                    batch_count += 1
                    total_exported += BATCH_SIZE

                    print(f"Completed batch {batch_count}, total exported: {total_exported}. Sleeping for {SLEEP_INTERVAL} sec...")

                    await asyncio.sleep(SLEEP_INTERVAL)

            except KeyboardInterrupt:
                print("\nExport interrupted by user")
                break
            except Exception as e:
                print(f"Unexpected error in main loop: {e}")
                print(f"Sleeping for {SLEEP_INTERVAL} seconds before retrying...")
                await asyncio.sleep(SLEEP_INTERVAL)

        print(f"Export completed. Total batches: {batch_count}, Total records: {total_exported}")

async def main():
    """Main entry point."""
    exporter = CertExporter()
    await exporter.run()

if __name__ == "__main__":
    asyncio.run(main())
