"""
Vessel Name Sanitization - Deterministic normalization.

Extracts vessel name, prefix, and IMO number from raw input.
No fuzzy corrections. No watchlist matching. O(n) complexity.
"""

import re
from dataclasses import dataclass
from typing import Optional, List


@dataclass
class VesselSanitizationResult:
    """Result of vessel name sanitization."""
    original: str
    sanitized_name: str
    vessel_name: str
    imo_number: str
    vessel_prefix: str
    sanitization_confidence: float
    sanitization_flags: List[str]
    decision_path: str


# Vessel prefixes (normalized forms)
VESSEL_PREFIXES = {
    'M/V': 'M/V',
    'MV': 'M/V',
    'M.V.': 'M/V',
    'M/T': 'M/T',
    'MT': 'M/T',
    'M.T.': 'M/T',
    'F/V': 'F/V',
    'FV': 'F/V',
    'F.V.': 'F/V',
    'S/S': 'S/S',
    'SS': 'S/S',
    'S.S.': 'S/S',
    'YACHT': 'YACHT',
    'HMS': 'HMS',
    'USS': 'USS',
    'RMS': 'RMS',
    'TANKER': 'TANKER',
    'VESSEL': 'VESSEL',
    'SHIP': 'SHIP',
}

# IMO pattern: "IMO" followed by 7 digits
IMO_PATTERN = re.compile(r'\bIMO[:\s]?(\d{7})\b', re.IGNORECASE)
IMO_STANDALONE = re.compile(r'\b(\d{7})\b')  # 7 digits alone (only if IMO context)


def _normalize_whitespace(text: str) -> str:
    """Normalize whitespace and remove duplicate punctuation."""
    # Collapse multiple spaces
    text = ' '.join(text.split())
    # Remove duplicate punctuation (but keep single)
    text = re.sub(r'([.,;:!?])\1+', r'\1', text)
    return text.strip()


def _extract_prefix(tokens: List[str], original: str) -> tuple:
    """Extract vessel prefix from tokens. Returns (prefix, remaining_tokens)."""
    if not tokens:
        return "", tokens

    upper_original = original.upper()

    # Check for slash variants first (e.g., "M/V", "M/T")
    for raw, normalized in VESSEL_PREFIXES.items():
        if '/' in raw:
            # Check if original starts with this prefix
            if upper_original.startswith(raw):
                # Remove prefix from tokens
                prefix_len = len(raw)
                remaining = original[prefix_len:].strip()
                return normalized, remaining.split() if remaining else []
            # Also check space variant (e.g., "M / V")
            space_variant = raw.replace('/', ' / ')
            if upper_original.startswith(space_variant):
                prefix_len = len(space_variant)
                remaining = original[prefix_len:].strip()
                return normalized, remaining.split() if remaining else []

    # Check first token
    first = tokens[0].upper().rstrip('.')
    if first in VESSEL_PREFIXES:
        return VESSEL_PREFIXES[first], tokens[1:]

    # Check two-token prefix (e.g., "M", "/", "V" or "M", "V")
    if len(tokens) >= 2:
        combined = (tokens[0] + tokens[1]).upper().replace('.', '')
        if combined in VESSEL_PREFIXES:
            return VESSEL_PREFIXES[combined], tokens[2:]

    return "", tokens


def _extract_imo(text: str) -> tuple:
    """Extract IMO number from text. Returns (imo_number, text_without_imo)."""
    # Look for explicit IMO pattern
    match = IMO_PATTERN.search(text)
    if match:
        imo = match.group(1)
        # Remove the IMO portion from text
        text_clean = text[:match.start()] + text[match.end():]
        text_clean = _normalize_whitespace(text_clean)
        return imo, text_clean

    return "", text


def sanitize_vessel_name(original_name: str) -> dict:
    """
    Sanitize a vessel name.

    Extracts:
    - vessel_name: The actual vessel name (prefix removed)
    - imo_number: IMO number if present (7 digits)
    - vessel_prefix: Normalized prefix (M/V, M/T, etc.)

    Returns dict with all fields for consistency with other sanitizers.

    No fuzzy corrections. No watchlist matching.
    """
    flags: List[str] = []
    decision_path = "NAME_ONLY"

    # Handle None/empty
    if original_name is None:
        original_name = ""
    raw = str(original_name).strip()

    # Check for blank/garbage
    if not raw:
        return {
            "original": raw,
            "sanitized_name": "",
            "vessel_name": "",
            "imo_number": "",
            "vessel_prefix": "",
            "sanitization_confidence": 0.0,
            "sanitization_flags": ["BLANK"],
            "decision_path": "GARBAGE",
        }

    if len(raw) < 2:
        return {
            "original": raw,
            "sanitized_name": raw,
            "vessel_name": raw,
            "imo_number": "",
            "vessel_prefix": "",
            "sanitization_confidence": 0.1,
            "sanitization_flags": ["TOO_SHORT"],
            "decision_path": "GARBAGE",
        }

    # Normalize whitespace
    working = _normalize_whitespace(raw)

    # Extract IMO number first
    imo_number, working_no_imo = _extract_imo(working)
    if imo_number:
        flags.append("IMO_EXTRACTED")
        decision_path = "IMO_EXTRACTED"
        working = working_no_imo

    # Tokenize
    tokens = working.split()

    # Extract prefix
    prefix, remaining_tokens = _extract_prefix(tokens, working)
    if prefix:
        flags.append(f"PREFIX_{prefix.replace('/', '_')}")
        if decision_path == "NAME_ONLY":
            decision_path = "PREFIX_ONLY"
        elif decision_path == "IMO_EXTRACTED":
            decision_path = "IMO_AND_PREFIX"

    # Build vessel name from remaining tokens
    if remaining_tokens:
        vessel_name = ' '.join(remaining_tokens)
    else:
        vessel_name = working  # No prefix found, use original

    # Build sanitized name (prefix + vessel name)
    if prefix and vessel_name:
        sanitized_name = f"{prefix} {vessel_name}"
    elif prefix:
        sanitized_name = prefix
    else:
        sanitized_name = vessel_name

    # Normalize to uppercase for consistency
    sanitized_name = sanitized_name.upper()
    vessel_name = vessel_name.upper()

    # Calculate confidence
    confidence = 0.7  # Base confidence for vessel
    if imo_number:
        confidence += 0.2
    if prefix:
        confidence += 0.1
    confidence = min(confidence, 1.0)

    return {
        "original": raw,
        "sanitized_name": sanitized_name,
        "vessel_name": vessel_name,
        "imo_number": imo_number,
        "vessel_prefix": prefix,
        "sanitization_confidence": confidence,
        "sanitization_flags": flags,
        "decision_path": decision_path,
    }


def sanitize_vessel_batch(names: list) -> list:
    """Sanitize a batch of vessel names. O(n) total."""
    return [sanitize_vessel_name(name) for name in names]
