"""
Organization Name Sanitization - Deterministic normalization.

Normalizes organization names, extracts legal suffixes, categorizes org type.
No fuzzy corrections. No watchlist matching. O(n) complexity.
"""

import re
from dataclasses import dataclass
from typing import Optional, List, Tuple


@dataclass
class OrgSanitizationResult:
    """Result of organization name sanitization."""
    original: str
    sanitized_name: str
    org_name: str
    legal_suffix: str
    org_category: str
    sanitization_confidence: float
    sanitization_flags: List[str]
    decision_path: str


# Legal suffixes by category (uppercase for matching)
CORPORATE_SUFFIXES = {
    # US
    'LLC', 'L.L.C.', 'INC', 'INC.', 'INCORPORATED',
    'CORP', 'CORP.', 'CORPORATION',
    'CO', 'CO.', 'COMPANY', 'COMPANIES',
    'LTD', 'LTD.', 'LIMITED',
    'LP', 'L.P.', 'LLP', 'L.L.P.', 'PLLC', 'P.L.L.C.',
    'PC', 'P.C.', 'PA', 'P.A.', 'NA', 'N.A.', 'FSB', 'F.S.B.',
    # UK
    'PLC', 'P.L.C.',
    # German
    'GMBH', 'GMBH.', 'AG', 'A.G.', 'KG', 'K.G.', 'OHG', 'UG',
    # French
    'SA', 'S.A.', 'SARL', 'S.A.R.L.', 'SAS', 'S.A.S.', 'SASU',
    # Spanish/Latin
    'SL', 'S.L.', 'SRL', 'S.R.L.', 'LTDA', 'LTDA.', 'CIA', 'CIA.',
    # Italian
    'SPA', 'S.P.A.', 'SRL', 'S.R.L.',
    # Dutch/Belgian
    'NV', 'N.V.', 'BV', 'B.V.',
    # Nordic
    'AB', 'A.B.', 'AS', 'A.S.', 'A/S', 'OY', 'OYJ', 'ASA',
    # European
    'SE', 'S.E.',
    # Australian
    'PTY', 'PROPRIETARY',
    # Russian/CIS
    'OAO', 'ZAO', 'PAO', 'OOO', 'AO', 'TOO',
    'JSC', 'OJSC', 'CJSC', 'PJSC',
    # Japanese
    'KK', 'GK', 'YK',
    # Other
    'PTE', 'PTE.', 'SDN', 'SDN.', 'BHD', 'BHD.',
}

