"""Privacy and PII (Personally Identifiable Information) sanitization utility.

Ensures the Temple Chatbot does not permanently retain unnecessary personal information
in conversation messages or telemetry metadata.
"""

import re
from typing import Any, Dict, Optional


# Regex patterns for common personal identifiable information
EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
    re.IGNORECASE,
)

# Credit/Debit Card pattern (13-19 digits with optional spaces or dashes)
CREDIT_CARD_PATTERN = re.compile(
    r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|6(?:011|5[0-9][0-9])[0-9]{12}|3[47][0-9]{13}|3(?:0[0-5]|[68][0-9])[0-9]{11}|(?:2131|1800|35\d{3})\d{11})\b"
    r"|\b(?:\d{4}[\s-]?){3}\d{4}\b"
)

# Government IDs (Indian Aadhaar: 12 digits e.g. 1234 5678 9012, and US SSN: 123-45-6789)
AADHAAR_PATTERN = re.compile(r"\b\d{4}\s\d{4}\s\d{4}\b")
SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

# Phone numbers (Indian +91 / local 10-digit, US/UK format, and international with optional country code)
PHONE_PATTERN = re.compile(
    r"(?:(?:\+?91[\s-]?)?[6-9]\d{9}\b)"  # Indian 10-digit mobile
    r"|(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b"  # US/Canada
    r"|(?:\+\d{1,3}[\s-]?)?\(?\d{2,4}\)?[\s.-]?\d{3,4}[\s.-]?\d{3,4}\b"  # Generic international
)

# IPv4 address pattern
IPV4_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

# Keys in metadata dictionaries that should never be permanently stored
SENSITIVE_METADATA_KEYS = {
    "authorization",
    "cookie",
    "set-cookie",
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "x-api-key",
}


def scrub_pii(text: Optional[str]) -> str:
    """Scrub personal identifying information from conversational text.

    Redacts:
    - Email addresses -> [EMAIL_REDACTED]
    - Credit/Debit cards -> [CARD_REDACTED]
    - National IDs (Aadhaar, SSN) -> [ID_REDACTED]
    - Phone numbers -> [PHONE_REDACTED]

    Args:
        text: Input string potentially containing personal details.

    Returns:
        Cleaned string with PII replaced by redaction placeholders.
    """
    if not text:
        return ""

    sanitized = text

    # Redact Credit Cards first (to avoid phone regex partial match)
    sanitized = CREDIT_CARD_PATTERN.sub("[CARD_REDACTED]", sanitized)

    # Redact Government IDs
    sanitized = AADHAAR_PATTERN.sub("[ID_REDACTED]", sanitized)
    sanitized = SSN_PATTERN.sub("[ID_REDACTED]", sanitized)

    # Redact Emails
    sanitized = EMAIL_PATTERN.sub("[EMAIL_REDACTED]", sanitized)

    # Redact Phone Numbers
    sanitized = PHONE_PATTERN.sub("[PHONE_REDACTED]", sanitized)

    return sanitized


def anonymize_ip(ip_address: Optional[str]) -> Optional[str]:
    """Anonymize an IP address to preserve regional analytics without storing exact PII.

    For IPv4: replaces the last octet with '0' (e.g. 192.168.1.123 -> 192.168.1.0).
    For IPv6 or invalid: returns redacted placeholder.
    """
    if not ip_address:
        return None

    clean_ip = ip_address.strip()
    if IPV4_PATTERN.match(clean_ip):
        parts = clean_ip.split(".")
        return f"{parts[0]}.{parts[1]}.{parts[2]}.0"
    return "[IP_ANONYMIZED]"


def sanitize_session_metadata(metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Sanitize session metadata dictionary by removing sensitive authentication or PII keys.

    Args:
        metadata: Raw metadata dictionary from headers or client payload.

    Returns:
        Cleaned metadata dictionary safe for persistent storage.
    """
    if not metadata or not isinstance(metadata, dict):
        return {}

    sanitized: Dict[str, Any] = {}
    for key, value in metadata.items():
        lower_key = key.lower()
        if lower_key in SENSITIVE_METADATA_KEYS:
            continue
        if "ip" in lower_key and isinstance(value, str):
            sanitized[key] = anonymize_ip(value)
        elif isinstance(value, str):
            sanitized[key] = scrub_pii(value)
        elif isinstance(value, dict):
            sanitized[key] = sanitize_session_metadata(value)
        else:
            sanitized[key] = value

    return sanitized
