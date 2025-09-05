"""
Japanese Certificate Parser

Enhanced parser for extracting all required fields from .jp domain certificates.
"""

import base64
import logging
import hashlib
import json
from typing import Dict, List, Optional, Any, Set
from datetime import datetime, timezone, timedelta
from enum import Enum
import warnings

# JST timezone
JST = timezone(timedelta(hours=9))

from cryptography.utils import CryptographyDeprecationWarning
from cryptography.x509 import ExtensionNotFound

try:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.x509.oid import NameOID, ExtensionOID
    import jpholiday
    HAS_CRYPTO = True
    HAS_JPHOLIDAY = True
except ImportError as e:
    HAS_CRYPTO = False
    HAS_JPHOLIDAY = False
    logging.warning(f"Missing dependencies: {e}")

# Suppress UserWarning about attribute length (number at end varies)
"""
Common Name (CN) is defined in RFC 5280 to be a maximum of 64 characters, but in practice, it is used beyond that, so suppress the warning.
repos/ct/src/share/cert_parser.py:163: UserWarning: Attribute's length must be >= 1 and <= 64, but it was 89
  for attribute in certificate.subject:
"""
warnings.filterwarnings(
    "ignore",
    message=r"Attribute's length must be >= 1 and <= 64, but it was.*",
    category=UserWarning
)

logger = logging.getLogger(__name__)

class VettingLevel(str, Enum):
    DV = "dv"
    OV = "ov"
    EV = "ev"

