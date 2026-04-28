"""
Regression tests for non-sharded L1 aggregation in counts dict.

Bug: counts.l1_resolved only summed l1_exact + l1_norm, missing mixed-mode
layers (L1_PERSON, L1_ORG, L1_VESSEL) and person-mode layers
(L1_PERSON_EXACT, L1_PERSON_ALIAS, L1_PERSON_INITIAL).

Fix: counts.l1_resolved now equals l1_total + l1_mixed_person + l1_mixed_org
+ l1_mixed_vessel, matching stats.layer_1_total.

These tests verify the aggregation math without importing the full server.
"""
import pytest


def compute_l1_counts(results):
    """
    Replicates the non-sharded aggregation logic from server_enterprise_golden.py
    (lines 6468-6704) for the L1-related fields.
    """
    # Company mode layers
    l1_exact = sum(1 for r in results if r.get("layer") == "L1_EXACT")
    l1_norm = sum(1 for r in results if r.get("layer") == "L1_NORM")

    # Person mode layers
    l1_person_exact = sum(1 for r in results if r.get("layer") == "L1_PERSON_EXACT")
    l1_person_alias = sum(1 for r in results if r.get("layer") == "L1_PERSON_ALIAS")
    l1_person_initial = sum(1 for r in results if r.get("layer") == "L1_PERSON_INITIAL")

    # Combined L1 (company + person)
    l1_total = l1_exact + l1_norm + l1_person_exact + l1_person_alias + l1_person_initial

    # Mixed mode layers
    l1_mixed_person = sum(1 for r in results if r.get("layer") == "L1_PERSON")
    l1_mixed_org = sum(1 for r in results if r.get("layer") == "L1_ORG")
    l1_mixed_vessel = sum(1 for r in results if r.get("layer") == "L1_VESSEL")

    # Other layers
    l0 = sum(1 for r in results if r.get("layer", "").startswith("L0_GARBAGE"))
    l2 = sum(1 for r in results if r.get("layer") == "L2_VECTOR")
    l3 = sum(1 for r in results if r.get("layer") in ("L3_LLM", "L3_CACHED"))
    l4 = sum(1 for r in results if r.get("layer") == "L4_HUMAN")

    # ── FIX: l1_resolved must include ALL L1 variants ──
    l1_resolved = l1_total + l1_mixed_person + l1_mixed_org + l1_mixed_vessel

    # stats.layer_1_total (reference — already correct in production)
    layer_1_total = l1_total + l1_mixed_person + l1_mixed_org + l1_mixed_vessel

    return {
        "l1_resolved": l1_resolved,
        "l1_exact": l1_exact,
        "l1_norm": l1_norm,
        "layer_1_total": layer_1_total,
        "l0_quarantined": l0,
        "l2_resolved": l2,
        "l3_resolved": l3,
        "l4_flagged": l4,
        "l1_mixed_person": l1_mixed_person,
        "l1_mixed_org": l1_mixed_org,
        "l1_mixed_vessel": l1_mixed_vessel,
    }


# ============================================================================
# Mixed Mode — the primary regression case
# ============================================================================

class TestMixedModeL1Aggregation:
    """Batches processed in MIXED mode produce L1_PERSON, L1_ORG, L1_VESSEL."""

    def test_mixed_mode_l1_resolved_includes_all_subtypes(self):
        """REGRESSION: l1_resolved must equal sum of L1_PERSON + L1_ORG + L1_VESSEL."""
        results = [
            {"layer": "L1_PERSON"} for _ in range(7726)
        ] + [
            {"layer": "L1_ORG"} for _ in range(2217)
        ] + [
            {"layer": "L1_VESSEL"} for _ in range(5)
        ] + [
            {"layer": "L0_GARBAGE"} for _ in range(52)
        ]
        counts = compute_l1_counts(results)

        assert counts["l1_resolved"] == 7726 + 2217 + 5  # 9948
        assert counts["l1_resolved"] == counts["layer_1_total"]
        assert counts["l0_quarantined"] == 52
        assert counts["l2_resolved"] == 0
        assert counts["l3_resolved"] == 0
        assert counts["l4_flagged"] == 0

    def test_mixed_mode_matches_stats_layer_1_total(self):
        """counts.l1_resolved must always equal stats.layer_1_total."""
        results = [
            {"layer": "L1_PERSON"} for _ in range(100)
        ] + [
            {"layer": "L1_ORG"} for _ in range(50)
        ] + [
            {"layer": "L4_HUMAN"} for _ in range(10)
        ]
        counts = compute_l1_counts(results)

        assert counts["l1_resolved"] == 150
        assert counts["l1_resolved"] == counts["layer_1_total"]
        assert counts["l4_flagged"] == 10

    def test_mixed_mode_with_garbage_and_l4(self):
        """Mixed mode batch with all layer types present."""
        results = (
            [{"layer": "L1_PERSON"}] * 185
            + [{"layer": "L1_ORG"}] * 85
            + [{"layer": "L1_VESSEL"}] * 2
            + [{"layer": "L0_GARBAGE"}] * 10
            + [{"layer": "L4_HUMAN"}] * 3
        )
        counts = compute_l1_counts(results)

        assert counts["l1_resolved"] == 185 + 85 + 2  # 272
        assert counts["l0_quarantined"] == 10
        assert counts["l4_flagged"] == 3
        assert counts["l1_mixed_person"] == 185
        assert counts["l1_mixed_org"] == 85
        assert counts["l1_mixed_vessel"] == 2


