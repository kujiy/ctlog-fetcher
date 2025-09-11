import asyncio
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from src.manager_api.models import Cert, UniqueCert
from src.manager_api.db import get_async_session
from src.share.logger import logger
from src.config import JST

_last_processed_cert_id = None
_processing_lock = asyncio.Lock()

async def get_last_processed_cert_id(session):
    global _last_processed_cert_id

    if _last_processed_cert_id is None:
        # On first startup: estimate the maximum cert ID from the unique_certs table
        # Since cert.id is not directly stored in unique_certs, estimate using created_at
        last_unique_cert = (await session.execute(
            select(UniqueCert).order_by(UniqueCert.id.desc()).limit(1)
        )).scalars().first()
        if last_unique_cert:
            last_cert = (await session.execute(
                select(Cert).where(Cert.created_at <= last_unique_cert.created_at).order_by(Cert.id.desc()).limit(1)
            )).scalars().first()
            _last_processed_cert_id = last_cert.id if last_cert else 0
        else:
            _last_processed_cert_id = 0

    return _last_processed_cert_id

def update_last_processed_cert_id(cert_id: int):
    global _last_processed_cert_id
    _last_processed_cert_id = cert_id

async def update_unique_certs():
    logger.info("🥑 unique_certs_updater: Starting update process")
    async with _processing_lock:
        async for session in get_async_session():
            try:
                last_processed_id = await get_last_processed_cert_id(session)
                batch_size = 100
                new_certs = (await session.execute(
                    select(Cert).where(Cert.id > last_processed_id).order_by(Cert.id.asc()).limit(batch_size)
                )).scalars().all()

                if not new_certs:
                    logger.debug("🥑 unique_certs_updater: No new certificates to process")
                    return

                inserted = 0
                skipped_duplicates = 0
                successfully_processed_ids = []

                unique_certs_to_insert = []
                cert_id_mapping = {}

                for cert in new_certs:
                    existing = (await session.execute(
                        select(UniqueCert).where(
                            (UniqueCert.issuer == cert.issuer) &
                            (UniqueCert.serial_number == cert.serial_number)
                        )
                    )).scalars().first()

                    if existing:
                        skipped_duplicates += 1
                        successfully_processed_ids.append(cert.id)
                        continue

                    unique_cert = UniqueCert(
                        issuer=cert.issuer,
                        common_name=cert.common_name,
                        not_before=cert.not_before,
                        not_after=cert.not_after,
                        serial_number=cert.serial_number,
                        subject_alternative_names=cert.subject_alternative_names,
                        certificate_fingerprint_sha256=cert.certificate_fingerprint_sha256,
                        subject_public_key_hash=cert.subject_public_key_hash,
                        public_key_algorithm=cert.public_key_algorithm,
                        key_size=cert.key_size,
                        signature_algorithm=cert.signature_algorithm,
                        ct_log_timestamp=cert.ct_log_timestamp,
                        crl_urls=cert.crl_urls,
                        ocsp_urls=cert.ocsp_urls,
                        vetting_level=cert.vetting_level,
                        san_count=cert.san_count,
                        issued_on_weekend=cert.issued_on_weekend,
                        issued_at_night=cert.issued_at_night,
                        organization_type=cert.organization_type,
                        is_wildcard=cert.is_wildcard,
                        root_ca_issuer_name=cert.root_ca_issuer_name,
                        is_precertificate=cert.is_precertificate,
                        log_name=cert.log_name,
                        ct_index=cert.ct_index,
                        ct_log_url=cert.ct_log_url,
                        worker_name=cert.worker_name,
                        created_at=cert.created_at,
                        ct_entry=cert.ct_entry,
                        inserted_at=datetime.now(JST)
                    )
                    unique_certs_to_insert.append(unique_cert)
                    cert_id_mapping[unique_cert] = cert.id

                if unique_certs_to_insert:
                    try:
                        session.add_all(unique_certs_to_insert)
                        await session.commit()
                        inserted = len(unique_certs_to_insert)
                        successfully_processed_ids.extend(cert_id_mapping.values())
                    except Exception as e:
                        await session.rollback()
                        logger.debug(f"Batch insert failed (expected for duplicates), falling back to individual inserts: {e}")

                        for unique_cert in unique_certs_to_insert:
                            try:
                                session.add(unique_cert)
                                await session.commit()
                                inserted += 1
                                successfully_processed_ids.append(cert_id_mapping[unique_cert])
                            except Exception as individual_error:
                                await session.rollback()
                                skipped_duplicates += 1
                                if skipped_duplicates <= 10:
                                    logger.debug(f"Skipped duplicate cert: issuer={unique_cert.issuer}, serial={unique_cert.serial_number}")

                if new_certs:
                    max_batch_id = max(cert.id for cert in new_certs)
                    update_last_processed_cert_id(max_batch_id)
                    current_last_processed_id = max_batch_id
                else:
                    current_last_processed_id = last_processed_id

                logger.info(f"🥑 unique_certs_updater: processed {len(new_certs)} certs, inserted: {inserted}, skipped_duplicates: {skipped_duplicates}, last_processed_id: {current_last_processed_id}")

            except Exception as e:
                logger.error(f"🥑 unique_certs_updater error: {e}")
                await session.rollback()
                if 'new_certs' in locals() and new_certs:
                    try:
                        max_batch_id = max(cert.id for cert in new_certs)
                        update_last_processed_cert_id(max_batch_id)
                        logger.info(f"🥑 unique_certs_updater: Exception occurred, but saved progress to ID {max_batch_id}")
                    except Exception as progress_error:
                        logger.error(f"🥑 unique_certs_updater: Failed to save progress after exception: {progress_error}")

async def unique_certs_updater_job():
    while True:
        try:
            await update_unique_certs()
        except Exception as e:
            logger.error(f"[unique_certs_updater] Unexpected error: {e}")
        await asyncio.sleep(60)

def start_unique_certs_updater():
    asyncio.create_task(unique_certs_updater_job())
    logger.info("🥑 unique_certs_updater background job started (1min interval)")

if __name__ == "__main__":
    asyncio.run(unique_certs_updater_job())
