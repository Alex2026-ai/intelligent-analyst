"""Mixed-Mode Canonical Pre-Check — Regression Tests.

Validates that obvious organization canonicals resolve deterministically
in MIXED mode via the canonical pre-check in resolve_mixed_sync(),
instead of falling through to the org sanitizer and then L4.

Added: 2026-03-18, after BATCH-D4B4DDCE investigation proved that
mixed-mode ORG rows bypassed the canonical lookup entirely.
"""

import os
import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def resolver():
    """Import resolve_mixed_sync and _try_canonical_match from the server module."""
    from app.server_enterprise_golden import (
        resolve_mixed_sync,
        _try_canonical_match,
    )
    return {
        "resolve_mixed_sync": resolve_mixed_sync,
        "_try_canonical_match": _try_canonical_match,
    }


# ---------------------------------------------------------------------------
# 1. _try_canonical_match — unit tests for the pre-check helper
# ---------------------------------------------------------------------------

class TestTryCanonicalMatch:
    """Verify the canonical pre-check helper resolves known entities."""

    def test_fidelity_investments_alias(self, resolver):
        """The original failure case: 'Fidelity Investments' must match."""
        result = resolver["_try_canonical_match"]("Fidelity Investments")
        assert result is not None, "Fidelity Investments should match via alias"
        resolved, layer, confidence = result
        assert resolved == "Fidelity Investments"
        assert layer == "L1_CANONICAL"
        assert confidence == 1.0

    def test_fidelity_lowercase(self, resolver):
        """Lowercase alias 'fidelity' must match."""
        result = resolver["_try_canonical_match"]("fidelity")
        assert result is not None
        assert result[0] == "Fidelity Investments"

    def test_hsbc(self, resolver):
        """HSBC alias must match."""
        result = resolver["_try_canonical_match"]("HSBC")
        assert result is not None
        assert result[0] == "HSBC Holdings PLC"
        assert result[2] == 1.0

    def test_jpmorgan_chase(self, resolver):
        """JPMorgan Chase must match via suffix-stripped or alias."""
        result = resolver["_try_canonical_match"]("JPMorgan Chase")
        assert result is not None
        assert result[0] == "JPMorgan Chase & Co."

    def test_barclays(self, resolver):
        """Barclays alias must match."""
        result = resolver["_try_canonical_match"]("Barclays")
        assert result is not None
        assert result[0] == "Barclays PLC"

    def test_deutsche_bank(self, resolver):
        """Deutsche Bank alias must match."""
        result = resolver["_try_canonical_match"]("Deutsche Bank")
        assert result is not None
        assert result[0] == "Deutsche Bank AG"

    def test_noncanonical_org_returns_none(self, resolver):
        """An unknown org name must return None (falls to sanitizer)."""
        result = resolver["_try_canonical_match"]("Acme Widget Corporation")
        assert result is None

    def test_random_string_returns_none(self, resolver):
        """A random string must return None."""
        result = resolver["_try_canonical_match"]("xyz random company name 12345")
        assert result is None

    def test_empty_returns_none(self, resolver):
        """Empty string must return None."""
        result = resolver["_try_canonical_match"]("")
        assert result is None


# ---------------------------------------------------------------------------
# 2. resolve_mixed_sync — integration tests for the ORG canonical path
# ---------------------------------------------------------------------------

