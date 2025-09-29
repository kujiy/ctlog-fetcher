import json
import os
import time
import traceback
import uuid
from typing import List

import requests

from src.share.cert_parser2 import JPCertificateParser2
from src.worker import logger, FAILED_FILE_DIR
from src.worker.worker_base_models import WorkerArgs, CertCompareModel, PendingRequest
from src.worker.worker_common_funcs import list_model_to_list_dict
from src.worker.worker_error_handlings import report_worker_error, save_pending_request
from src.manager_api.base_models import UploadCertItem



# --- JP certs filter for uniqueness ---
# Remove duplicate JP certificates
def extract_jp_certs(entries, log_name, ct_log_url, args: WorkerArgs, current) -> List[CertCompareModel]:
    jp_certs = []
    parser = JPCertificateParser2()
    for i, entry in enumerate(entries):
        try:
            cert_data = parser.parse_only_jp_cert_to_cert2(entry)
        except Exception as e:
            _tb = traceback.format_exc()
            ct_index = current + i

            # Save failed entry to tests/resources/failed directory
            try:
                failed_entry_data = {
                    "entry": entry,
                    "log_name": log_name,
                    "ct_log_url": ct_log_url,
                    "ct_index": ct_index,
                    "worker_name": args.worker_name,
                    "error_message": str(e),
                    "traceback": _tb,
                    "timestamp": time.time()
                }
                failed_filename = f"failed_entry_{log_name}_{ct_index}_{uuid.uuid4().hex[:8]}.json"
                failed_filepath = os.path.join(FAILED_FILE_DIR, failed_filename)
                with open(failed_filepath, "w") as f:
                    json.dump(failed_entry_data, f, indent=2)
                logger.debug(f"Saved failed entry to {failed_filepath}")
            except Exception as save_e:
                logger.warning(f"Failed to save failed entry: {save_e}")

            report_worker_error(
                args=args,
                error_type="parse_error",
                error_message=str(e),
                traceback_str=_tb,
                entry=entry,
                log_name=log_name,
                ct_log_url=ct_log_url,
                ct_index=ct_index
            )
            continue
        if cert_data:
            jp_certs.append(CertCompareModel(**{
                "ct_entry": json.dumps(entry, separators=(',', ':')),
                "ct_log_url": ct_log_url,
                "log_name": log_name,
                "worker_name": args.worker_name,
                "ct_index": current + i,
                "ip_address": None,  # Optional field from UploadCertItem
                "issuer": cert_data.issuer,
                "serial_number": cert_data.serial_number,
                "certificate_fingerprint_sha256": cert_data.certificate_fingerprint_sha256,
                "common_name": cert_data.common_name
            }))
    return jp_certs


def filter_jp_certs_unique(jp_certs: List[CertCompareModel]) -> List[CertCompareModel]:
    seen = set()
    filtered = []
    for cert in jp_certs:
        key = (
            cert.issuer,
            cert.serial_number,
            cert.certificate_fingerprint_sha256,
        )
        if key not in seen:
            seen.add(key)
            filtered.append(cert)
    return filtered


# --- upload_jp_certs: moved above worker_job_thread ---
# Upload JP certificates to the manager API
def upload_jp_certs(args, category, current, jp_certs: List[CertCompareModel], failed_lock) -> int:
    last_uploaded_index = None
    if jp_certs:
        # Convert CertCompareModel to UploadCertItem (remove internal duplicate checking fields)
        upload_items = [
            UploadCertItem(
                ct_entry=cert.ct_entry,
                ct_log_url=cert.ct_log_url,
                log_name=cert.log_name,
                worker_name=cert.worker_name,
                ct_index=cert.ct_index,
            )
            for cert in jp_certs
        ]

        url = f"{args.manager}/api/worker/upload2"
        try:
            resp = requests.post(url, json=[item.dict() for item in upload_items], timeout=180)
            if resp.status_code == 200:
                last_uploaded_index = current
            else:
                logger.warning(f"[{category}] Upload failed: {resp.status_code} {url} {resp.text}")
                with failed_lock:
                    save_pending_request(PendingRequest(
                        url=url,
                        method="POST",
                        data=[item.dict() for item in upload_items]
                    ), prefix="pending_upload")
        except Exception as e:
            logger.debug(f"[{category}] Upload exception: {e}")
            with failed_lock:
                save_pending_request(PendingRequest(
                    url=url,
                    method="POST",
                    data=[item.dict() for item in upload_items]
                ), prefix="pending_upload")
    return last_uploaded_index



def upload(args: WorkerArgs, category, ct_log_url, current, entries, failed_lock,
           jp_certs_buffer: List[CertCompareModel], last_uploaded_index: int, log_name: str,
           worker_jp_count: int) -> (List[CertCompareModel], int, int):
    # Parsing
    jp_certs: CertCompareModel = extract_jp_certs(entries, log_name, ct_log_url, args, current)
    if jp_certs:
        # Add the number of found jp_certs before deduplication as a reward for the worker
        worker_jp_count += len(jp_certs)
        jp_certs_buffer.extend(jp_certs)
        # Remove duplicates
        jp_certs_buffer = filter_jp_certs_unique(jp_certs_buffer)
    # upload if buffer is large enough
    if len(jp_certs_buffer) >= 32:
        last_uploaded_index = upload_jp_certs(args, category, current, jp_certs_buffer, failed_lock)
        jp_certs_buffer = []
    return jp_certs_buffer, last_uploaded_index, worker_jp_count