class JPCertificateParser:
    """Enhanced parser for Japanese domain certificates."""

    def __init__(self):
        """Initialize the parser."""
        if not HAS_CRYPTO:
            raise ImportError("cryptography library is required")

        # JST timezone
        self.jp_tz = JST

        # Japanese organization type mappings
        self.org_type_mapping = {
            'go.jp': 'go.jp',      # Government
            'lg.jp': 'lg.jp',      # Local government
            'ac.jp': 'ac.jp',      # Academic
            'co.jp': 'co.jp',      # Commercial
            'ne.jp': 'ne.jp',      # Network
            'or.jp': 'or.jp',      # Organization
            'ed.jp': 'ed.jp',      # Education
            'ad.jp': 'ad.jp',      # JPNIC
            # Add prefectural JP domain names to the mapping
            'hokkaido.jp': 'prefecture.jp',
            'aomori.jp': 'prefecture.jp',
            'iwate.jp': 'prefecture.jp',
            'miyagi.jp': 'prefecture.jp',
            'akita.jp': 'prefecture.jp',
            'yamagata.jp': 'prefecture.jp',
            'fukushima.jp': 'prefecture.jp',
            'ibaraki.jp': 'prefecture.jp',
            'tochigi.jp': 'prefecture.jp',
            'gunma.jp': 'prefecture.jp',
            'saitama.jp': 'prefecture.jp',
            'chiba.jp': 'prefecture.jp',
            'tokyo.jp': 'prefecture.jp',
            'kanagawa.jp': 'prefecture.jp',
            'niigata.jp': 'prefecture.jp',
            'toyama.jp': 'prefecture.jp',
            'ishikawa.jp': 'prefecture.jp',
            'fukui.jp': 'prefecture.jp',
            'yamanashi.jp': 'prefecture.jp',
            'nagano.jp': 'prefecture.jp',
            'gifu.jp': 'prefecture.jp',
            'shizuoka.jp': 'prefecture.jp',
            'aichi.jp': 'prefecture.jp',
            'mie.jp': 'prefecture.jp',
            'shiga.jp': 'prefecture.jp',
            'kyoto.jp': 'prefecture.jp',
            'osaka.jp': 'prefecture.jp',
            'hyogo.jp': 'prefecture.jp',
            'nara.jp': 'prefecture.jp',
            'wakayama.jp': 'prefecture.jp',
            'tottori.jp': 'prefecture.jp',
            'shimane.jp': 'prefecture.jp',
            'okayama.jp': 'prefecture.jp',
            'hiroshima.jp': 'prefecture.jp',
            'yamaguchi.jp': 'prefecture.jp',
            'tokushima.jp': 'prefecture.jp',
            'kagawa.jp': 'prefecture.jp',
            'ehime.jp': 'prefecture.jp',
            'kochi.jp': 'prefecture.jp',
            'fukuoka.jp': 'prefecture.jp',
            'saga.jp': 'prefecture.jp',
            'nagasaki.jp': 'prefecture.jp',
            'kumamoto.jp': 'prefecture.jp',
            'oita.jp': 'prefecture.jp',
            'miyazaki.jp': 'prefecture.jp',
            'kagoshima.jp': 'prefecture.jp',
            'okinawa.jp': 'prefecture.jp'
        }

    def parse_ct_entry_to_certificate_data(self, ct_entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Parse CT log entry and extract all required certificate data (for any domain).
        Returns None only if parsing fails (not for non-jp domains).
        """
        certificate, entry_type, ct_log_timestamp = self._parse_certificate_from_ct_entry(ct_entry)

        # Check if certificate parsing failed (e.g., OCSP certificates)
        if certificate is None:
            return None

        # Extract all domains
        domains = self._extract_domains_from_cert(certificate)

        # Basic certificate information
        cert_data = self._extract_basic_info(certificate, ct_entry)
        cert_data.update(self._extract_extension_urls(certificate))
        cert_data.update(self._extract_timing_info(certificate, ct_log_timestamp))
        # For compatibility, still call _extract_jp_specific_info, but pass all domains
        cert_data.update(self._extract_jp_specific_info(certificate, domains))
        cert_data.update(self._extract_technical_info(certificate))

        cert_data['ct_log_timestamp'] = ct_log_timestamp
        cert_data['subject_alternative_names'] = json.dumps(domains)
        cert_data['san_count'] = len(domains)
        cert_data['is_precertificate'] = (entry_type == 1)
        cert_data['vetting_level'] = self._extract_vetting_level(certificate).value
        return cert_data

    def parse_only_jp_cert(self, ct_entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Parse CT log entry and return cert data only if it is a .jp domain cert, else None.
        """
        cert_data = self.parse_ct_entry_to_certificate_data(ct_entry)
        if not cert_data:
            return None
        # Check if any SAN or CN is .jp
        domains = json.loads(cert_data.get('subject_alternative_names', '[]'))
        if any(d.lower().endswith('.jp') for d in domains):
            return cert_data

    def _parse_certificate_from_ct_entry(self, entry: Dict[str, Any]) -> (Any, Any, Any):
        """Parse certificate from CT log entry."""
        leaf_input = entry.get("leaf_input")
        extra_data = entry.get("extra_data")

        if not leaf_input:
            return None, None, None

        # Decode the leaf input
        leaf_data = base64.b64decode(leaf_input)

        if len(leaf_data) < 12:
            return None, None, None

        # Extract the entry type (2 bytes at offset 10)
        entry_type = int.from_bytes(leaf_data[10:12], byteorder='big')
        # 2:10 bytes in leaf_input is the timestamp (8 bytes)
        ct_log_timestamp_ms = int.from_bytes(leaf_data[2:10], byteorder='big')
        ct_log_timestamp = datetime.fromtimestamp(ct_log_timestamp_ms / 1000, tz=timezone.utc)

        cert_data = None

        if entry_type == 0:  # X509LogEntryType - regular certificate
            if len(leaf_data) > 15:
                cert_length = int.from_bytes(leaf_data[12:15], byteorder='big')
                if len(leaf_data) >= 15 + cert_length:
                    cert_data = leaf_data[15:15+cert_length]

        elif entry_type == 1:  # PrecertLogEntryType - precertificate
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
            return None, entry_type, ct_log_timestamp

        try:
            certificate = x509.load_der_x509_certificate(cert_data)
        except Exception:
            return None, entry_type, ct_log_timestamp

        # Test if we can access certificate extensions
        # Some certificates (like OCSP responder certs) have malformed extension structures
        try:
            # Suppress CryptographyDeprecationWarning and handle it explicitly
            with warnings.catch_warnings(record=True) as caught_warnings:
                warnings.simplefilter("always", CryptographyDeprecationWarning)
                """
                Accessing certificate.extensions to trigger exceptions/warnings
                """
                eku = certificate.extensions.get_extension_for_oid(ExtensionOID.EXTENDED_KEY_USAGE).value
        except ExtensionNotFound:
            # skip a cert without EKU. Since 2020, EKU is mandatory for web server certs.
            return None, entry_type, ct_log_timestamp
        except Exception as e:
            error_msg = str(e)
            # Skip OCSP responder certs with malformed extensions
            # The pem has been recorded in tests/resources/invalid_certs/
            if "error parsing asn1 value" in error_msg \
                or "path_length must be None when ca is False" in error_msg \
                or "The parsed certificate contains a NULL parameter value in its signature algorithm parameters" in error_msg:
                # logger.debug(f"[_parse_certificate_from_ct_entry] Certificate has malformed extensions, skipping: {e}")
                return None, entry_type, ct_log_timestamp
            else:
                # Re-raise unexpected errors
                raise

        # certificate.extensions raises a warning
        if caught_warnings:
            for warning in caught_warnings:
                if issubclass(warning.category, CryptographyDeprecationWarning):
                    try:
                        eku_types = [oid.dotted_string for oid in eku]
                        raise RuntimeError(f"CryptographyDeprecationWarning encountered. EKU types: {eku_types}")
                    except x509.ExtensionNotFound:
                        raise RuntimeError("CryptographyDeprecationWarning encountered, and no EKU extension found.")
                else:
                    raise RuntimeError(f"Unexpected warning encountered: {warning.message}")

        return certificate, entry_type, ct_log_timestamp



    def _extract_domains_from_cert(self, certificate) -> List[str]:
        """Extract all domains from certificate."""
        domains = []

        try:
            # Get Common Name from subject
            for attribute in certificate.subject:
                if attribute.oid == NameOID.COMMON_NAME:
                    domains.append(attribute.value)

            # Get Subject Alternative Names
            try:
                san_ext = certificate.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
                for name in san_ext.value:
                    if isinstance(name, x509.DNSName):
                        domains.append(name.value)
            except x509.ExtensionNotFound:
                pass

        except Exception:
            pass

        return domains

    def _extract_basic_info(self, certificate, ct_entry: Dict[str, Any]) -> Dict[str, Any]:
        """Extract basic certificate information."""
        data = {}

        # Basic fields
        data['certificate_fingerprint_sha256'] = certificate.fingerprint(hashes.SHA256()).hex()
        data['serial_number'] = str(certificate.serial_number)

        # Subject and issuer
        data['subject_common_name'] = self._get_name_attribute(certificate.subject, NameOID.COMMON_NAME)
        issuer_cn = self._get_name_attribute(certificate.issuer, NameOID.COMMON_NAME)
        if issuer_cn is not None:
            data['issuer'] = issuer_cn
        else:
            # {"leaf_input":"AAAAAAFxLko8hwABtnFqrstaexEa6Zz+CVGGozhI8IF1FafM6uzX3zzHrUIABJcwggSToAMCAQICEF+N5G0NnYAA84gnA7BO270wDQYJKoZIhvcNAQELBQAwYDELMAkGA1UEBhMCVFcxIzAhBgNVBAoMGkNodW5naHdhIFRlbGVjb20gQ28uLCBMdGQuMSwwKgYDVQQLDCNQdWJsaWMgQ2VydGlmaWNhdGlvbiBBdXRob3JpdHkgLSBHMjAeFw0yMDAzMzEwMTUyMjlaFw0yMjA0MjExNTU5NTlaMG8xCzAJBgNVBAYTAlRXMRIwEAYDVQQHDAnoh7rljJfluIIxLTArBgNVBAoMJOWogemLkuaVuOS9jemWi+eZvOiCoeS7veaciemZkOWFrOWPuDEdMBsGA1UEAwwUdGVzdGRmby5keW5hY3cuY28uanAwggEiMA0GCSqGSIb3DQEBAQUAA4IBDwAwggEKAoIBAQCK9D6eZrXr6ekkncYlwKaZFkwkSpPcCH7SsstAzlHQSIkBxLtc8VFO8hy6B3g2KRKp0VBLQNtOkLVOvjrm9lBh+LVOHxeX4Xj2S8HDabFg9ZnEx2K/QNPRFj75mlUS1nl94O8RX4vlpqqAAwkTMQY9PxOC0M6GUPLY9a2RMpB54TGg1+FcdkXZ2loYoMMxdc+tsAcaSi/GSQg8t24mDSDL1ms1eve+StqL9YQarmvScvw9QehF4NsrDD5XxBLbGPdEyep8HDc3ddj8OGskbdLJdOqyQ3ZQLUDUEdShum7hDPJsq7TOxtHqwGG/TgTR/g366bBs873SqMXCOUeQRVxpAgMBAAGjggJQMIICTDAfBgNVHSMEGDAWgBTLg31lFa+pyfOoqfRkfHlSBXRAYTAdBgNVHQ4EFgQU4SyUqnc1+726PV9DC4ZT1WYWxwUwgZsGA1UdHwSBkzCBkDBJoEegRYZDaHR0cDovL3JlcG9zaXRvcnkucHVibGljY2EuaGluZXQubmV0L2NybC9QdWJDQUcyLzEwMC0xL2NvbXBsZXRlLmNybDBDoEGgP4Y9aHR0cDovL3JlcG9zaXRvcnkucHVibGljY2EuaGluZXQubmV0L2NybC9QdWJDQUcyL2NvbXBsZXRlLmNybDCBkwYIKwYBBQUHAQEEgYYwgYMwSQYIKwYBBQUHMAKGPWh0dHA6Ly9yZXBvc2l0b3J5LnB1YmxpY2NhLmhpbmV0Lm5ldC9jZXJ0cy9Jc3N1ZWRUb1RoaXNDQS5wN2IwNgYIKwYBBQUHMAGGKmh0dHA6Ly9vY3NwLnB1YmxpY2NhLmhpbmV0Lm5ldC9PQ1NQL29jc3BHMjAiBgNVHSAEGzAZMAgGBmeBDAECAjANBgsrBgEEAYG3I2QAAzAdBgNVHSUEFjAUBggrBgEFBQcDAQYIKwYBBQUHAwIwgYIGA1UdEQR7MHmCFHRlc3RkZm8uZHluYWN3LmNvLmpwghV0ZXN0ZGZvLmR5bmFjdy5jb20udHeCEnRlc3QuZHluYWN3LmNvbS50d4ISdGVzdC5keW5hY3cuY29tLmhrgg90ZXN0LmR5bmFjdy5jb22CEW1haWxkYy5keW5hY3cuY29tMA4GA1UdDwEB/wQEAwIFoAAA","extra_data":"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"}
            data['issuer'] = certificate.issuer.rfc4514_string()

        # Validity period
        data['not_before'] = certificate.not_valid_before_utc.replace(tzinfo=None)
        data['not_after'] = certificate.not_valid_after_utc.replace(tzinfo=None)

        # Public key info
        public_key = certificate.public_key()
        data['public_key_algorithm'] = public_key.__class__.__name__
        data['key_size'] = self._get_key_size(public_key)

        # Signature algorithm
        data['signature_algorithm'] = certificate.signature_algorithm_oid._name

        return data

    def _extract_extension_urls(self, certificate) -> Dict[str, Any]:
        """Extract CRL and OCSP URLs."""
        data = {
            'crl_urls': None,
            'ocsp_urls': None
        }

        try:
            # CRL Distribution Points
            try:
                crl_ext = certificate.extensions.get_extension_for_oid(ExtensionOID.CRL_DISTRIBUTION_POINTS)
                crl_urls = []
                for point in crl_ext.value:
                    if point.full_name:
                        for name in point.full_name:
                            if isinstance(name, x509.UniformResourceIdentifier):
                                crl_urls.append(name.value)
                if crl_urls:
                    data['crl_urls'] = json.dumps(crl_urls)
            except x509.ExtensionNotFound:
                pass

            # OCSP URLs
            try:
                aia_ext = certificate.extensions.get_extension_for_oid(ExtensionOID.AUTHORITY_INFORMATION_ACCESS)
                ocsp_urls = []
                for desc in aia_ext.value:
                    if desc.access_method == x509.AuthorityInformationAccessOID.OCSP:
                        if isinstance(desc.access_location, x509.UniformResourceIdentifier):
                            ocsp_urls.append(desc.access_location.value)
                if ocsp_urls:
                    data['ocsp_urls'] = json.dumps(ocsp_urls)
            except x509.ExtensionNotFound:
                pass

        except Exception as e:
            logger.debug(f"[_extract_extension_urls] Error extracting URLs: {e}")
            raise

        return data

    def _extract_timing_info(self, certificate, ct_log_timestamp) -> Dict[str, Any]:
        """Extract timing-related information for Japan using ct_log_timestamp."""
        data = {
            'issued_on_weekend': False,
            'issued_at_night': False
        }

        try:
            # Convert to Japan time using ct_log_timestamp
            ct_jp = ct_log_timestamp.astimezone(self.jp_tz)

            # Check if issued on weekend
            weekday = ct_jp.weekday()  # 0=Monday, 6=Sunday
            data['issued_on_weekend'] = weekday >= 5  # Saturday or Sunday

            # Check if issued at night (20:00 - 08:00 JST)
            hour = ct_jp.hour
            data['issued_at_night'] = hour >= 20 or hour < 8

            # Check if issued on Japanese holiday (if jpholiday is available)
            if HAS_JPHOLIDAY:
                try:
                    date_only = ct_jp.date()
                    if jpholiday.is_holiday(date_only):
                        data['issued_on_weekend'] = True  # Treat holidays as weekends
                except Exception:
                    pass

        except Exception as e:
            logger.debug(f"[_extract_timing_info] Error extracting timing info: {e}")
            raise

        return data

    def _extract_jp_specific_info(self, certificate, jp_domains: List[str]) -> Dict[str, Any]:
        """Extract Japan-specific certificate information."""
        data = {
            'organization_type': 'unknown',
            'is_wildcard': False,
            'root_ca_issuer_name': None
        }

        try:
            self._extract_org_type(data, jp_domains)

            # Check for wildcard certificates
            for domain in jp_domains:
                if '*' in domain:
                    data['is_wildcard'] = True
                    break

            # Extract root CA name (simplified - use issuer for now)
            data['root_ca_issuer_name'] = self._get_name_attribute(certificate.issuer, NameOID.COMMON_NAME)

        except Exception as e:
            logger.debug(f"[_extract_jp_specific_info] Error extracting JP-specific info: {e}")
            raise

        return data

    def _extract_org_type(self, data, jp_domains):
        # Determine organization type from domains
        for domain in jp_domains:
            domain_lower = domain.lower()
            for suffix, org_type in self.org_type_mapping.items():
                if domain_lower.endswith('.' + suffix):
                    data['organization_type'] = org_type
                    break
            if data['organization_type'] != 'unknown':
                break

    def _extract_vetting_level(self, certificate) -> VettingLevel:
        """
        Extract vetting level: 'ev' if policy OID 2.23.140.1.1 is present,
        'ov' if organizationName (O) is present, otherwise 'dv'.
        """
        try:
            # Check for EV OID in certificate policies
            try:
                policies = certificate.extensions.get_extension_for_oid(
                    x509.ExtensionOID.CERTIFICATE_POLICIES
                ).value
                for policy in policies:
                    if getattr(policy.policy_identifier, "dotted_string", "") == "2.23.140.1.1":
                        return VettingLevel.EV
            except Exception:
                pass

            # Check for organizationName (O)
            try:
                org = self._get_name_attribute(certificate.subject, x509.NameOID.ORGANIZATION_NAME)
                if org:
                    return VettingLevel.OV
            except Exception:
                pass

            return VettingLevel.DV
        except Exception:
            return VettingLevel.DV

    def _extract_technical_info(self, certificate) -> Dict[str, Any]:
        """Extract technical information."""
        data = {
            'subject_public_key_hash': None,
            'issuance_lag_seconds': None,
            'days_before_expiry': None,
            'issued_after_expiry': False,
            'is_automated_renewal': None
        }

        try:
            # Public key hash for detecting key reuse
            public_key = certificate.public_key()
            public_key_bytes = public_key.public_bytes(
                encoding=serialization.Encoding.DER,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )
            data['subject_public_key_hash'] = hashlib.sha256(public_key_bytes).hexdigest()

            # Calculate issuance lag (CT timestamp vs not_before)
            # This would need the actual CT timestamp converted properly
            # For now, set to None as we need more precise timing data

            # Other fields would be calculated during analysis phase
            # when comparing with previous certificates

        except Exception as e:
            logger.debug(f"[_extract_technical_info] Error extracting technical info: {e}")
            raise

        return data

    def _get_name_attribute(self, name, oid) -> Optional[str]:
        """Extract a specific attribute from a certificate name."""
        try:
            attributes = name.get_attributes_for_oid(oid)
            if attributes:
                return attributes[0].value
        except Exception:
            pass
        return None

    def _get_key_size(self, public_key) -> Optional[int]:
        """Get the size of the public key."""
        try:
            if hasattr(public_key, 'key_size'):
                return public_key.key_size
            elif hasattr(public_key, 'curve') and hasattr(public_key.curve, 'key_size'):
                return public_key.curve.key_size
        except Exception:
            pass
        return None

    def calculate_renewal_metrics(self, current_cert: Dict[str, Any],
                                previous_certs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Calculate renewal-related metrics by comparing with previous certificates.

        Args:
            current_cert: Current certificate data
            previous_certs: List of previous certificates for the same domain(s)

        Returns:
            Dictionary with renewal metrics
        """
        metrics = {
            'days_before_expiry': None,
            'issued_after_expiry': False,
            'is_automated_renewal': None
        }

        try:
            if not previous_certs:
                return metrics

            # Find the most recent previous certificate
            previous_cert = max(previous_certs, key=lambda x: x.get('not_before', datetime.min))

            current_not_before = current_cert['not_before']
            previous_not_after = previous_cert.get('not_after')

            if previous_not_after:
                # Calculate days between expiry and new certificate
                delta = current_not_before - previous_not_after
                metrics['days_before_expiry'] = delta.days

                # Check if issued after expiry
                metrics['issued_after_expiry'] = delta.days > 0

                # Simple heuristic for automated renewal
                # Regular intervals (like 60, 90 days before expiry) suggest automation
                days_before = -delta.days if delta.days < 0 else 0
                common_intervals = [30, 60, 90]  # Common auto-renewal intervals

                if any(abs(days_before - interval) <= 7 for interval in common_intervals):
                    metrics['is_automated_renewal'] = True
                elif delta.days > 30:  # Very late renewal suggests manual process
                    metrics['is_automated_renewal'] = False

        except Exception as e:
            logger.debug(f"[calculate_renewal_metrics] Error calculating renewal metrics: {e}")
            raise

        return metrics