class TestMixedModeCanonicalPrecheck:
    """Verify resolve_mixed_sync resolves canonical ORGs at L1_CANONICAL."""

    def test_fidelity_resolves_deterministically(self, resolver):
        """Fidelity Investments in mixed mode must resolve at L1_CANONICAL, not L1_ORG."""
        result = resolver["resolve_mixed_sync"]("Fidelity Investments")
        assert result["layer"] == "L1_CANONICAL", (
            f"Expected L1_CANONICAL, got {result['layer']}. "
            f"Fidelity must resolve via canonical pre-check, not sanitizer."
        )
        assert result["resolved"] == "Fidelity Investments"
        assert result["confidence"] == 1.0
        assert result["entity_type"] == "ORGANIZATION"
        assert result["decision_path"] == "CANONICAL_RESOLVED"

    def test_hsbc_resolves_deterministically(self, resolver):
        """HSBC in mixed mode must resolve at L1_CANONICAL."""
        result = resolver["resolve_mixed_sync"]("HSBC")
        assert result["layer"] == "L1_CANONICAL"
        assert result["resolved"] == "HSBC Holdings PLC"
        assert result["confidence"] == 1.0

    def test_barclays_resolves_deterministically(self, resolver):
        """Barclays in mixed mode must resolve at L1_CANONICAL."""
        result = resolver["resolve_mixed_sync"]("Barclays")
        assert result["layer"] == "L1_CANONICAL"
        assert result["resolved"] == "Barclays PLC"

    def test_jpmorgan_resolves_deterministically(self, resolver):
        """JPMorgan in mixed mode must resolve at L1_CANONICAL."""
        result = resolver["resolve_mixed_sync"]("jpmorgan")
        assert result["layer"] == "L1_CANONICAL"
        assert result["resolved"] == "JPMorgan Chase & Co."

    def test_noncanonical_org_still_uses_sanitizer(self, resolver):
        """Non-canonical org must still go through sanitize_organization_name."""
        result = resolver["resolve_mixed_sync"]("Acme Widget Corporation")
        # Should NOT be L1_CANONICAL — should be L1_ORG (sanitized)
        assert result["layer"] != "L1_CANONICAL", (
            "Non-canonical org should not resolve at L1_CANONICAL"
        )
        # Should still produce sanitized output
        assert result.get("sanitized_name") or result.get("org_name")

    def test_person_name_not_affected(self, resolver):
        """Person names must still go through person sanitizer, not canonical check."""
        result = resolver["resolve_mixed_sync"]("John Michael Smith")
        assert result["entity_type"] == "PERSON"
        assert result["layer"] == "L1_PERSON"
        # Should NOT have canonical resolution fields
        assert result.get("resolved") is None or result["layer"] == "L1_PERSON"

    def test_canonical_match_not_promoted_to_l4(self, resolver):
        """A canonical match must never land in L4_HUMAN."""
        result = resolver["resolve_mixed_sync"]("Fidelity Investments")
        assert result["layer"] != "L4_HUMAN", (
            "Canonical match must resolve deterministically, never L4"
        )

    def test_canonical_result_has_resolved_field(self, resolver):
        """Canonical match must set the 'resolved' field for downstream consumers."""
        result = resolver["resolve_mixed_sync"]("Goldman Sachs")
        if result["layer"] == "L1_CANONICAL":
            assert result.get("resolved") is not None
            assert "Goldman Sachs" in result["resolved"]


# ---------------------------------------------------------------------------
# 3. Stale cache bypass — deterministic canonical wins over cached UNKNOWN
# ---------------------------------------------------------------------------

class TestStaleCacheBypass:
    """Verify that deterministic canonical resolution in Phase 1 prevents
    stale L3 cache UNKNOWN from overriding a now-known canonical."""

    def test_canonical_resolves_before_l3_phase(self, resolver):
        """
        If Fidelity resolves at L1_CANONICAL in Phase 1, it never reaches
        Phase 2 (L3 processing), so no cache lookup occurs.
        The 'resolved' field being set means it won't be promoted to L4_HUMAN.
        """
        result = resolver["resolve_mixed_sync"]("Fidelity Investments")
        # L1_CANONICAL with resolved != None means this row will NOT be
        # promoted to L4_HUMAN in the Phase 2 promotion step (line 5743-5754),
        # because that promotion only targets rows with layer == "L1_ORG"
        # and resolved == None.
        assert result["layer"] == "L1_CANONICAL"
        assert result.get("resolved") is not None, (
            "resolved must be set to prevent Phase 2 L4 promotion"
        )

    def test_noncanonical_org_still_eligible_for_l3(self, resolver):
        """Non-canonical ORGs must still land at L1_ORG (eligible for Phase 2 promotion)."""
        result = resolver["resolve_mixed_sync"]("Obscure Financial Holdings Ltd")
        # This should go through sanitizer path
        if result["entity_type"] == "ORGANIZATION":
            assert result["layer"] in ("L1_ORG", "L0_GARBAGE"), (
                f"Non-canonical org should be L1_ORG or garbage, got {result['layer']}"
            )
