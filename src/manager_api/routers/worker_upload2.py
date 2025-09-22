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
from src.manager_api.models import Cert2
from src.share.cert_parser2 import JPCertificateParser2
from typing import List
from src.manager_api.base_models import UploadCertItem, UploadResponse
import datetime as dt
from src.share.logger import logger

router = APIRouter()

@router.post("/api/worker/upload2")
async def upload_certificates2(
    items: List[UploadCertItem],
    db=Depends(get_async_session)
):
    logger.debug(f"[upload_certificates2] Received {len(items)} items for upload")
    inserted = 0
    skipped_duplicates = 0
    parser = JPCertificateParser2()

    # List for batch processing
    certs_to_insert = []

    for item in items:
        # Extract only .jp certificates using cert_parser2
        try:
            entry_dict = json.loads(item.ct_entry)
            cert_data = parser.parse_only_jp_cert_to_cert2(entry_dict)
        except Exception as e:
            logger.debug(f"[upload_certificates2] Error parsing CT entry for item: {item} *{e}")
            continue
        if not cert_data:
            continue

        # Get values for duplicate check
        issuer = cert_data.issuer
        serial_number = cert_data.serial_number
        certificate_fingerprint_sha256 = cert_data.certificate_fingerprint_sha256

        # Fast duplicate check with memory cache
        dup = await cert_cache.is_duplicate(issuer, serial_number, certificate_fingerprint_sha256)
        if dup:
            skipped_duplicates += 1
            continue  # Skip duplicates (no DB query)

        # Map to all fields of Cert2 model
        cert = Cert2(
            serial_number=serial_number,
            issuer=issuer,
            not_before=cert_data.not_before,
            not_after=cert_data.not_after,
            common_name=cert_data.common_name,
            subject_alternative_names=cert_data.subject_alternative_names,
            san_count=cert_data.san_count,
            certificate_fingerprint_sha256=certificate_fingerprint_sha256,
            public_key_algorithm=cert_data.public_key_algorithm,
            key_size=cert_data.key_size,
            signature_algorithm=cert_data.signature_algorithm,
            ct_log_timestamp=cert_data.ct_log_timestamp,
            has_crl_urls=cert_data.has_crl_urls,
            has_ocsp_urls=cert_data.has_ocsp_urls,
            issued_on_weekend=cert_data.issued_on_weekend,
            issued_at_night=cert_data.issued_at_night,
            organization_type=cert_data.organization_type,
            is_wildcard=cert_data.is_wildcard,
            subject_public_key_hash=cert_data.subject_public_key_hash,
            is_precertificate=cert_data.is_precertificate,
            vetting_level=cert_data.vetting_level,
            # Issuer components
            issuer_cn=cert_data.issuer_cn,
            issuer_o=cert_data.issuer_o,
            issuer_ou=cert_data.issuer_ou,
            issuer_c=cert_data.issuer_c,
            issuer_st=cert_data.issuer_st,
            issuer_l=cert_data.issuer_l,
            issuer_email=cert_data.issuer_email,
            issuer_dc=cert_data.issuer_dc,
            # Root issuer components
            root_issuer=cert_data.root_issuer,
            root_issuer_cn=cert_data.root_issuer_cn,
            root_issuer_o=cert_data.root_issuer_o,
            root_issuer_ou=cert_data.root_issuer_ou,
            root_issuer_c=cert_data.root_issuer_c,
            root_issuer_st=cert_data.root_issuer_st,
            root_issuer_l=cert_data.root_issuer_l,
            root_issuer_email=cert_data.root_issuer_email,
            root_issuer_dc=cert_data.root_issuer_dc
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

            logger.debug(f"[upload_certificates2] Batch insert successful: {inserted} certs")

        except IntegrityError as e:
            # On duplicate error, process one by one
            logger.debug(f"[upload_certificates2] Batch insert failed due to duplicates, falling back to individual inserts. {e}")
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
        logger.debug(f"[upload_certificates2] Cache stats: hit_rate={cache_stats['hit_rate']:.2%}, "
                    f"size={cache_stats['cache_size']}, hits={cache_stats['hit_count']}, "
                    f"misses={cache_stats['miss_count']}")

    logger.debug(f"[upload_certificates2] Result: inserted={inserted}, skipped_duplicates={skipped_duplicates}")
    return UploadResponse(inserted=inserted, skipped_duplicates=skipped_duplicates)


async def save_failed(e, items):
    # Save request to pending/upload_failure as JSON
    os.makedirs("pending/upload_failure", exist_ok=True)
    now = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    rand = random.randint(1000, 9999)
    filename = f"pending/upload_failure/upload_failure2_{now}_{rand}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump([item.dict() for item in items], f, ensure_ascii=False, indent=2)
    logger.error(
        f"[CRITICAL:upload_certificates2] Failed to store certs. Saved request to {filename}. Please run scripts/upload_pending_failure.sh to retry. Error: {e}")