# Government keywords
GOVT_KEYWORDS = {
    'MINISTRY', 'DEPARTMENT', 'DEPT', 'BUREAU', 'AGENCY', 'AUTHORITY',
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

# Insurance keywords
INSURANCE_KEYWORDS = {
    'INSURANCE', 'ASSURANCE', 'REINSURANCE', 'UNDERWRITING',
    'UNDERWRITERS', 'BROKER', 'BROKERS', 'BROKERAGE',
    'INDEMNITY', 'MUTUAL', 'SYNDICATE', 'SYNDICATION',
    'ACTUARIAL', 'CLAIMS', 'ADJUSTER', 'ADJUSTERS',
}

# Finance keywords
FINANCE_KEYWORDS = {
    'BANK', 'BANKING', 'BANQUE', 'BANCA', 'BANCO',
    'FINANCE', 'FINANCIAL', 'FINANCING', 'FINANZ',
    'CAPITAL', 'CAPITALS', 'INVESTMENT', 'INVESTMENTS', 'INVESTING',
    'HOLDINGS', 'HOLDING', 'TRUST', 'TRUSTS', 'TRUSTEE',
    'FUND', 'FUNDS', 'ASSET', 'ASSETS', 'MANAGEMENT',
    'SECURITIES', 'EQUITY', 'EQUITIES', 'VENTURES', 'VENTURE',
    'PARTNERS', 'PARTNERSHIP', 'ASSOCIATES', 'ADVISORS', 'ADVISORY',
    'CREDIT', 'LENDING', 'LEASING', 'FACTORING',
}

# Suffix normalization map (normalize variations to canonical form)
SUFFIX_NORMALIZE = {
    'L.L.C.': 'LLC',
    'INC.': 'INC',
    'INCORPORATED': 'INC',
    'CORP.': 'CORP',
    'CORPORATION': 'CORP',
    'CO.': 'CO',
    'COMPANY': 'CO',
    'COMPANIES': 'CO',
    'LTD.': 'LTD',
    'LIMITED': 'LTD',
    'L.P.': 'LP',
    'L.L.P.': 'LLP',
    'P.L.L.C.': 'PLLC',
    'P.C.': 'PC',
    'P.A.': 'PA',
    'N.A.': 'NA',
    'F.S.B.': 'FSB',
    'P.L.C.': 'PLC',
    'GMBH.': 'GMBH',
    'A.G.': 'AG',
    'K.G.': 'KG',
    'S.A.': 'SA',
    'S.A.R.L.': 'SARL',
    'S.A.S.': 'SAS',
    'S.L.': 'SL',
    'S.R.L.': 'SRL',
    'LTDA.': 'LTDA',
    'CIA.': 'CIA',
    'S.P.A.': 'SPA',
    'N.V.': 'NV',
    'B.V.': 'BV',
    'A.B.': 'AB',
    'A.S.': 'AS',
    'S.E.': 'SE',
    'PTE.': 'PTE',
    'SDN.': 'SDN',
    'BHD.': 'BHD',
}


def _normalize_whitespace(text: str) -> str:
    """Normalize whitespace and remove duplicate punctuation."""
    # Collapse multiple spaces
    text = ' '.join(text.split())
    # Remove duplicate punctuation
    text = re.sub(r'([.,;:!?])\1+', r'\1', text)
    return text.strip()


def _extract_legal_suffix(tokens: List[str]) -> Tuple[List[str], str, str]:
    """
    Extract legal suffix from end of token list.
    Returns (remaining_tokens, suffix, normalized_suffix).
    """
    if not tokens:
        return tokens, "", ""

    # Check last 1-2 tokens for suffix
    for num_tokens in [2, 1]:
        if len(tokens) >= num_tokens:
            # Try combining last N tokens
            candidate = ' '.join(tokens[-num_tokens:]).upper()
            candidate_clean = candidate.replace('.', '').replace(',', '')

            # Check if it's a known suffix
            if candidate_clean in CORPORATE_SUFFIXES or candidate in CORPORATE_SUFFIXES:
                remaining = tokens[:-num_tokens]
                # Normalize suffix
                normalized = SUFFIX_NORMALIZE.get(candidate, candidate_clean)
                return remaining, candidate, normalized

            # Also check single token
            if num_tokens == 1:
                single = tokens[-1].upper().rstrip('.,')
                if single in CORPORATE_SUFFIXES:
                    remaining = tokens[:-1]
                    normalized = SUFFIX_NORMALIZE.get(single, single)
                    return remaining, single, normalized

    return tokens, "", ""


def _categorize_org(text: str, tokens: List[str]) -> str:
    """Categorize organization type based on keywords."""
    upper_text = text.upper()
    upper_tokens = [t.upper() for t in tokens]

    # Check in order of specificity
    for keyword in GOVT_KEYWORDS:
        if keyword in upper_text or keyword in upper_tokens:
            return "GOVERNMENT"

    for keyword in INSURANCE_KEYWORDS:
        if keyword in upper_text or keyword in upper_tokens:
            return "INSURANCE"

    for keyword in FINANCE_KEYWORDS:
        if keyword in upper_text or keyword in upper_tokens:
            return "FINANCE"

    for keyword in LOGISTICS_KEYWORDS:
        if keyword in upper_text or keyword in upper_tokens:
            return "LOGISTICS"

    return "COMPANY"


def sanitize_organization_name(original_name: str) -> dict:
    """
    Sanitize an organization name.

    Extracts:
    - org_name: Main organization name (suffix removed)
    - legal_suffix: Detected legal suffix (normalized)
    - org_category: GOVERNMENT | LOGISTICS | INSURANCE | FINANCE | COMPANY | OTHER

    Returns dict with all fields for consistency with other sanitizers.

    No fuzzy corrections. No watchlist matching.
    """
    flags: List[str] = []
    decision_path = "NORMALIZED"

    # Handle None/empty
    if original_name is None:
        original_name = ""
    raw = str(original_name).strip()

    # Check for blank/garbage
    if not raw:
        return {
            "original": raw,
            "sanitized_name": "",
            "org_name": "",
            "legal_suffix": "",
            "org_category": "OTHER",
            "sanitization_confidence": 0.0,
            "sanitization_flags": ["BLANK"],
            "decision_path": "GARBAGE",
        }

    if len(raw) < 2:
        return {
            "original": raw,
            "sanitized_name": raw,
            "org_name": raw,
            "legal_suffix": "",
            "org_category": "OTHER",
            "sanitization_confidence": 0.1,
            "sanitization_flags": ["TOO_SHORT"],
            "decision_path": "GARBAGE",
        }

    # Normalize whitespace
    working = _normalize_whitespace(raw)

    # Tokenize
    tokens = working.split()

    # Extract legal suffix
    remaining_tokens, raw_suffix, normalized_suffix = _extract_legal_suffix(tokens)

    if normalized_suffix:
        flags.append(f"SUFFIX_{normalized_suffix}")
        decision_path = "SUFFIX_EXTRACTED"
        org_name = ' '.join(remaining_tokens) if remaining_tokens else working
    else:
        org_name = working

    # Categorize organization
    org_category = _categorize_org(working, tokens)
    flags.append(f"CATEGORY_{org_category}")

    # Build sanitized name (uppercase for consistency)
    sanitized_name = working.upper()
    org_name = org_name.upper()

    # Calculate confidence
    confidence = 0.7  # Base confidence
    if normalized_suffix:
        confidence += 0.2  # Strong signal from legal suffix
    if org_category != "COMPANY":
        confidence += 0.1  # Strong signal from category keywords
    confidence = min(confidence, 1.0)

    return {
        "original": raw,
        "sanitized_name": sanitized_name,
        "org_name": org_name,
        "legal_suffix": normalized_suffix,
        "org_category": org_category,
        "sanitization_confidence": confidence,
        "sanitization_flags": flags,
        "decision_path": decision_path,
    }


def sanitize_org_batch(names: list) -> list:
    """Sanitize a batch of organization names. O(n) total."""
    return [sanitize_organization_name(name) for name in names]
