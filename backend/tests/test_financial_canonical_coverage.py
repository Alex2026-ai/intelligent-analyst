"""Financial Canonical Coverage — Regression Tests.

Validates that major financial institutions resolve at L1 (deterministic)
and do not silently fall through to L4 due to missing canonical coverage.

Added: 2026-03-18, after BATCH-D4B4DDCE investigation revealed
"Fidelity Investments" was absent from canonicals/aliases.
"""

import os
import re
import pytest

# ---------------------------------------------------------------------------
# Fixtures: extract canonical data from server module without full import
# ---------------------------------------------------------------------------

_SERVER_PATH = os.path.join(
    os.path.dirname(__file__), "..", "app", "server_enterprise_golden.py"
)


@pytest.fixture(scope="module")
def canonical_data():
    """Load CANONICALS list and KNOWN_PARENTS dict from server source."""
    with open(_SERVER_PATH, "r") as f:
        content = f.read()

    # Extract canonical list definitions
    start = content.find("CANONICALS_TECH = [")
    end = content.find("KNOWN_PARENTS = {")
    exec(content[start:end], globals())

    canonicals = (
        CANONICALS_TECH + CANONICALS_ENTERPRISE + CANONICALS_DATA
        + CANONICALS_INFRASTRUCTURE + CANONICALS_PHARMA + CANONICALS_FINANCIAL
        + CANONICALS_CONSULTING + CANONICALS_CONSUMER_ELECTRONICS + CANONICALS_AUTOMOTIVE
        + CANONICALS_RETAIL_FOOD + CANONICALS_STREAMING_MEDIA
        + CANONICALS_ENERGY + CANONICALS_TELECOM + CANONICALS_AEROSPACE_DEFENSE
        + CANONICALS_INDUSTRIAL + CANONICALS_INSURANCE + CANONICALS_AIRLINES
        + CANONICALS_LOGISTICS + CANONICALS_HOSPITALITY + CANONICALS_MEDIA_ENTERTAINMENT
        + CANONICALS_CHEMICALS + CANONICALS_HEALTHCARE_SERVICES + CANONICALS_MEDICAL_DEVICES
        + CANONICALS_FINTECH + CANONICALS_CYBERSECURITY + CANONICALS_REAL_ESTATE
        + CANONICALS_ECOMMERCE_RETAIL
    )

    # Extract KNOWN_PARENTS
    kp_start = content.find("KNOWN_PARENTS = {")
    kp_end = content.find("\n}", kp_start) + 2
    local_ns = {}
    exec(content[kp_start:kp_end], local_ns)
    known_parents = local_ns["KNOWN_PARENTS"]

    return {
        "canonicals": canonicals,
        "canonicals_financial": CANONICALS_FINANCIAL,
        "known_parents": known_parents,
        "canonical_set_lower": {c.lower() for c in canonicals},
        "kp_exact": {k.lower(): v for k, v in known_parents.items()},
    }


# ---------------------------------------------------------------------------
# 1. Canonical presence — key financial entities must be in the list
# ---------------------------------------------------------------------------

REQUIRED_FINANCIAL_CANONICALS = [
    # US Banks
    "JPMorgan Chase & Co.",
    "Bank of America Corporation",
    "Citigroup Inc.",
    "Wells Fargo & Company",
    "Goldman Sachs Group, Inc.",
    "Morgan Stanley",
    "Charles Schwab Corporation",
    "TD Bank, N.A.",
    "The Bank of New York Mellon",
    "State Street Corporation",
    "Capital One Financial Corporation",
    # US Asset Managers
    "BlackRock, Inc.",
    "The Vanguard Group",
    "Fidelity Investments",
    "T. Rowe Price Group",
    "PIMCO",
    "Invesco Ltd.",
    "Franklin Templeton",
    # Europe Banks
    "HSBC Holdings PLC",
    "BNP Paribas SA",
    "Barclays PLC",
    "UBS Group AG",
    "Deutsche Bank AG",
    "Banco Santander SA",
    # Europe Asset Managers
    "Amundi",
    "Schroders PLC",
    # Payment Networks
    "Visa Inc.",
    "Mastercard Incorporated",
    "American Express Company",
]


