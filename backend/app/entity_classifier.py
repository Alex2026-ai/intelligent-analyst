"""
Entity Classifier - Deterministic row-level classification.

Routes each input row to the correct sanitizer: PERSON | ORGANIZATION | VESSEL | GARBAGE

O(n) complexity. No ML. No fuzzy matching. No watchlist lookups.
"""

import re
from enum import Enum
from typing import Tuple, List


class EntityType(str, Enum):
    """Entity type classification."""
    PERSON = "PERSON"
    ORGANIZATION = "ORGANIZATION"
    VESSEL = "VESSEL"
    GARBAGE = "GARBAGE"


# =============================================================================
# CLASSIFICATION PATTERNS (all case-insensitive)
# =============================================================================

# Vessel prefixes - require word boundary or slash
VESSEL_PREFIXES = {
    'M/V', 'MV', 'MT', 'FV', 'SS', 'YACHT', 'HMS', 'USS', 'RMS',
    'M/T', 'F/V', 'S/S', 'TANKER', 'VESSEL', 'SHIP'
}

# IMO pattern: "IMO" followed by 7 digits (with optional colon/space)
IMO_PATTERN = re.compile(r'\bIMO[:\s]?\d{7}\b', re.IGNORECASE)
IMO_LOOSE_PATTERN = re.compile(r'\bIMO\b', re.IGNORECASE)

# Corporate suffixes
CORPORATE_SUFFIXES = {
    'LLC', 'LTD', 'PLC', 'INC', 'CORP', 'CO', 'COMPANY', 'COMPANIES',
    'SA', 'S.A.', 'AG', 'BV', 'B.V.', 'GMBH', 'SARL', 'SPA', 'S.P.A.',
    'NV', 'N.V.', 'OY', 'OYJ', 'AB', 'AS', 'A/S', 'SE', 'SRL', 'S.R.L.',
    'LIMITED', 'INCORPORATED', 'CORPORATION', 'PTY', 'PROPRIETARY',
    'LP', 'LLP', 'PLLC', 'PC', 'PA', 'NA', 'FSB',
    # International
    'GMBH', 'GMBH.', 'GBMH', 'KG', 'OHG', 'UG',  # German
    'LTDA', 'LTDA.', 'CIA', 'CIA.', 'SAS', 'SASU',  # Spanish/French
    'JSC', 'OJSC', 'CJSC', 'PJSC', 'OAO', 'ZAO', 'PAO',  # Russian
    'AO', 'TOO', 'OOO',  # CIS
    'KK', 'GK', 'YK',  # Japanese
}

# Government/State keywords
GOVT_KEYWORDS = {
    'MINISTRY', 'DEPARTMENT', 'BUREAU', 'AGENCY', 'AUTHORITY',
    'GOVERNMENT', 'GOVT', 'GOV', 'FEDERAL', 'STATE', 'NATIONAL',
    'REPUBLIC', 'KINGDOM', 'EMBASSY', 'CONSULATE', 'COMMISSION',
    'COMMITTEE', 'COUNCIL', 'ADMINISTRATION', 'DIRECTORATE',
    'SECRETARIAT', 'OFFICE', 'SERVICE', 'FORCE', 'MILITARY',
    'ARMY', 'NAVY', 'POLICE', 'CUSTOMS', 'TREASURY',
    'CENTRAL BANK', 'RESERVE BANK', 'PEOPLES BANK',
}

# Logistics keywords
LOGISTICS_KEYWORDS = {
    'LOGISTICS', 'FREIGHT', 'SHIPPING', 'TRANSPORT', 'TRANSPORTATION',
    'CARGO', 'LINES', 'LINE', 'PORT', 'TERMINAL', 'MARITIME',
    'FORWARDING', 'FORWARDERS', 'EXPRESS', 'COURIER', 'DELIVERY',
    'WAREHOUSE', 'WAREHOUSING', 'DISTRIBUTION', 'SUPPLY CHAIN',
    'CONTAINER', 'CONTAINERS', 'TRUCKING', 'HAULAGE', 'CARRIER',
    'AIRLINES', 'AIRWAYS', 'AVIATION', 'AIR CARGO',
}

