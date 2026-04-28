"""PII scrubber — removes personally identifiable information from all log output.

Runs on EVERY log entry before serialization. Not optional. Not disableable.
PHI must never appear in logs at ANY level (HIPAA requirement).
"""

from __future__ import annotations

import re
from typing import Any

# PII detection patterns — all categories from CONVENTIONS.md
PII_PATTERNS: dict[str, re.Pattern] = {
    "SSN": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "EMAIL": re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
    "PHONE_US": re.compile(r"(?:\(\d{3}\)\s?|\b\d{3}[-.])\d{3}[-.]?\d{4}\b"),
    "CREDIT_CARD": re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"),
    "IP_ADDRESS": re.compile(
        r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
    ),
    "DOB": re.compile(r"\b(?:0[1-9]|1[0-2])/(?:0[1-9]|[12]\d|3[01])/(?:19|20)\d{2}\b"),
    "DRIVERS_LICENSE": re.compile(r"\b[A-Z]\d{7,14}\b"),
}

# Fields that should never be logged, even scrubbed
RESTRICTED_FIELDS: frozenset[str] = frozenset({
    "password", "secret", "token", "api_key", "private_key",
    "phi", "medical_record", "diagnosis", "treatment",
    "health_info", "patient_data", "mrn",
})


def scrub_value(value: str) -> str:
    """Scrub PII from a single string value.

    Args:
        value: String that may contain PII.

    Returns:
        String with all PII replaced by [CATEGORY_REDACTED] markers.
    """
    for pii_type, pattern in PII_PATTERNS.items():
        value = pattern.sub(f"[{pii_type}_REDACTED]", value)
    return value


def scrub_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Scrub PII from all string values in a dictionary.

    Restricted fields are replaced entirely with [RESTRICTED_REDACTED].
    All other string values are pattern-scrubbed.

    Args:
        data: Dictionary that may contain PII in values.

    Returns:
        New dictionary with PII scrubbed.
    """
    result: dict[str, Any] = {}
    for key, value in data.items():
        if key.lower() in RESTRICTED_FIELDS:
            result[key] = "[RESTRICTED_REDACTED]"
        elif isinstance(value, str):
            result[key] = scrub_value(value)
        elif isinstance(value, dict):
            result[key] = scrub_dict(value)
        elif isinstance(value, list):
            result[key] = [
                scrub_value(item) if isinstance(item, str) else item
                for item in value
            ]
        else:
            result[key] = value
    return result


def scrub_log_event(event_dict: dict[str, Any]) -> dict[str, Any]:
    """Scrub PII from a structured log event.

    This is the structlog processor function. It runs on every log entry
    before serialization. Not optional.
    """
    return scrub_dict(event_dict)