@pytest.mark.parametrize("canonical", REQUIRED_FINANCIAL_CANONICALS)
def test_financial_canonical_present(canonical_data, canonical):
    """Each required financial entity must exist in CANONICALS_FINANCIAL."""
    assert canonical in canonical_data["canonicals_financial"], (
        f"'{canonical}' missing from CANONICALS_FINANCIAL — financial coverage regression"
    )


# ---------------------------------------------------------------------------
# 2. Alias coverage — common short names must resolve via KNOWN_PARENTS
# ---------------------------------------------------------------------------

REQUIRED_FINANCIAL_ALIASES = {
    # The original failure case
    "fidelity": "Fidelity Investments",
    "fidelity investments": "Fidelity Investments",
    # US Banks
    "jpmorgan": "JPMorgan Chase & Co.",
    "chase": "JPMorgan Chase & Co.",
    "bofa": "Bank of America Corporation",
    "bank of america": "Bank of America Corporation",
    "citibank": "Citigroup Inc.",
    "wells fargo": "Wells Fargo & Company",
    "goldman sachs": "Goldman Sachs Group, Inc.",
    "morgan stanley": "Morgan Stanley",
    "schwab": "Charles Schwab Corporation",
    "td bank": "TD Bank, N.A.",
    "bny mellon": "The Bank of New York Mellon",
    "state street": "State Street Corporation",
    # US Asset Managers
    "blackrock": "BlackRock, Inc.",
    "vanguard": "The Vanguard Group",
    "pimco": "PIMCO",
    "invesco": "Invesco Ltd.",
    # Europe
    "hsbc": "HSBC Holdings PLC",
    "bnp": "BNP Paribas SA",
    "barclays": "Barclays PLC",
    "ubs": "UBS Group AG",
    "deutsche bank": "Deutsche Bank AG",
    "santander": "Banco Santander SA",
    "bbva": "Banco Bilbao Vizcaya Argentaria",
    "amundi": "Amundi",
}


@pytest.mark.parametrize(
    "alias,expected",
    list(REQUIRED_FINANCIAL_ALIASES.items()),
    ids=list(REQUIRED_FINANCIAL_ALIASES.keys()),
)
def test_financial_alias_resolves(canonical_data, alias, expected):
    """Each financial alias must map to the correct canonical via KNOWN_PARENTS."""
    actual = canonical_data["kp_exact"].get(alias)
    assert actual == expected, (
        f"Alias '{alias}' → got '{actual}', expected '{expected}'"
    )


# ---------------------------------------------------------------------------
# 3. No false L4 — alias targets must exist in the canonical set
# ---------------------------------------------------------------------------


def test_all_financial_alias_targets_are_canonical(canonical_data):
    """Every KNOWN_PARENTS target for financial aliases must exist in CANONICALS."""
    financial_aliases = {
        k: v for k, v in canonical_data["known_parents"].items()
        if v in canonical_data["canonicals_financial"]
    }
    missing = []
    for alias, target in financial_aliases.items():
        if target.lower() not in canonical_data["canonical_set_lower"]:
            missing.append((alias, target))
    assert not missing, (
        f"Alias targets not in CANONICALS (would cause false L4): {missing}"
    )


# ---------------------------------------------------------------------------
# 4. No duplicates in CANONICALS_FINANCIAL
# ---------------------------------------------------------------------------


def test_no_duplicate_financial_canonicals(canonical_data):
    """CANONICALS_FINANCIAL must not contain duplicate entries."""
    from collections import Counter
    counts = Counter(canonical_data["canonicals_financial"])
    dupes = {k: v for k, v in counts.items() if v > 1}
    assert not dupes, f"Duplicate entries in CANONICALS_FINANCIAL: {dupes}"