# Insurance/Finance keywords
FINANCE_KEYWORDS = {
    'INSURANCE', 'ASSURANCE', 'REINSURANCE', 'UNDERWRITING',
    'UNDERWRITERS', 'BROKER', 'BROKERS', 'BROKERAGE',
    'INDEMNITY', 'MUTUAL', 'SYNDICATE', 'SYNDICATION',
    'BANK', 'BANKING', 'BANQUE', 'BANCA', 'BANCO',
    'FINANCE', 'FINANCIAL', 'FINANCING', 'FINANZ',
    'CAPITAL', 'CAPITALS', 'INVESTMENT', 'INVESTMENTS', 'INVESTING',
    'HOLDINGS', 'HOLDING', 'TRUST', 'TRUSTS', 'TRUSTEE',
    'FUND', 'FUNDS', 'ASSET', 'ASSETS', 'MANAGEMENT',
    'SECURITIES', 'EQUITY', 'EQUITIES', 'VENTURES', 'VENTURE',
    'PARTNERS', 'PARTNERSHIP', 'ASSOCIATES', 'ADVISORS', 'ADVISORY',
    'CREDIT', 'LENDING', 'LEASING', 'FACTORING',
}

# Combined organization keywords (for quick lookup)
ORG_KEYWORDS = CORPORATE_SUFFIXES | GOVT_KEYWORDS | LOGISTICS_KEYWORDS | FINANCE_KEYWORDS

# Additional org indicators (less specific but still org-like)
ORG_INDICATORS = {
    'GROUP', 'GROUPS', 'ENTERPRISE', 'ENTERPRISES', 'INDUSTRIES', 'INDUSTRY',
    'INTERNATIONAL', 'INTL', "INT'L", 'GLOBAL', 'WORLDWIDE', 'WORLD',
    'TRADING', 'TRADE', 'TRADERS', 'EXPORT', 'IMPORT', 'EXPORTS', 'IMPORTS',
    'MANUFACTURING', 'MANUFACTURER', 'MANUFACTURERS', 'MFG',
    'CONSTRUCTION', 'ENGINEERING', 'ENGINEERS', 'BUILDERS',
    'SERVICES', 'SERVICE', 'SOLUTIONS', 'SYSTEMS', 'TECHNOLOGIES', 'TECHNOLOGY',
    'PRODUCTS', 'PRODUCTIONS', 'PRODUCTION', 'STUDIO', 'STUDIOS',
    'MEDIA', 'COMMUNICATIONS', 'TELECOM', 'TELECOMMUNICATIONS',
    'ENERGY', 'OIL', 'GAS', 'PETROLEUM', 'PETROL', 'MINING', 'MINERALS',
    'PHARMACEUTICALS', 'PHARMA', 'HEALTHCARE', 'MEDICAL', 'BIOTECH',
    'FOUNDATION', 'INSTITUTE', 'INSTITUTION', 'UNIVERSITY', 'COLLEGE',
    'ASSOCIATION', 'SOCIETY', 'FEDERATION', 'UNION', 'COOPERATIVE',
    'FACTORY', 'PLANT', 'MILL', 'REFINERY', 'WORKS',
}

# Person title prefixes (strong person signal)
PERSON_TITLES = {
    'MR', 'MR.', 'MRS', 'MRS.', 'MS', 'MS.', 'MISS', 'MISS.',
    'DR', 'DR.', 'PROF', 'PROF.', 'PROFESSOR',
    'SIR', 'DAME', 'LORD', 'LADY', 'REV', 'REV.', 'REVEREND',
    'HON', 'HON.', 'HONORABLE', 'HONOURABLE',
    'CAPT', 'CAPT.', 'CAPTAIN', 'COL', 'COL.', 'COLONEL',
    'GEN', 'GEN.', 'GENERAL', 'MAJ', 'MAJ.', 'MAJOR',
    'LT', 'LT.', 'LIEUTENANT', 'SGT', 'SGT.', 'SERGEANT',
    'CPL', 'CPL.', 'CORPORAL', 'PVT', 'PVT.', 'PRIVATE',
    'ADM', 'ADM.', 'ADMIRAL', 'CDR', 'CDR.', 'COMMANDER',
}

# Person name suffixes
PERSON_SUFFIXES = {
    'JR', 'JR.', 'SR', 'SR.', 'II', 'III', 'IV', 'V',
    'PHD', 'PH.D.', 'MD', 'M.D.', 'DDS', 'D.D.S.',
    'ESQ', 'ESQ.', 'CPA', 'C.P.A.', 'MBA', 'M.B.A.', 'JD', 'J.D.',
    'RN', 'R.N.', 'NP', 'N.P.', 'PA', 'P.A.', 'DO', 'D.O.',
}

# Slavic patronymic endings (strong person signal for Russian/Slavic names)
PATRONYMIC_ENDINGS = (
    'OVICH', 'EVICH', 'OVNA', 'EVNA', 'ICHNA', 'INICHNA',
    'OVIC', 'EVIC',  # Serbian/Croatian
    'OWICZ', 'EWICZ',  # Polish
)


