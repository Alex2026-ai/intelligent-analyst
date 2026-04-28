"""
Person name sanitization (NO watchlist matching).

Pure string transformation for data quality improvement.
This is NOT sanctions screening - that's Global RADAR's job.

Goal: Standardize messy name data before it reaches screening systems.
"""

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional, Tuple


# Title prefixes to strip
TITLE_PREFIXES = {
    'mr', 'mrs', 'ms', 'miss', 'dr', 'prof', 'professor',
    'sir', 'dame', 'lord', 'lady', 'rev', 'reverend',
    'hon', 'honorable', 'capt', 'captain', 'col', 'colonel',
    'gen', 'general', 'maj', 'major', 'lt', 'lieutenant',
    'sgt', 'sergeant', 'cpl', 'corporal', 'pvt', 'private',
}

# Suffixes to strip (NOT single letters - those may be patronymic initials)
NAME_SUFFIXES = {
    'jr', 'sr', 'ii', 'iii', 'iv',  # Roman numerals (not single 'i' or 'v')
    'phd', 'md', 'dds', 'esq', 'cpa', 'mba', 'jd',
    'rn', 'np', 'pa', 'do', 'dvm', 'od',
}

# Garbage patterns
GARBAGE_PATTERNS = {
    'n/a', 'na', 'none', 'null', 'unknown', 'tbd', 'test',
    'xxx', 'zzz', 'aaa', 'abc', '123', 'sample', 'example',
    'delete', 'remove', 'blank', 'empty', 'no name', 'noname',
}

# Slavic patronymic endings (transliterated)
# Male: -ович (-ovich), -евич (-evich), -ич (-ich)
# Female: -овна (-ovna), -евна (-evna), -ична (-ichna), -инична (-inichna)
PATRONYMIC_ENDINGS = (
    'ovich', 'evich', 'ich',  # Male
    'ovna', 'evna', 'ichna', 'inichna',  # Female
    'ovic', 'evic',  # Serbian/Croatian variants
    'owicz', 'ewicz',  # Polish variants
)

# Slavic surname endings (to distinguish surnames from first names)
# These suffixes indicate a word is a surname, not a first name
SLAVIC_SURNAME_ENDINGS = (
    # Russian/Ukrainian masculine
    'ov', 'ev', 'in', 'yn', 'ko', 'uk', 'yk', 'ak', 'ek', 'ik',
    'sky', 'ski', 'skiy', 'skyi', 'ckiy', 'cki',
    # Russian/Ukrainian feminine
    'ova', 'eva', 'ina', 'yna',
    'skaya', 'skya', 'ska', 'cka', 'ckaya',
    # Polish
    'ski', 'ska', 'cki', 'cka', 'wicz', 'icz',
    # Georgian
    'shvili', 'dze', 'adze',
    # Armenian
    'yan', 'ian', 'ants',
)


@dataclass
class SanitizationResult:
    """Result of name sanitization."""
    original: str
    sanitized: str
    first_name: Optional[str]
    middle_name: Optional[str]
    last_name: Optional[str]
    suffix: Optional[str]
    format_standardized: bool  # True if converted to "LAST, FIRST" format
    confidence: float  # 0-1 parsing confidence
    flags: list  # List of quality flags


def normalize_unicode(text: str) -> str:
    """Normalize unicode characters to ASCII equivalents."""
    # NFKD normalization decomposes characters
    normalized = unicodedata.normalize('NFKD', text)
    # Keep only ASCII characters
    ascii_text = normalized.encode('ascii', 'ignore').decode('ascii')
    return ascii_text


def strip_titles(name: str) -> Tuple[str, list]:
    """Strip title prefixes from name."""
    tokens = name.split()
    stripped_titles = []

    while tokens:
        token_lower = tokens[0].lower().rstrip('.')
        if token_lower in TITLE_PREFIXES:
            stripped_titles.append(tokens.pop(0))
        else:
            break

    return ' '.join(tokens), stripped_titles


def strip_suffixes(name: str) -> Tuple[str, Optional[str]]:
    """Strip suffixes from name."""
    tokens = name.split()
    suffix = None

    while tokens:
        token_lower = tokens[-1].lower().rstrip('.,')
        if token_lower in NAME_SUFFIXES:
            suffix = tokens.pop()
        else:
            break

    return ' '.join(tokens), suffix


def is_patronymic(token: str) -> bool:
    """Check if a token is a Slavic patronymic."""
    if not token or len(token) < 4:
        return False
    lower = token.lower()
    return any(lower.endswith(ending) for ending in PATRONYMIC_ENDINGS)


