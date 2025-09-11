from fastapi import Depends, APIRouter
from src.manager_api.models import Cert
from sqlalchemy import select
from src.manager_api.db import get_async_session

router = APIRouter()



# --- Unique Certs API ---
@router.get("/api/unique_certs")
async def get_unique_certs(db=Depends(get_async_session)):
    stmt = select(Cert).order_by(Cert.id.desc()).limit(100)
    certs = (await db.execute(stmt)).scalars().all()

    result = []
    for cert in certs:
        result.append({
            "id": cert.id,
            "issuer": cert.issuer,
            "common_name": cert.common_name,
            "not_before": cert.not_before.isoformat() if cert.not_before else None,
            "not_after": cert.not_after.isoformat() if cert.not_after else None,
            "serial_number": cert.serial_number,
            "subject_alternative_names": cert.subject_alternative_names,
            "certificate_fingerprint_sha256": cert.certificate_fingerprint_sha256,
            "subject_public_key_hash": cert.subject_public_key_hash,
            "public_key_algorithm": cert.public_key_algorithm,
            "key_size": cert.key_size,
            "signature_algorithm": cert.signature_algorithm,
            "ct_log_timestamp": cert.ct_log_timestamp,
            "crl_urls": cert.crl_urls,
            "ocsp_urls": cert.ocsp_urls,
            "vetting_level": cert.vetting_level,
            "san_count": cert.san_count,
            "issued_on_weekend": cert.issued_on_weekend,
            "issued_at_night": cert.issued_at_night,
            "organization_type": cert.organization_type,
            "is_wildcard": cert.is_wildcard,
            "root_ca_issuer_name": cert.root_ca_issuer_name,
            "is_precertificate": cert.is_precertificate,
            "log_name": cert.log_name,
            "ct_index": cert.ct_index,
            "ct_log_url": cert.ct_log_url,
            "worker_name": cert.worker_name,
            "created_at": cert.created_at.isoformat() if cert.created_at else None,
            "ct_entry": cert.ct_entry,
        })

    return {
        "count": len(result),
        "unique_certs": result
    }





# --- Fetched Certs by Worker API ---
@router.get("/api/fetched_certs/{worker_name}")
async def get_fetched_certs_by_worker(worker_name: str, db=Depends(get_async_session)):
    stmt = select(Cert).where(Cert.worker_name == worker_name).order_by(Cert.id.desc()).limit(100)
    certs = (await db.execute(stmt)).scalars().all()

    result = []
    for cert in certs:
        result.append({
            "id": cert.id,
            "issuer": cert.issuer,
            "common_name": cert.common_name,
            "not_before": cert.not_before.isoformat() if cert.not_before else None,
            "not_after": cert.not_after.isoformat() if cert.not_after else None,
            "serial_number": cert.serial_number,
            "subject_alternative_names": cert.subject_alternative_names,
            "certificate_fingerprint_sha256": cert.certificate_fingerprint_sha256,
            "subject_public_key_hash": cert.subject_public_key_hash,
            "public_key_algorithm": cert.public_key_algorithm,
            "key_size": cert.key_size,
            "signature_algorithm": cert.signature_algorithm,
            "ct_log_timestamp": cert.ct_log_timestamp,
            "crl_urls": cert.crl_urls,
            "ocsp_urls": cert.ocsp_urls,
            "vetting_level": cert.vetting_level,
            "san_count": cert.san_count,
            "issued_on_weekend": cert.issued_on_weekend,
            "issued_at_night": cert.issued_at_night,
            "organization_type": cert.organization_type,
            "is_wildcard": cert.is_wildcard,
            "root_ca_issuer_name": cert.root_ca_issuer_name,
            "is_precertificate": cert.is_precertificate,
            "log_name": cert.log_name,
            "ct_index": cert.ct_index,
            "ct_log_url": cert.ct_log_url,
            "worker_name": cert.worker_name,
            "created_at": cert.created_at.isoformat() if cert.created_at else None,
            "ct_entry": cert.ct_entry
        })

    return {
        "count": len(result),
        "certs": result
    }