def _tokenize(text: str) -> List[str]:
    """Split text into tokens, preserving punctuation markers."""
    # Split on whitespace, keep non-empty
    return [t for t in text.split() if t]


def _has_vessel_prefix(tokens: List[str], original: str) -> Tuple[bool, str]:
    """Check if name starts with vessel prefix."""
    if not tokens:
        return False, ""

    upper = original.upper()

    # Check two-token prefixes first (e.g., "M/V", "M/T")
    for prefix in VESSEL_PREFIXES:
        if '/' in prefix:
            # Look for slash variants
            if upper.startswith(prefix) or upper.startswith(prefix.replace('/', ' ')):
                return True, prefix

    # Check single token prefix
    first = tokens[0].upper().rstrip('.')
    if first in VESSEL_PREFIXES:
        return True, first

    return False, ""


def _has_imo(text: str) -> Tuple[bool, str]:
    """Check for IMO number pattern."""
    # Strict pattern: IMO + 7 digits
    match = IMO_PATTERN.search(text)
    if match:
        # Extract the 7-digit number
        imo_text = match.group()
        digits = re.search(r'\d{7}', imo_text)
        return True, digits.group() if digits else ""

    # Loose pattern: just "IMO" present
    if IMO_LOOSE_PATTERN.search(text):
        return True, ""

    return False, ""


def _has_org_keyword(tokens: List[str]) -> Tuple[bool, str, str]:
    """Check if any token matches organization keywords. Returns (match, keyword, category)."""
    for token in tokens:
        upper = token.upper().rstrip('.,;:')

        if upper in CORPORATE_SUFFIXES:
            return True, upper, "CORPORATE"
        if upper in GOVT_KEYWORDS:
            return True, upper, "GOVERNMENT"
        if upper in LOGISTICS_KEYWORDS:
            return True, upper, "LOGISTICS"
        if upper in FINANCE_KEYWORDS:
            return True, upper, "FINANCE"
        if upper in ORG_INDICATORS:
            return True, upper, "INDICATOR"

    return False, "", ""


def _has_person_title(tokens: List[str]) -> Tuple[bool, str]:
    """Check if first token is a person title."""
    if not tokens:
        return False, ""

    first = tokens[0].upper().rstrip('.')
    if first in PERSON_TITLES or (first + '.') in PERSON_TITLES:
        return True, first

    return False, ""


def _has_person_suffix(tokens: List[str]) -> Tuple[bool, str]:
    """Check if last token is a person suffix."""
    if not tokens:
        return False, ""

    last = tokens[-1].upper().rstrip('.,')
    if last in PERSON_SUFFIXES or (last + '.') in PERSON_SUFFIXES:
        return True, last

    return False, ""


def _has_patronymic(tokens: List[str]) -> bool:
    """Check if any token ends with Slavic patronymic suffix."""
    for token in tokens:
        upper = token.upper()
        for ending in PATRONYMIC_ENDINGS:
            if upper.endswith(ending) and len(upper) > len(ending) + 2:
                return True
    return False


def _is_mostly_alphabetic(text: str) -> bool:
    """Check if text is mostly alphabetic characters."""
    alpha_count = sum(1 for c in text if c.isalpha())
    total = len(text.replace(' ', ''))
    if total == 0:
        return False
    return alpha_count / total >= 0.8


def _numeric_ratio(text: str) -> float:
    """Calculate ratio of digits to total characters."""
    clean = text.replace(' ', '').replace('.', '').replace('-', '').replace(',', '')
    if not clean:
        return 0.0
    digit_count = sum(1 for c in clean if c.isdigit())
    return digit_count / len(clean)


def _is_id_like(text: str) -> bool:
    """Check if text looks like an ID/invoice number."""
    # Long digit runs (5+ digits in a row)
    if re.search(r'\d{5,}', text):
        return True

    # Invoice-like patterns: letters + digits mixed heavily
    # e.g., "INV-2024-001234", "PO12345678"
    if re.match(r'^[A-Z]{2,4}[-/]?\d{4,}', text.upper()):
        return True

    # UUID-like: groups of hex with dashes
    if re.match(r'^[0-9A-F]{8}-[0-9A-F]{4}-', text.upper()):
        return True

    return False


