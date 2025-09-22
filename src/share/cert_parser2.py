"""
Japanese Certificate Parser for Cert2 Model

Enhanced parser for extracting certificate data specifically for the Cert2 analysis model.
"""

import base64
import logging
import hashlib
import json
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timezone, timedelta
from enum import Enum
import warnings

# JST timezone
JST = timezone(timedelta(hours=9))

from pydantic import BaseModel, Field
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


class Cert2Data(BaseModel):
    """Pydantic model for certificate data returned by JPCertificateParser2."""
    
    # Basic certificate information
    certificate_fingerprint_sha256: str = Field(..., description="SHA256 fingerprint of the certificate")
    serial_number: str = Field(..., description="Certificate serial number")
    common_name: Optional[str] = Field(None, description="Common name from certificate subject")
    
    # Validity period
    not_before: datetime = Field(..., description="Certificate not valid before date")
    not_after: datetime = Field(..., description="Certificate not valid after date")
    
    # Public key information
    public_key_algorithm: Optional[str] = Field(None, description="Public key algorithm")
    key_size: Optional[int] = Field(None, description="Public key size in bits")
    signature_algorithm: Optional[str] = Field(None, description="Signature algorithm")
    
    # URL indicators
    has_crl_urls: int = Field(0, description="Binary indicator for CRL URLs presence (0 or 1)")
    has_ocsp_urls: int = Field(0, description="Binary indicator for OCSP URLs presence (0 or 1)")
    
    # Timing information
    issued_on_weekend: bool = Field(False, description="Whether certificate was issued on weekend/holiday")
    issued_at_night: bool = Field(False, description="Whether certificate was issued at night (20:00-08:00 JST)")
    
    # Japan-specific information
    organization_type: str = Field("unknown", description="Organization type based on JP domain")
    is_wildcard: bool = Field(False, description="Whether certificate is a wildcard certificate")
    root_ca_issuer_name: Optional[str] = Field(None, description="Root CA issuer name")
    
    # Technical information
    subject_public_key_hash: Optional[str] = Field(None, description="SHA256 hash of subject public key")
    issuance_lag_seconds: Optional[int] = Field(None, description="Issuance lag in seconds")
    days_before_expiry: Optional[int] = Field(None, description="Days before certificate expiry")
    issued_after_expiry: bool = Field(False, description="Whether certificate was issued after expiry")
    is_automated_renewal: Optional[bool] = Field(None, description="Whether certificate is automated renewal")
    
    # Issuer information
    issuer: Optional[str] = Field(None, description="Complete issuer string")
    issuer_cn: Optional[str] = Field(None, description="Issuer common name")
    issuer_o: Optional[str] = Field(None, description="Issuer organization")
    issuer_ou: Optional[str] = Field(None, description="Issuer organizational unit")
    issuer_c: Optional[str] = Field(None, description="Issuer country")
    issuer_st: Optional[str] = Field(None, description="Issuer state/province")
    issuer_l: Optional[str] = Field(None, description="Issuer locality")
    issuer_email: Optional[str] = Field(None, description="Issuer email")
    issuer_dc: Optional[str] = Field(None, description="Issuer domain component")
    
    # Root issuer information
    root_issuer: Optional[str] = Field(None, description="Complete root issuer string")
    root_issuer_cn: Optional[str] = Field(None, description="Root issuer common name")
    root_issuer_o: Optional[str] = Field(None, description="Root issuer organization")
    root_issuer_ou: Optional[str] = Field(None, description="Root issuer organizational unit")
    root_issuer_c: Optional[str] = Field(None, description="Root issuer country")
    root_issuer_st: Optional[str] = Field(None, description="Root issuer state/province")
    root_issuer_l: Optional[str] = Field(None, description="Root issuer locality")
    root_issuer_email: Optional[str] = Field(None, description="Root issuer email")
    root_issuer_dc: Optional[str] = Field(None, description="Root issuer domain component")
    
    # CT log specific information
    ct_log_timestamp: datetime = Field(..., description="CT log timestamp")
    subject_alternative_names: str = Field(..., description="JSON string of subject alternative names")
    san_count: int = Field(0, description="Number of subject alternative names")
    is_precertificate: bool = Field(False, description="Whether this is a precertificate")
    vetting_level: str = Field(..., description="Certificate vetting level (dv, ov, ev)")