def is_slavic_surname(token: str) -> bool:
    """Check if a token looks like a Slavic surname based on suffix."""
    if not token or len(token) < 3:
        return False
    lower = token.lower()
    # Check surname endings, but not if it also matches patronymic
    # (patronymics like "Ivanovich" end in "ich" which could match "ovich")
    if is_patronymic(token):
        return False
    return any(lower.endswith(ending) for ending in SLAVIC_SURNAME_ENDINGS)


def detect_format(name: str) -> str:
    """Detect name format: LAST_FIRST, FIRST_LAST, SLAVIC, or UNKNOWN."""
    if ',' in name:
        return 'LAST_FIRST'

    tokens = name.split()
    if len(tokens) >= 2:
        # Check for Slavic "LAST FIRST PATRONYMIC" format
        if len(tokens) >= 3 and is_patronymic(tokens[-1]):
            return 'SLAVIC'

        # Heuristic: if first token is ALL CAPS and longer, might be LAST FIRST
        if tokens[0].isupper() and len(tokens[0]) > 3:
            # Check if pattern looks like "SMITH JOHN" vs "John Smith"
            if all(t.isupper() for t in tokens):
                return 'AMBIGUOUS_CAPS'
        return 'FIRST_LAST'

    return 'UNKNOWN'


def parse_name_parts(name: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Parse name into (first, middle, last) parts.

    Handles multiple formats:
    - "LAST, FIRST MIDDLE" (comma-separated)
    - "LAST FIRST PATRONYMIC" (Slavic format)
    - "FIRST MIDDLE LAST" (Western format)
    """
    name = name.strip()

    if not name:
        return None, None, None

    # Handle "LAST, FIRST MIDDLE" format
    if ',' in name:
        parts = name.split(',', 1)
        last_name = parts[0].strip()
        remainder = parts[1].strip() if len(parts) > 1 else ''

        if remainder:
            tokens = remainder.split()
            first_name = tokens[0] if tokens else None
            middle_name = ' '.join(tokens[1:]) if len(tokens) > 1 else None
        else:
            first_name = None
            middle_name = None

        return first_name, middle_name, last_name

    tokens = name.split()

    if len(tokens) == 1:
        # Single name - treat as last name (more conservative for screening)
        return None, None, tokens[0]

    # Check for Slavic names with patronymic
    # Pattern: 3+ tokens where last token is patronymic
    if len(tokens) >= 3 and is_patronymic(tokens[-1]):
        # Determine order: "LAST FIRST PATRONYMIC" vs "FIRST LAST PATRONYMIC"
        first_is_surname = is_slavic_surname(tokens[0])
        second_is_surname = is_slavic_surname(tokens[1])

        if first_is_surname and not second_is_surname:
            # "LAST FIRST PATRONYMIC" (official Russian format)
            # e.g., "RUBTSOVA NATPLYA ALEKSANDROVNA"
            last_name = tokens[0]
            first_name = tokens[1]
            patronymic = ' '.join(tokens[2:])
        elif second_is_surname and not first_is_surname:
            # "FIRST LAST PATRONYMIC" (Western-influenced format)
            # e.g., "OLEG TSARYOV ANATOLEVICH"
            first_name = tokens[0]
            last_name = tokens[1]
            patronymic = ' '.join(tokens[2:])
        else:
            # Ambiguous - default to "LAST FIRST PATRONYMIC" (official format)
            last_name = tokens[0]
            first_name = tokens[1]
            patronymic = ' '.join(tokens[2:])

        return first_name, patronymic, last_name

    # Check for 2-token Slavic where second is patronymic
    # Format: "SURNAME PATRONYMIC" (missing first name)
    # e.g., "RYSKIN MARKOVICH", "PATRUSHEV NIKOLAYEVICH"
    if len(tokens) == 2 and is_patronymic(tokens[-1]):
        # Treat as LAST + PATRONYMIC (no first name)
        # The first token is the surname, second is patronymic as middle
        return None, tokens[1], tokens[0]

    # Default: "FIRST MIDDLE LAST" (Western format)
    if len(tokens) == 2:
        return tokens[0], None, tokens[1]
    else:
        return tokens[0], ' '.join(tokens[1:-1]), tokens[-1]


def is_garbage(name: str) -> bool:
    """Check if name is garbage/placeholder."""
    if not name or not name.strip():
        return True

    clean = name.strip().lower()

    # Check garbage patterns
    if clean in GARBAGE_PATTERNS:
        return True

    # All same character
    if len(set(clean.replace(' ', ''))) == 1:
        return True

    # Too short
    if len(clean) < 2:
        return True

    return False


def is_numeric(name: str) -> bool:
    """Check if name is primarily numeric."""
    clean = name.replace(' ', '').replace('.', '').replace('-', '').replace(',', '')
    if not clean:
        return False

    digit_count = sum(1 for c in clean if c.isdigit())
    return digit_count / len(clean) > 0.5


def sanitize_person_name_only(raw: str) -> SanitizationResult:
    """
    Sanitize a person name WITHOUT watchlist matching.

    Pure string transformation - O(1) per name.

    Returns standardized format: "LAST, FIRST MIDDLE"
    """
    flags = []
    confidence = 1.0

    # Handle None/empty
    if raw is None:
        raw = ''
    raw = str(raw).strip()

    # Check for blank
    if not raw:
        return SanitizationResult(
            original=raw,
            sanitized='',
            first_name=None,
            middle_name=None,
            last_name=None,
            suffix=None,
            format_standardized=False,
            confidence=0.0,
            flags=['BLANK']
        )

    # Check for garbage
    if is_garbage(raw):
        flags.append('GARBAGE')
        confidence = 0.0
        return SanitizationResult(
            original=raw,
            sanitized=raw,
            first_name=None,
            middle_name=None,
            last_name=None,
            suffix=None,
            format_standardized=False,
            confidence=confidence,
            flags=flags
        )

    # Check for numeric
    if is_numeric(raw):
        flags.append('NUMERIC')
        confidence = 0.1
        return SanitizationResult(
            original=raw,
            sanitized=raw,
            first_name=None,
            middle_name=None,
            last_name=None,
            suffix=None,
            format_standardized=False,
            confidence=confidence,
            flags=flags
        )

    # Start sanitization
    working = raw

    # Normalize unicode
    working = normalize_unicode(working)
    if working != raw:
        flags.append('UNICODE_NORMALIZED')

    # Normalize whitespace
    working = ' '.join(working.split())

    # Normalize dot-separated names (e.g., "FIRST.MIDDLE.LAST" → "FIRST MIDDLE LAST")
    # Only if no spaces and multiple dots (likely a dot-separated name, not abbreviation)
    if ' ' not in working and working.count('.') >= 2:
        working = working.replace('.', ' ')
        working = ' '.join(working.split())  # Clean up extra spaces
        flags.append('DOT_NORMALIZED')

    # Strip titles
    working, stripped_titles = strip_titles(working)
    if stripped_titles:
        flags.append('TITLE_STRIPPED')

    # Strip suffixes
    working, suffix = strip_suffixes(working)
    if suffix:
        flags.append('SUFFIX_STRIPPED')

    # Check length after stripping
    if len(working) < 2:
        flags.append('TOO_SHORT')
        confidence = 0.2

    # Detect original format
    original_format = detect_format(working)

    # Parse name parts
    first_name, middle_name, last_name = parse_name_parts(working)

    # Flag Slavic format detection
    if original_format == 'SLAVIC':
        flags.append('SLAVIC_FORMAT')
        # Higher confidence for Slavic detection - patronymic is strong signal
        confidence = min(confidence, 0.95)

    # Assess parsing confidence
    if first_name and last_name:
        confidence = min(confidence, 0.9)
        if len(first_name) == 1:
            flags.append('FIRST_INITIAL_ONLY')
            # Initials are common and valid - don't penalize heavily
            confidence = min(confidence, 0.85)
    elif last_name and not first_name:
        flags.append('LAST_NAME_ONLY')
        # Single-word names are valid (orgs, nicknames) - auto-resolve
        confidence = min(confidence, 0.85)
    elif not last_name:
        flags.append('PARSE_FAILED')
        confidence = min(confidence, 0.3)

    # Build standardized output: "LAST, FIRST MIDDLE"
    format_standardized = False
    if last_name:
        parts = [last_name.upper()]
        if first_name or middle_name:
            first_parts = []
            if first_name:
                first_parts.append(first_name.upper())
            if middle_name:
                first_parts.append(middle_name.upper())
            parts.append(', ')
            parts.append(' '.join(first_parts))

        sanitized = ''.join(parts)

        # Check if format changed
        if original_format != 'LAST_FIRST':
            format_standardized = True
            flags.append('FORMAT_STANDARDIZED')
    else:
        sanitized = working.upper()

    return SanitizationResult(
        original=raw,
        sanitized=sanitized,
        first_name=first_name.upper() if first_name else None,
        middle_name=middle_name.upper() if middle_name else None,
        last_name=last_name.upper() if last_name else None,
        suffix=suffix.upper() if suffix else None,
        format_standardized=format_standardized,
        confidence=confidence,
        flags=flags
    )


def sanitize_batch(names: list) -> list:
    """Sanitize a batch of names. O(n) total."""
    return [sanitize_person_name_only(name) for name in names]
