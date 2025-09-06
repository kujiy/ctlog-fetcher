"""
Debug script to analyze the problematic certificate and understand the ASN.1 parsing error.
"""

import json
import os
import sys
import base64
from cryptography import x509
from cryptography.x509.oid import ExtensionOID

# Add the project root to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

"""
@/tests/resources/issuer/distinct-issuer-cn.json このファイルの証明書のissuerをO, CNなどfieldごとに、テーブル形式で表示するテストファイルを書いて。 @/tests/resources/issuer/distinct-issuer-cn.json を読み込み、ct_entryごとにループ。cryptographyでloadして、issuerのo, cnなどを変数に入れる。最後に変数の中身をtable形式でprint out.
"""
def parse_certificate_from_ct_entry(entry):
    leaf_input = entry.get("leaf_input")
    extra_data = entry.get("extra_data")
    if not leaf_input:
        return None
    leaf_data = base64.b64decode(leaf_input)
    if len(leaf_data) < 12:
        return None
    entry_type = int.from_bytes(leaf_data[10:12], byteorder='big')
    cert_data = None
    if entry_type == 0:
        if len(leaf_data) > 15:
            cert_length = int.from_bytes(leaf_data[12:15], byteorder='big')
            if len(leaf_data) >= 15 + cert_length:
                cert_data = leaf_data[15:15+cert_length]
    elif entry_type == 1:
        if extra_data:
            try:
                extra_decoded = base64.b64decode(extra_data)
                if len(extra_decoded) > 3:
                    cert_length = int.from_bytes(extra_decoded[0:3], byteorder='big')
                    if len(extra_decoded) >= 3 + cert_length:
                        cert_data = extra_decoded[3:3+cert_length]
            except Exception:
                pass
    if not cert_data:
        return None
    try:
        certificate = x509.load_der_x509_certificate(cert_data)
        return certificate
    except Exception:
        return None


def main():
    ct_entry_file_path = "tests/resources/issuer/distinct-issuer-cn.json"
    issuer_rows = []
    with open(ct_entry_file_path, 'r') as f:
        data = json.load(f)
    for item in data:
        ct_entry_str = item.get("ct_entry")
        if not ct_entry_str:
            continue
        try:
            ct_entry = json.loads(ct_entry_str)
        except Exception:
            continue
        certificate = parse_certificate_from_ct_entry(ct_entry)
        if not certificate:
            continue
        issuer_details = get_issuer_details(certificate)
        country = issuer_details.get("countryName", "")
        org = issuer_details.get("organizationName", "")
        cn = issuer_details.get("commonName", "")
        # If multiple values, join with comma
        if isinstance(country, list):
            country = ", ".join(country)
        if isinstance(org, list):
            org = ", ".join(org)
        if isinstance(cn, list):
            cn = ", ".join(cn)
        issuer_rows.append((country, org, cn))
    # Print table
    print(f"{'countryName':<20} {'O':<40} {'CN':<40}")
    print("-" * 100)
    for country, org, cn in issuer_rows:
        print(f"{country:<20} {org:<40} {cn:<40}")

def get_issuer_details(certificate):
    """Extract issuer details into a dictionary."""
    issuer_details = {}
    for attr in certificate.issuer:
        oid_name = attr.oid._name
        if oid_name in issuer_details:
            # If the attribute already exists, convert to list or append to existing list
            if isinstance(issuer_details[oid_name], list):
                issuer_details[oid_name].append(attr.value)
            else:
                issuer_details[oid_name] = [issuer_details[oid_name], attr.value]
        else:
            issuer_details[oid_name] = attr.value
    return issuer_details


if __name__ == '__main__':
    main()