class JPCertificateParser2:
    """Enhanced parser for Japanese domain certificates - Cert2 model specific."""

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

    def parse_ct_entry_to_cert2_data(self, ct_entry: Dict[str, Any]) -> Optional[Cert2Data]:
        """
        Parse CT log entry and extract all required certificate data for Cert2 model.
        Returns None only if parsing fails (not for non-jp domains).
        """
        certificate, entry_type, ct_log_timestamp = self._parse_certificate_from_ct_entry(ct_entry)

        # Check if certificate parsing failed (e.g., OCSP certificates)
        if certificate is None:
            return None

        # Extract all domains
        domains = self._extract_domains_from_cert(certificate)

        # Basic certificate information for Cert2
        cert_data = self._extract_cert2_basic_info(certificate, ct_entry)
        cert_data.update(self._extract_cert2_url_indicators(certificate))
        cert_data.update(self._extract_timing_info(certificate, ct_log_timestamp))
        cert_data.update(self._extract_jp_specific_info(certificate, domains))
        cert_data.update(self._extract_technical_info(certificate))
        cert_data.update(self._extract_cert2_issuer_components(certificate))

        cert_data['ct_log_timestamp'] = ct_log_timestamp
        cert_data['subject_alternative_names'] = json.dumps(domains)
        cert_data['san_count'] = len(domains)
        cert_data['is_precertificate'] = (entry_type == 1)
        cert_data['vetting_level'] = self._extract_vetting_level(certificate).value
        
        return Cert2Data(**cert_data)

    def parse_only_jp_cert_to_cert2(self, ct_entry: Dict[str, Any]) -> Optional[Cert2Data]:
        """
        Parse CT log entry and return cert2 data only if it is a .jp domain cert, else None.
        """
        cert_data = self.parse_ct_entry_to_cert2_data(ct_entry)
        if not cert_data:
            return None
        # Check if any SAN or CN is .jp
        domains = json.loads(cert_data.subject_alternative_names)
        if any(d.lower().endswith('.jp') for d in domains):
            return cert_data
        return None

    def _parse_certificate_from_ct_entry(self, entry: Dict[str, Any]) -> Tuple[Any, Any, Any]:
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

    def get_preferred_issuer_string(self, issuer) -> str:
        """
        Return issuer string by priority:
        1. O (OrganizationName)
        2. CN (CommonName)
        3. rfc4514_string()
        """
        org = self._get_name_attribute(issuer, NameOID.ORGANIZATION_NAME)
        if org:
            return org
        cn = self._get_name_attribute(issuer, NameOID.COMMON_NAME)
        if cn:
            return cn
        return issuer.rfc4514_string()

    def _extract_cert2_basic_info(self, certificate, ct_entry: Dict[str, Any]) -> Dict[str, Any]:
        """Extract basic certificate information for Cert2 model."""
        data = {}

        # Basic fields (same as original but with common_name instead of subject_common_name)
        data['certificate_fingerprint_sha256'] = certificate.fingerprint(hashes.SHA256()).hex()
        data['serial_number'] = str(certificate.serial_number)
        data['common_name'] = self._get_name_attribute(certificate.subject, NameOID.COMMON_NAME)

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

    def _extract_cert2_url_indicators(self, certificate) -> Dict[str, Any]:
        """Extract binary indicators for CRL and OCSP URLs presence."""
        data = {
            'has_crl_urls': 0,
            'has_ocsp_urls': 0
        }

        try:
            # Check CRL Distribution Points
            try:
                crl_ext = certificate.extensions.get_extension_for_oid(ExtensionOID.CRL_DISTRIBUTION_POINTS)
                for point in crl_ext.value:
                    if point.full_name:
                        for name in point.full_name:
                            if isinstance(name, x509.UniformResourceIdentifier):
                                data['has_crl_urls'] = 1
                                break
                    if data['has_crl_urls'] == 1:
                        break
            except x509.ExtensionNotFound:
                pass

            # Check OCSP URLs
            try:
                aia_ext = certificate.extensions.get_extension_for_oid(ExtensionOID.AUTHORITY_INFORMATION_ACCESS)
                for desc in aia_ext.value:
                    if desc.access_method == x509.AuthorityInformationAccessOID.OCSP:
                        if isinstance(desc.access_location, x509.UniformResourceIdentifier):
                            data['has_ocsp_urls'] = 1
                            break
            except x509.ExtensionNotFound:
                pass

        except Exception as e:
            logger.debug(f"[_extract_cert2_url_indicators] Error extracting URL indicators: {e}")
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
        except Exception as e:
            logger.debug(f"[_extract_technical_info] Error extracting technical info: {e}")
            raise

        return data

    def _extract_cert2_issuer_components(self, certificate) -> Dict[str, Any]:
        """Extract issuer and root issuer components for Cert2 model."""
        data = {}

        # Complete issuer string (for unique index)
        data['issuer'] = self.get_preferred_issuer_string(certificate.issuer)
        
        # Individual issuer components
        data['issuer_cn'] = self._get_name_attribute(certificate.issuer, NameOID.COMMON_NAME)
        data['issuer_o'] = self._get_name_attribute(certificate.issuer, NameOID.ORGANIZATION_NAME)
        data['issuer_ou'] = self._get_name_attribute(certificate.issuer, NameOID.ORGANIZATIONAL_UNIT_NAME)
        data['issuer_c'] = self._get_name_attribute(certificate.issuer, NameOID.COUNTRY_NAME)
        data['issuer_st'] = self._get_name_attribute(certificate.issuer, NameOID.STATE_OR_PROVINCE_NAME)
        data['issuer_l'] = self._get_name_attribute(certificate.issuer, NameOID.LOCALITY_NAME)
        data['issuer_email'] = self._get_name_attribute(certificate.issuer, NameOID.EMAIL_ADDRESS)
        data['issuer_dc'] = self._get_name_attribute(certificate.issuer, NameOID.DOMAIN_COMPONENT)

        # For root issuer, we'll use the same issuer data for now
        # In a real implementation, you might want to extract this from the certificate chain
        data['root_issuer'] = data['issuer']
        data['root_issuer_cn'] = data['issuer_cn']
        data['root_issuer_o'] = data['issuer_o']
        data['root_issuer_ou'] = data['issuer_ou']
        data['root_issuer_c'] = data['issuer_c']
        data['root_issuer_st'] = data['issuer_st']
        data['root_issuer_l'] = data['issuer_l']
        data['root_issuer_email'] = data['issuer_email']
        data['root_issuer_dc'] = data['issuer_dc']

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
