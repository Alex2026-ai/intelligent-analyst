"""PII detection patterns — regex-based detection for all categories."""

from __future__ import annotations

import re

# Ordered by specificity (most specific first to avoid partial matches)
PII_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("CREDIT_CARD", re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b")),
    ("MRN", re.compile(r"\bMRN[-:]?\s?\d{5,10}\b", re.IGNORECASE)),
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
    ("PHONE", re.compile(r"(?:\(\d{3}\)\s?|\b\d{3}[-.])\d{3}[-.]?\d{4}\b")),
    ("DOB", re.compile(r"\b(?:0[1-9]|1[0-2])/(?:0[1-9]|[12]\d|3[01])/(?:19|20)\d{2}\b")),
    ("IP_ADDRESS", re.compile(
        r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
    )),
    ("DRIVERS_LICENSE", re.compile(r"\b[A-Z]\d{7,14}\b")),
]


def detect_pii(text: str) -> list[tuple[str, str, int, int]]:
    """Detect PII instances in text.

    Returns list of (category, matched_text, start, end) tuples,
    ordered by position in text.
    """
    findings: list[tuple[str, str, int, int]] = []
    for category, pattern in PII_PATTERNS:
        for match in pattern.finditer(text):
            findings.append((category, match.group(), match.start(), match.end()))
    # Sort by position (start), then by length descending (prefer longer matches)
    findings.sort(key=lambda f: (f[2], -(f[3] - f[2])))
    return findings
