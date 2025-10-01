import datetime as dt
import json
import logging
import os
import random
from typing import List

from fastapi import Depends, APIRouter
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.mysql import insert

from src.manager_api.base_models import UploadCertItem, UploadResponse
from src.manager_api.certificate_cache import cert_cache
from src.manager_api.db import get_async_session
from src.manager_api.models import Cert2
from src.share.cert_parser2 import JPCertificateParser2
from src.share.logger import logger

router = APIRouter()


@router.post("/api/worker/upload2")
async def upload_certificates2(
    items: List[UploadCertItem],
    db: AsyncSession = Depends(get_async_session)
):
    logger.debug(f"[upload_certificates2] Received {len(items)} items for upload")
    inserted = 0
    skipped_duplicates = 0
    parser = JPCertificateParser2()

    # List for batch processing
    cert_dicts = []

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

        # Create a dictionary that perfectly matches the fields of the Cert2 table
        cert_dict = {
            # Basic certificate information
            'common_name': cert_data.common_name,
            'ct_log_timestamp': cert_data.ct_log_timestamp,
            'not_before': cert_data.not_before,
            'not_after': cert_data.not_after,
            'issuer': cert_data.issuer,
            'vetting_level': cert_data.vetting_level,
            'issued_on_weekend': cert_data.issued_on_weekend,
            'issued_at_night': cert_data.issued_at_night,
            'organization_type': cert_data.organization_type,
            'is_wildcard': cert_data.is_wildcard,
            'is_precertificate': cert_data.is_precertificate,
            'san_count': cert_data.san_count,
            'subject_alternative_names': cert_data.subject_alternative_names,
            
            # Relative fields (not used in cert_parser2, set to None)
            'is_automated_renewal': None,
            'days_before_expiry': None,
            'issued_after_expiry': None,
            'reuse_subject_public_key_hash': None,
            
            # URL indicators
            'has_crl_urls': cert_data.has_crl_urls,
            'has_ocsp_urls': cert_data.has_ocsp_urls,
            
            # Issuer components
            'issuer_cn': cert_data.issuer_cn,
            'issuer_o': cert_data.issuer_o,
            'issuer_ou': cert_data.issuer_ou,
            'issuer_c': cert_data.issuer_c,
            'issuer_st': cert_data.issuer_st,
            'issuer_l': cert_data.issuer_l,
            
            # Subject components
            'subject': cert_data.subject,
            'subject_cn': cert_data.subject_cn,
            'subject_o': cert_data.subject_o,
            'subject_ou': cert_data.subject_ou,
            'subject_c': cert_data.subject_c,
            'subject_st': cert_data.subject_st,
            'subject_l': cert_data.subject_l,
            
            # Unique certificate identification
            'serial_number': cert_data.serial_number,
            'certificate_fingerprint_sha256': cert_data.certificate_fingerprint_sha256,
            'subject_public_key_hash': cert_data.subject_public_key_hash,
            'public_key_algorithm': cert_data.public_key_algorithm,
            'key_size': cert_data.key_size,
            'signature_algorithm': cert_data.signature_algorithm,
            
            # Technical information
            'authority_key_identifier': cert_data.authority_key_identifier,
            'subject_key_identifier': cert_data.subject_key_identifier,
            
            # CT log related fields
            'log_name': item.log_name,
            'ct_index': item.ct_index,
            'worker_name': item.worker_name,
            'created_at': dt.datetime.now(),
            'ct_entry': item.ct_entry
        }
        cert_dicts.append(cert_dict)

    # Batch INSERT with INSERT IGNORE (prevents deadlocks)
    if cert_dicts:
        try:
            stmt = insert(Cert2).values(cert_dicts)
            stmt = stmt.prefix_with('IGNORE')
            result = await db.execute(stmt)
            await db.commit()

            inserted = result.rowcount
            skipped_duplicates += len(cert_dicts) - inserted

            # キャッシュに追加
            for cert_dict in cert_dicts:
                await cert_cache.add(cert_dict['issuer'], cert_dict['serial_number'], cert_dict['certificate_fingerprint_sha256'])

            logger.debug(f"🐕 [upload_certificates2] INSERT IGNORE successful: inserted={inserted}, skipped={skipped_duplicates}")

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


async def save_failed(e: Exception, items: List[UploadCertItem]):
    # Save request to pending/upload_failure as JSON
    os.makedirs("pending/upload_failure", exist_ok=True)
    now = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    rand = random.randint(1000, 9999)
    filename = f"pending/upload_failure/upload_failure2_{now}_{rand}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump([item.dict() for item in items], f, ensure_ascii=False, indent=2)
    logger.error(
        f"[CRITICAL:upload_certificates2] Failed to store certs. Saved request to {filename}. Please run scripts/upload_pending_failure.sh to retry. Error: {e}")