# ============================================================================
# Company Mode — must remain correct
# ============================================================================

class TestCompanyModeL1Aggregation:
    """Batches processed in COMPANY mode produce L1_EXACT and L1_NORM."""

    def test_company_mode_l1_resolved(self):
        results = (
            [{"layer": "L1_EXACT"}] * 11
            + [{"layer": "L1_NORM"}] * 786
            + [{"layer": "L2_VECTOR"}] * 139
            + [{"layer": "L3_LLM"}] * 4
            + [{"layer": "L4_HUMAN"}] * 70
        )
        counts = compute_l1_counts(results)

        assert counts["l1_resolved"] == 11 + 786  # 797
        assert counts["l1_exact"] == 11
        assert counts["l1_norm"] == 786
        assert counts["l2_resolved"] == 139
        assert counts["l3_resolved"] == 4
        assert counts["l4_flagged"] == 70

    def test_company_mode_all_l1(self):
        """100% L1 resolution — common for well-known company datasets."""
        results = (
            [{"layer": "L1_EXACT"}] * 260
            + [{"layer": "L1_NORM"}] * 4338
            + [{"layer": "L0_GARBAGE"}] * 52
        )
        counts = compute_l1_counts(results)

        assert counts["l1_resolved"] == 260 + 4338  # 4598
        assert counts["l1_resolved"] == counts["layer_1_total"]


# ============================================================================
# Person Mode — L1_PERSON_EXACT, L1_PERSON_ALIAS, L1_PERSON_INITIAL
# ============================================================================

class TestPersonModeL1Aggregation:

    def test_person_mode_l1_resolved_includes_all_person_subtypes(self):
        results = (
            [{"layer": "L1_PERSON_EXACT"}] * 50
            + [{"layer": "L1_PERSON_ALIAS"}] * 30
            + [{"layer": "L1_PERSON_INITIAL"}] * 10
            + [{"layer": "L4_HUMAN"}] * 10
        )
        counts = compute_l1_counts(results)

        assert counts["l1_resolved"] == 50 + 30 + 10  # 90
        assert counts["l1_resolved"] == counts["layer_1_total"]
        assert counts["l4_flagged"] == 10


# ============================================================================
# Edge Cases
# ============================================================================

class TestEdgeCases:

    def test_empty_batch(self):
        counts = compute_l1_counts([])
        assert counts["l1_resolved"] == 0
        assert counts["layer_1_total"] == 0
        assert counts["l0_quarantined"] == 0

    def test_all_garbage(self):
        results = [{"layer": "L0_GARBAGE"}] * 500
        counts = compute_l1_counts(results)
        assert counts["l1_resolved"] == 0
        assert counts["l0_quarantined"] == 500

    def test_l3_cached_counted_correctly(self):
        results = (
            [{"layer": "L1_NORM"}] * 100
            + [{"layer": "L3_LLM"}] * 5
            + [{"layer": "L3_CACHED"}] * 15
        )
        counts = compute_l1_counts(results)
        assert counts["l1_resolved"] == 100
        assert counts["l3_resolved"] == 20  # 5 + 15

    def test_mixed_and_company_layers_together(self):
        """Hypothetical: both company and mixed layers present."""
        results = (
            [{"layer": "L1_EXACT"}] * 10
            + [{"layer": "L1_NORM"}] * 20
            + [{"layer": "L1_PERSON"}] * 50
            + [{"layer": "L1_ORG"}] * 30
        )
        counts = compute_l1_counts(results)
        assert counts["l1_resolved"] == 10 + 20 + 50 + 30  # 110
        assert counts["l1_resolved"] == counts["layer_1_total"]
