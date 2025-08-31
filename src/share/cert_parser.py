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
Common nameはRFC 5280で最大64文字までと定義されているが、実際はそれ以上使われているので警告を抑制する
/Users/jp23223/repos/ct/src/share/cert_parser.py:163: UserWarning: Attribute's length must be >= 1 and <= 64, but it was 89
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
        cert_data.update(self._extract_timing_info(certificate))
        # For compatibility, still call _extract_jp_specific_info, but pass all domains
        cert_data.update(self._extract_jp_specific_info(certificate, domains))
        cert_data.update(self._extract_technical_info(certificate))

        ## TODO: ct_log_timestampをDateTimeで保存するようにDB側を変更する
        # cert_data['ct_log_timestamp'] = ct_log_timestamp
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
        # leaf_inputの2:10バイト目から8バイトがtimestamp
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
            # EKUがない証明書はスルー。2020年以降のweb server用証明書はEKU必須
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
        data['issuer'] = self._get_name_attribute(certificate.issuer, NameOID.COMMON_NAME)

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

    def _extract_timing_info(self, certificate) -> Dict[str, Any]:
        """Extract timing-related information for Japan."""
        data = {
            'issued_on_weekend': False,
            'issued_at_night': False
        }

        try:
            # Convert to Japan time
            not_before_utc = certificate.not_valid_before_utc
            not_before_jp = not_before_utc.replace(tzinfo=timezone.utc).astimezone(self.jp_tz)

            # Check if issued on weekend
            weekday = not_before_jp.weekday()  # 0=Monday, 6=Sunday
            data['issued_on_weekend'] = weekday >= 5  # Saturday or Sunday

            # Check if issued at night (20:00 - 08:00 JST)
            hour = not_before_jp.hour
            data['issued_at_night'] = hour >= 20 or hour < 8

            # Check if issued on Japanese holiday (if jpholiday is available)
            if HAS_JPHOLIDAY:
                try:
                    date_only = not_before_jp.date()
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
