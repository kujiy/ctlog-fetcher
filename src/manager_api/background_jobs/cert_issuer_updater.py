import asyncio
import json
import os
from src.manager_api.db import get_async_session
from src.manager_api.models import Cert
from sqlalchemy import select, func, delete
from sqlalchemy.orm import sessionmaker
from src.share.logger import logger
from src.share.cert_parser import JPCertificateParser

BATCH_SIZE = 128
SLEEP_SEC = 0.3
PROGRESS_FILE = "cert_issuer_progress.txt"

class CertIssuerUpdater:
    def __init__(self):
        self.parser = JPCertificateParser()
        self.last_processed_id = 0

    async def load_progress(self):
        """Load the last processed ID from local file or start from 0"""
        try:
            if os.path.exists(PROGRESS_FILE):
                with open(PROGRESS_FILE, 'r') as f:
                    self.last_processed_id = int(f.read().strip())
                logger.info(f"8️⃣ Loaded progress from file: {self.last_processed_id}")
            else:
                self.last_processed_id = 0
                logger.info(f"8️⃣ Starting from ID: {self.last_processed_id} (no progress file found)")
        except Exception as e:
            logger.warning(f"8️⃣ Failed to load progress from file: {e}, starting from 0")
            self.last_processed_id = 0

    async def save_progress(self):
        """Save the current progress to local file"""
        try:
            with open(PROGRESS_FILE, 'w') as f:
                f.write(str(self.last_processed_id))
        except Exception as e:
            logger.warning(f"8️⃣ Failed to save progress to file: {e}")

    async def process_certificates_individually(self):
        """Process certificates one by one: update issuer, then remove duplicates for that certificate"""
        logger.info("8️⃣ - process_certificates_individually started")

        await self.load_progress()

        async for session in get_async_session():
            while True:
                # Fetch next batch of certificates that need processing
                result = await session.execute(
                    select(Cert.id, Cert.ct_entry, Cert.issuer, Cert.serial_number, Cert.certificate_fingerprint_sha256)
                    .where(Cert.id > self.last_processed_id)
                    .where(Cert.ct_entry.isnot(None))
                    .order_by(Cert.id.asc())
                    .limit(BATCH_SIZE)
                )
                rows = result.fetchall()

                if not rows:
                    logger.info("8️⃣ No more certificates to process")
                    break

                # Track processed certificates in this batch to avoid duplicate deletion issues
                processed_in_batch = set()
                processed_count = 0
                
                for row in rows:
                    # Skip if this certificate was already deleted in this batch
                    if row.id in processed_in_batch:
                        continue
                        
                    try:
                        # Step 1: Update issuer field by parsing ct_entry
                        updated_issuer = None
                        if row.ct_entry:
                            ct_entry_data = json.loads(row.ct_entry)
                            cert_data = self.parser.parse_ct_entry_to_certificate_data(ct_entry_data)

                            if cert_data and cert_data.get('issuer'):
                                # Update only the issuer field
                                await session.execute(
                                    Cert.__table__.update()
                                    .where(Cert.id == row.id)
                                    .values(issuer=cert_data['issuer'])
                                )
                                updated_issuer = cert_data['issuer']
                                await session.commit()

                        # Step 2: Remove duplicates for this specific certificate
                        # Use the updated issuer if available, otherwise use existing issuer
                        current_issuer = updated_issuer or row.issuer
                        current_serial = row.serial_number
                        current_fingerprint = row.certificate_fingerprint_sha256

                        if current_issuer and len(current_issuer) >= 10 and current_serial and current_fingerprint:
                            # Find all certificates with the same issuer, serial_number, and fingerprint
                            # Exclude certificates that have already been processed in this batch
                            duplicate_result = await session.execute(
                                select(Cert.id)
                                .where(
                                    Cert.issuer == current_issuer,
                                    Cert.serial_number == current_serial,
                                    Cert.certificate_fingerprint_sha256 == current_fingerprint,
                                    Cert.id > row.id  # Only look for duplicates with higher IDs to avoid deleting the current one
                                )
                                .order_by(Cert.id.asc())
                            )
                            duplicate_ids = [dup_row.id for dup_row in duplicate_result.fetchall()]

                            # Delete duplicates if any found
                            if duplicate_ids:
                                delete_result = await session.execute(
                                    delete(Cert).where(Cert.id.in_(duplicate_ids))
                                )
                                deleted_count = delete_result.rowcount
                                if deleted_count > 0:
                                    logger.info(f"8️⃣ Deleted {deleted_count} duplicates for cert ID {row.id}")
                                    # Mark deleted IDs as processed to avoid processing them later in this batch
                                    processed_in_batch.update(duplicate_ids)
                                await session.commit()

                        # Mark this certificate as processed
                        processed_in_batch.add(row.id)
                        processed_count += 1

                    except Exception as e:
                        logger.warning(f"8️⃣ Failed to process cert ID {row.id}: {e}")
                        continue

                self.last_processed_id = rows[-1].id
                await self.save_progress()  # Save progress after each batch
                logger.info(f"8️⃣ Processed {processed_count} certificates up to ID {self.last_processed_id}")

                # Sleep to avoid overwhelming the database
                await asyncio.sleep(SLEEP_SEC)

            # Break out of the async for loop
            break

async def cert_issuer_update_job():
    """Main job function that processes certificates individually"""
    logger.info("8️⃣ - cert_issuer_update_job started")

    updater = CertIssuerUpdater()

    # Process each certificate: update issuer, then remove duplicates for that certificate
    await updater.process_certificates_individually()

    logger.info("8️⃣ - cert_issuer_update_job completed")

async def cert_issuer_job_wrapper():
    """Wrapper that runs the job continuously"""
    logger.info("8️⃣ - cert_issuer_job_wrapper started")

    while True:
        try:
            await cert_issuer_update_job()
            logger.info("8️⃣ - cert_issuer_job_wrapper: sleep 3 minutes")
            await asyncio.sleep(60 * 3)  # 3 minutes
        except Exception as e:
            logger.error(f"❌8️⃣ - cert_issuer_job_wrapper error: {e}")
            logger.info("8️⃣ - cert_issuer_job_wrapper: sleep 5 minutes after error")
            await asyncio.sleep(60 * 5)  # 5 minutes on error

def start_cert_issuer_updater():
    """Start the cert issuer updater background job"""
    logger.info("8️⃣ [cert_issuer_updater] Started cert issuer updater background job")
    return asyncio.create_task(cert_issuer_job_wrapper())

if __name__ == "__main__":
    asyncio.run(cert_issuer_update_job())