def classify_entity(original_name: str) -> Tuple[str, float, List[str]]:
    """
    Classify an entity name into PERSON | ORGANIZATION | VESSEL | GARBAGE.

    Returns:
        entity_type: EntityType enum value as string
        classification_confidence: 0.0-1.0
        classification_flags: List of classification signals detected

    Deterministic, O(n), no ML, no fuzzy matching.
    """
    flags: List[str] = []

    # A) Pre-normalize (non-destructive)
    if original_name is None:
        return EntityType.GARBAGE.value, 0.0, ["NULL_INPUT"]

    working = " ".join(str(original_name).strip().split())

    # B) Basic GARBAGE detection (empty, too short)
    if not working:
        return EntityType.GARBAGE.value, 0.0, ["EMPTY"]

    if len(working) < 2:
        return EntityType.GARBAGE.value, 0.1, ["TOO_SHORT"]

    # Check for IMO pattern BEFORE numeric ratio check
    # (IMO numbers are highly numeric but NOT garbage)
    has_imo, imo_num = _has_imo(working)
    if has_imo:
        flags.append("IMO_PRESENT")
        if imo_num:
            flags.append(f"IMO_{imo_num}")
        return EntityType.VESSEL.value, 0.95, flags

    # Numeric ratio check (after IMO exception)
    num_ratio = _numeric_ratio(working)
    if num_ratio > 0.35:
        flags.append("NUMERIC_HEAVY")
        return EntityType.GARBAGE.value, 0.2, flags

    # ID-like pattern check
    if _is_id_like(working):
        flags.append("ID_LIKE")
        return EntityType.GARBAGE.value, 0.3, flags

    # Common garbage values
    lower = working.lower()
    if lower in {'n/a', 'na', 'none', 'null', 'unknown', 'tbd', 'test',
                 'xxx', 'zzz', 'aaa', 'abc', '123', 'sample', 'example',
                 'delete', 'remove', 'blank', 'empty', 'no name', 'noname',
                 '-', '--', '---', '.', '..', '...'}:
        flags.append("GARBAGE_VALUE")
        return EntityType.GARBAGE.value, 0.0, flags

    # All same character
    clean_chars = working.replace(' ', '')
    if len(set(clean_chars.lower())) == 1:
        flags.append("REPEATED_CHAR")
        return EntityType.GARBAGE.value, 0.1, flags

    # Tokenize for further analysis
    tokens = _tokenize(working)

    if not tokens:
        return EntityType.GARBAGE.value, 0.0, ["NO_TOKENS"]

    # C) VESSEL detection (prefix-based, IMO already handled above)
    has_prefix, prefix = _has_vessel_prefix(tokens, working)

    if has_prefix:
        flags.append(f"VESSEL_PREFIX_{prefix}")
        return EntityType.VESSEL.value, 0.90, flags

    # D) ORGANIZATION detection
    has_org, org_keyword, org_category = _has_org_keyword(tokens)
    if has_org:
        flags.append(f"ORG_{org_category}")
        flags.append(f"KEYWORD_{org_keyword}")
        confidence = 0.95 if org_category in ("CORPORATE", "GOVERNMENT") else 0.85
        return EntityType.ORGANIZATION.value, confidence, flags

    # E) PERSON detection
    has_title, title = _has_person_title(tokens)
    has_suffix, suffix = _has_person_suffix(tokens)
    has_patron = _has_patronymic(tokens)

    # Strong person signals
    if has_title:
        flags.append(f"TITLE_{title}")
        return EntityType.PERSON.value, 0.95, flags

    if has_suffix:
        flags.append(f"SUFFIX_{suffix}")
        return EntityType.PERSON.value, 0.90, flags

    if has_patron:
        flags.append("PATRONYMIC")
        return EntityType.PERSON.value, 0.90, flags

    # Heuristic: 2-4 tokens, mostly alphabetic, no org keywords = likely PERSON
    if 2 <= len(tokens) <= 4 and _is_mostly_alphabetic(working):
        flags.append("TOKEN_COUNT_PERSON_RANGE")
        flags.append("ALPHABETIC")
        return EntityType.PERSON.value, 0.75, flags

    # F) Fallback
    flags.append("LOW_CERTAINTY")

    if len(tokens) > 4:
        # Long names more likely org
        flags.append("LONG_NAME")
        return EntityType.ORGANIZATION.value, 0.50, flags
    elif len(tokens) == 1:
        # Single token - could be either, lean org for safety
        flags.append("SINGLE_TOKEN")
        return EntityType.ORGANIZATION.value, 0.40, flags
    else:
        # 2-4 tokens but not alphabetic enough
        return EntityType.PERSON.value, 0.50, flags
