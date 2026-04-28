"""Shared test fixtures for resolver tests."""

import pytest

from apps.api.src.resolver.base import ResolverConfig


# --- Rule sets for testing ---

SAMPLE_RULE_SET = [
    {
        "id": "R-001",
        "condition": {
            "all_of": [
                {"document_type_equals": "regulatory"},
                {"content_contains": "OFAC sanctions violation"},
            ]
        },
        "resolution": "OFAC sanctions violation detected — automatic regulatory flag",
    },
    {
        "id": "R-002",
        "condition": {
            "all_of": [
                {"document_type_equals": "regulatory"},
                {"content_pattern": r"SEC\s+Form\s+10-[KQ]"},
            ]
        },
        "resolution": "SEC filing requirement — regulatory deadline notice",
    },
    {
        "id": "R-003",
        "condition": {
            "all_of": [
                {"document_type_equals": "compliance"},
                {"content_contains": "anti-money laundering violation"},
            ]
        },
        "resolution": "AML violation detected — compliance flag",
    },
]

RULE_SET_VERSION = "1.0"


# --- Precedent stores for testing ---

SAMPLE_PRECEDENTS = [
    {
        "id": "P-001",
        "content": "Annual SOX compliance audit for FY2025 — all controls passed, no material weaknesses identified.",
        "resolution": "SOX compliance — clean audit, no findings",
    },
    {
        "id": "P-002",
        "content": "Material weakness in internal controls over financial reporting identified during Q3 audit.",
        "resolution": "Material weakness — internal control deficiency requiring remediation",
    },
    {
        "id": "P-003",
        "content": "HIPAA privacy rule violation — unauthorized disclosure of patient health information to third party.",
        "resolution": "HIPAA privacy violation — unauthorized PHI disclosure",
    },
]


# --- Config fixtures ---


@pytest.fixture
def default_config() -> ResolverConfig:
    return ResolverConfig()


@pytest.fixture
def strict_config() -> ResolverConfig:
    """Config with high review threshold — most things route to review."""
    return ResolverConfig(review_threshold=0.99, l2_match_threshold=0.9)


@pytest.fixture
def lenient_config() -> ResolverConfig:
    """Config with low thresholds — most things resolve."""
    return ResolverConfig(review_threshold=0.3, l2_match_threshold=0.3)


@pytest.fixture
def l1_only_config() -> ResolverConfig:
    return ResolverConfig(max_layer=1)


@pytest.fixture
def l2_only_config() -> ResolverConfig:
    return ResolverConfig(max_layer=2)


@pytest.fixture
def rule_set() -> list[dict]:
    return SAMPLE_RULE_SET


@pytest.fixture
def precedents() -> list[dict]:
    return SAMPLE_PRECEDENTS
