import json
import logging
import os
import random
from datetime import datetime
from fastapi import Query, Depends, APIRouter
from sqlalchemy.exc import IntegrityError
from src.manager_api.certificate_cache import cert_cache
from src.config import JST, BATCH_SIZE
from src.manager_api.db import get_async_session
from src.manager_api import locks
from src.manager_api.models import Cert
from src.share.cert_parser import JPCertificateParser
from typing import List
from src.manager_api.base_models import UploadCertItem, UploadResponse
import datetime as dt
from src.share.logger import logger

router = APIRouter()

@router.post("/api/worker/upload")
async def upload_certificates(
    items: List[UploadCertItem],
    db=Depends(get_async_session)
) -> UploadResponse:
    logger.debug(f"[upload_certificates] Received {len(items)} items for upload")
    inserted = 0
    skipped_duplicates = 0
    parser = JPCertificateParser()

    # List for batch processing
    certs_to_insert = []

    for item in items:
        # Extract only .jp certificates
        try:
            entry_dict = json.loads(item.ct_entry)
            cert_data = parser.parse_only_jp_cert(entry_dict)
        except Exception as e:
            logger.debug(f"[upload_certificates] Error parsing CT entry for item: {item}")
            continue
        if not cert_data:
            continue

        # Get values for duplicate check
        issuer = cert_data.get('issuer')
        serial_number = cert_data.get('serial_number')
        certificate_fingerprint_sha256 = cert_data.get('certificate_fingerprint_sha256')

        # Fast duplicate check with memory cache
        dup = await cert_cache.is_duplicate(issuer, serial_number, certificate_fingerprint_sha256)
        if dup:
            skipped_duplicates += 1
            continue  # Skip duplicates (no DB query)

        # Map to all fields of Cert model
        cert = Cert(
            serial_number=serial_number,
            issuer=issuer,
            not_before=cert_data.get('not_before'),
            not_after=cert_data.get('not_after'),
            common_name=cert_data.get('subject_common_name'),
            subject_alternative_names=cert_data.get('subject_alternative_names'),
            san_count=cert_data.get('san_count'),
            certificate_fingerprint_sha256=certificate_fingerprint_sha256,
            public_key_algorithm=cert_data.get('public_key_algorithm'),
            key_size=cert_data.get('key_size'),
            signature_algorithm=cert_data.get('signature_algorithm'),
            ct_log_timestamp=cert_data.get('ct_log_timestamp'),
            crl_urls=cert_data.get('crl_urls'),
            ocsp_urls=cert_data.get('ocsp_urls'),
            issued_on_weekend=cert_data.get('issued_on_weekend'),
            issued_at_night=cert_data.get('issued_at_night'),
            organization_type=cert_data.get('organization_type'),
            is_wildcard=cert_data.get('is_wildcard'),
            root_ca_issuer_name=cert_data.get('root_ca_issuer_name'),
            subject_public_key_hash=cert_data.get('subject_public_key_hash'),
            log_name=item.log_name,
            worker_name=item.worker_name,
            ct_log_url=item.ct_log_url,
            created_at=datetime.now(JST),
            ct_index=item.ct_index,
            ct_entry=item.ct_entry,
            is_precertificate=cert_data.get('is_precertificate'),
            vetting_level=cert_data.get('vetting_level')
        )
        certs_to_insert.append(cert)

    # Batch INSERT (prevent duplicates with DB constraints)
    if certs_to_insert:
        try:
            # Try batch insert
            db.add_all(certs_to_insert)
            await db.commit()
            inserted = len(certs_to_insert)

            # Register successfully inserted certificates in cache
            for cert in certs_to_insert:
                await cert_cache.add(cert.issuer, cert.serial_number, cert.certificate_fingerprint_sha256)

            logger.debug(f"[upload_certificates] Batch insert successful: {inserted} certs")

        except IntegrityError as e:
            # On duplicate error, process one by one
            logger.debug(f"[upload_certificates] Batch insert failed due to duplicates, falling back to individual inserts")
            await db.rollback()
            for cert in certs_to_insert:
                try:
                    db.add(cert)
                    await db.commit()
                    inserted += 1
                    # Register in cache only on success
                    await cert_cache.add(cert.issuer, cert.serial_number, cert.certificate_fingerprint_sha256)
                except IntegrityError as e:
                    # Duplicate error (if unique index exists)
                    await db.rollback()
                    skipped_duplicates += 1
                    await save_failed(e, items)
                    # Add to cache as duplicate (for skipping next time)
                    await cert_cache.add(cert.issuer, cert.serial_number, cert.certificate_fingerprint_sha256)
        except Exception as e:
            await save_failed(e, items)
            return UploadResponse(inserted=0, skipped_duplicates=0)

    # Output cache statistics to log (for debugging)
    if logger.isEnabledFor(logging.DEBUG):
        cache_stats = await cert_cache.get_stats()
        logger.debug(f"[upload_certificates] Cache stats: hit_rate={cache_stats['hit_rate']:.2%}, "
                    f"size={cache_stats['cache_size']}, hits={cache_stats['hit_count']}, "
                    f"misses={cache_stats['miss_count']}")

    logger.debug(f"[upload_certificates] Result: inserted={inserted}, skipped_duplicates={skipped_duplicates}")
    return UploadResponse(inserted=inserted, skipped_duplicates=skipped_duplicates)


async def save_failed(e, items):
    # Save request to pending/upload_failure as JSON
    os.makedirs("pending/upload_failure", exist_ok=True)
    now = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    rand = random.randint(1000, 9999)
    filename = f"pending/upload_failure/upload_failure_{now}_{rand}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump([item.dict() for item in items], f, ensure_ascii=False, indent=2)
    logger.error(
        f"[CRITICAL:upload_certificates] Failed to store certs. Saved request to {filename}. Please run scripts/upload_pending_failure.sh to retry. Error: {e}")
