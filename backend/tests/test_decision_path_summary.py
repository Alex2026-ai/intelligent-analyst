"""
================================================================================
Decision Path Summary Tests
================================================================================

Tests for compute_decision_path_summary() across all modes:
- Company mode: layer_1_exact + layer_1_norm
- Mixed mode: layer_1_mixed_org + layer_1_mixed_person + layer_1_mixed_vessel
- Person mode: layer_1_person_exact + layer_1_person_alias + layer_1_person_initial

Run with: pytest backend/tests/test_decision_path_summary.py -v
================================================================================
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.server_enterprise_golden import compute_decision_path_summary


class TestCompanyMode:
    """Company mode: L1 = layer_1_exact + layer_1_norm."""

    def test_company_basic(self):
        stats = {
            "layer_1_exact": 50,
            "layer_1_norm": 158,
            "layer_2_vector": 23,
            "layer_3_llm": 2,
            "layer_4_human": 37,
        }
        result = compute_decision_path_summary(stats)
        assert result["L1_DETERMINISTIC"] == 208
        assert result["L2_VECTOR_FUZZY"] == 23
        assert result["L3_LLM"] == 2
        assert result["L4_HUMAN_REVIEW_REQUIRED"] == 37
        assert result["total_processed"] == 270

    def test_company_zero_l3_l4(self):
        stats = {
            "layer_1_exact": 100,
            "layer_1_norm": 50,
            "layer_2_vector": 10,
            "layer_3_llm": 0,
            "layer_4_human": 0,
        }
        result = compute_decision_path_summary(stats)
        assert result["L1_DETERMINISTIC"] == 150
        assert result["total_processed"] == 160

    def test_company_empty_stats(self):
        result = compute_decision_path_summary({})
        assert result["L1_DETERMINISTIC"] == 0
        assert result["L2_VECTOR_FUZZY"] == 0
        assert result["L3_LLM"] == 0
        assert result["L4_HUMAN_REVIEW_REQUIRED"] == 0
        assert result["total_processed"] == 0


class TestMixedMode:
    """Mixed mode: L1 = layer_1_mixed_org + layer_1_mixed_person + layer_1_mixed_vessel."""

    def test_mixed_basic(self):
        stats = {
            "layer_1_exact": 0,
            "layer_1_norm": 0,
            "layer_1_mixed_org": 185,
            "layer_1_mixed_person": 85,
            "layer_1_mixed_vessel": 0,
            "layer_2_vector": 0,
            "layer_3_llm": 0,
            "layer_4_human": 0,
            "layer_1_total": 270,
        }
        result = compute_decision_path_summary(stats)
        assert result["L1_DETERMINISTIC"] == 270
        assert result["total_processed"] == 270
        # L1 must match layer_1_total
        assert result["L1_DETERMINISTIC"] == stats["layer_1_total"]

    def test_mixed_with_vessel(self):
        stats = {
            "layer_1_exact": 0,
            "layer_1_norm": 0,
            "layer_1_mixed_org": 100,
            "layer_1_mixed_person": 50,
            "layer_1_mixed_vessel": 30,
            "layer_2_vector": 0,
            "layer_3_llm": 0,
            "layer_4_human": 0,
        }
        result = compute_decision_path_summary(stats)
        assert result["L1_DETERMINISTIC"] == 180
        assert result["total_processed"] == 180

    def test_mixed_nonzero_total(self):
        """Mixed mode should produce nonzero total (regression for BATCH-A02F301F)."""
        # Exact stats from the bug: BATCH-A02F301F
        stats = {
            "layer_1_exact": 0,
            "layer_1_norm": 0,
            "layer_1_mixed_org": 185,
            "layer_1_mixed_person": 85,
            "layer_1_mixed_vessel": 0,
            "layer_2_vector": 0,
            "layer_3_llm": 0,
            "layer_4_human": 0,
        }
        result = compute_decision_path_summary(stats)
        assert result["total_processed"] > 0, "Mixed mode must not produce zero total"
        assert result["L1_DETERMINISTIC"] == 270


class TestPersonMode:
    """Person mode: L1 includes person-specific layers."""

    def test_person_basic(self):
        stats = {
            "layer_1_exact": 0,
            "layer_1_norm": 0,
            "layer_1_person_exact": 40,
            "layer_1_person_alias": 20,
            "layer_1_person_initial": 10,
            "layer_2_vector": 0,
            "layer_2_person_fuzzy": 15,
            "layer_3_llm": 0,
            "layer_4_human": 5,
        }
        result = compute_decision_path_summary(stats)
        assert result["L1_DETERMINISTIC"] == 70
        assert result["L2_VECTOR_FUZZY"] == 15
        assert result["L4_HUMAN_REVIEW_REQUIRED"] == 5
        assert result["total_processed"] == 90


class TestCrossMode:
    """Edge cases across modes."""

    def test_mixed_counters_ignored_when_zero(self):
        """Company stats with zero mixed counters should be unchanged."""
        stats_company = {
            "layer_1_exact": 50,
            "layer_1_norm": 150,
            "layer_2_vector": 20,
            "layer_3_llm": 5,
            "layer_4_human": 10,
        }
        result = compute_decision_path_summary(stats_company)
        assert result["L1_DETERMINISTIC"] == 200
        assert result["total_processed"] == 235

    def test_total_consistency(self):
        """total_processed must equal sum of all four categories."""
        stats = {
            "layer_1_exact": 10,
            "layer_1_norm": 20,
            "layer_1_mixed_org": 30,
            "layer_1_mixed_person": 40,
            "layer_2_vector": 5,
            "layer_2_person_fuzzy": 3,
            "layer_3_llm": 2,
            "layer_4_human": 1,
        }
        result = compute_decision_path_summary(stats)
        expected = (
            result["L1_DETERMINISTIC"]
            + result["L2_VECTOR_FUZZY"]
            + result["L3_LLM"]
            + result["L4_HUMAN_REVIEW_REQUIRED"]
        )
        assert result["total_processed"] == expected
