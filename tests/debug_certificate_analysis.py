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

def analyze_certificate_extensions(cert_data):
    """Analyze certificate extensions in detail."""
    print("🔍 CERTIFICATE EXTENSION ANALYSIS")
    print("=" * 50)

    try:
        certificate = x509.load_der_x509_certificate(cert_data)
        print(f"✅ Certificate loaded successfully")
        print(f"📋 Subject: {certificate.subject}")
        print(f"🏢 Issuer: {certificate.issuer}")
        print(f"🔢 Serial number: {certificate.serial_number}")
        print(f"📅 Valid from: {certificate.not_valid_before_utc}")
        print(f"📅 Valid until: {certificate.not_valid_after_utc}")

        print(f"\n🔧 EXTENSIONS ANALYSIS:")
        print(f"📊 Total extensions: {len(certificate.extensions)}")

        for i, ext in enumerate(certificate.extensions):
            print(f"\n📌 Extension {i+1}:")
            print(f"   OID: {ext.oid}")
            print(f"   Critical: {ext.critical}")
            print(f"   Value type: {type(ext.value)}")

            # Check if this is the problematic extension
            if ext.oid == ExtensionOID.CRL_DISTRIBUTION_POINTS:
                print(f"   ⚠️  THIS IS CRL_DISTRIBUTION_POINTS - PROBLEMATIC EXTENSION!")
                try:
                    print(f"   Value: {ext.value}")
                    for j, point in enumerate(ext.value):
                        print(f"      Point {j+1}: {point}")
                        if point.full_name:
                            for k, name in enumerate(point.full_name):
                                print(f"         Name {k+1}: {name} (type: {type(name)})")
                except Exception as e:
                    print(f"   ❌ ERROR accessing CRL extension value: {e}")
                    print(f"   🔍 Raw extension data length: {len(ext.value.public_bytes()) if hasattr(ext.value, 'public_bytes') else 'N/A'}")

            elif ext.oid == ExtensionOID.AUTHORITY_INFORMATION_ACCESS:
                print(f"   ℹ️  THIS IS AUTHORITY_INFORMATION_ACCESS")
                try:
                    print(f"   Value: {ext.value}")
                    for j, desc in enumerate(ext.value):
                        print(f"      Access {j+1}: {desc.access_method} -> {desc.access_location}")
                except Exception as e:
                    print(f"   ❌ ERROR accessing AIA extension value: {e}")

            else:
                try:
                    # Try to access the value safely
                    value_str = str(ext.value)[:100] + "..." if len(str(ext.value)) > 100 else str(ext.value)
                    print(f"   Value: {value_str}")
                except Exception as e:
                    print(f"   ❌ ERROR accessing extension value: {e}")

        return certificate

    except Exception as e:
        print(f"❌ Failed to load certificate: {e}")
        return None

def analyze_failed_entry():
    """Analyze the specific failed entry."""
    failed_entry_file = os.path.join(
        os.path.dirname(__file__),
        'resources',
        'invalid_certs',
        'path-length.json'
    )

    print("🧪 ANALYZING FAILED CERTIFICATE ENTRY")
    print("=" * 50)

    with open(failed_entry_file, 'r') as f:
        failed_data = json.load(f)

    ct_entry = failed_data['entry']

    print(f"📁 File: {os.path.basename(failed_entry_file)}")
    # print(f"🏷️  Log name: {failed_data['log_name']}")
    # print(f"🔢 CT index: {failed_data['ct_index']}")
    # print(f"⚠️  Expected error: {failed_data['error_message']}")

    # Parse the certificate from CT entry
    leaf_input = ct_entry.get("leaf_input")
    extra_data = ct_entry.get("extra_data")

    if not leaf_input:
        print("❌ No leaf_input found")
        return

    # Decode the leaf input
    leaf_data = base64.b64decode(leaf_input)
    print(f"📊 Leaf data length: {len(leaf_data)} bytes")

    if len(leaf_data) < 12:
        print("❌ Leaf data too short")
        return

    # Extract the entry type (2 bytes at offset 10)
    entry_type = int.from_bytes(leaf_data[10:12], byteorder='big')
    print(f"🏷️  Entry type: {entry_type} ({'X509LogEntryType' if entry_type == 0 else 'PrecertLogEntryType' if entry_type == 1 else 'Unknown'})")

    cert_data = None

    if entry_type == 0:  # X509LogEntryType - regular certificate
        if len(leaf_data) > 15:
            cert_length = int.from_bytes(leaf_data[12:15], byteorder='big')
            print(f"📏 Certificate length: {cert_length} bytes")
            if len(leaf_data) >= 15 + cert_length:
                cert_data = leaf_data[15:15+cert_length]
                print(f"✅ Extracted certificate data: {len(cert_data)} bytes")

    elif entry_type == 1:  # PrecertLogEntryType - precertificate
        if extra_data:
            try:
                extra_decoded = base64.b64decode(extra_data)
                print(f"📊 Extra data length: {len(extra_decoded)} bytes")
                if len(extra_decoded) > 3:
                    cert_length = int.from_bytes(extra_decoded[0:3], byteorder='big')
                    print(f"📏 Certificate length from extra_data: {cert_length} bytes")
                    if len(extra_decoded) >= 3 + cert_length:
                        cert_data = extra_decoded[3:3+cert_length]
                        print(f"✅ Extracted certificate data from extra_data: {len(cert_data)} bytes")
            except Exception as e:
                print(f"❌ Error processing extra_data: {e}")

    if cert_data:
        print(f"\n🔍 ANALYZING CERTIFICATE DATA:")
        certificate = analyze_certificate_extensions(cert_data)

        if certificate:
            print(f"\n🎯 TESTING SPECIFIC EXTENSION ACCESS:")

            # Test CRL Distribution Points access
            print(f"\n📋 Testing CRL Distribution Points access...")
            try:
                crl_ext = certificate.extensions.get_extension_for_oid(ExtensionOID.CRL_DISTRIBUTION_POINTS)
                print(f"✅ CRL extension found: {crl_ext}")
                print(f"   Critical: {crl_ext.critical}")
                print(f"   Value type: {type(crl_ext.value)}")

                # Try to access the value
                print(f"   Attempting to access value...")
                crl_value = crl_ext.value
                print(f"   ✅ Value accessed successfully: {crl_value}")

                # Try to iterate through points
                print(f"   Attempting to iterate through distribution points...")
                for i, point in enumerate(crl_value):
                    print(f"      Point {i}: {point}")
                    if point.full_name:
                        print(f"         Full name: {point.full_name}")
                        for j, name in enumerate(point.full_name):
                            print(f"            Name {j}: {name} (type: {type(name)})")
                            if isinstance(name, x509.UniformResourceIdentifier):
                                print(f"               URI: {name.value}")

            except Exception as e:
                print(f"❌ ERROR accessing CRL Distribution Points: {e}")
                print(f"   Error type: {type(e)}")
                import traceback
                print(f"   Traceback:\n{traceback.format_exc()}")

    else:
        print("❌ No certificate data extracted")

if __name__ == '__main__':
    analyze_failed_entry()
