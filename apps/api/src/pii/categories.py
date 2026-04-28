"""PII category definitions and severity levels."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Severity(str, Enum):
    """PII severity levels."""
    CRITICAL = "critical"   # SSN, credit card, MRN
    HIGH = "high"           # Names, DOB, driver's license
    MEDIUM = "medium"       # Email, phone, address
    LOW = "low"             # IP address


@dataclass(frozen=True)
class PIICategory:
    """Definition of a PII category."""
    name: str
    token_prefix: str
    severity: Severity


# All supported PII categories
CATEGORIES: dict[str, PIICategory] = {
    "NAME": PIICategory("NAME", "NAME", Severity.HIGH),
    "SSN": PIICategory("SSN", "SSN", Severity.CRITICAL),
    "EMAIL": PIICategory("EMAIL", "EMAIL", Severity.MEDIUM),
    "PHONE": PIICategory("PHONE", "PHONE", Severity.MEDIUM),
    "DOB": PIICategory("DOB", "DOB", Severity.HIGH),
    "MRN": PIICategory("MRN", "MRN", Severity.CRITICAL),
    "CREDIT_CARD": PIICategory("CREDIT_CARD", "CC", Severity.CRITICAL),
    "ADDRESS": PIICategory("ADDRESS", "ADDR", Severity.MEDIUM),
    "IP_ADDRESS": PIICategory("IP_ADDRESS", "IP", Severity.LOW),
    "DRIVERS_LICENSE": PIICategory("DRIVERS_LICENSE", "DL", Severity.HIGH),
}
