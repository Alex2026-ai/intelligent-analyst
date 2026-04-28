"""
Tests for backend/app/l3_drift_invariant.py

Verifies zone classification, percentage calculations, cost_exceeded flag,
edge cases (zero records), and reason string formatting.
"""

import pytest
from app.l3_drift_invariant import (
    compute_drift_invariant,
    DriftInvariant,
    WARN_THRESHOLD_PCT,
    RED_THRESHOLD_PCT,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _inv(l3: int, l4: int, total: int, spent: float = 0.0, budget: float = 10.0) -> DriftInvariant:
    return compute_drift_invariant(
        total_l3=l3,
        total_l4=l4,
        total_valid_records=total,
        spent_usd=spent,
        budget_usd=budget,
    )


# ---------------------------------------------------------------------------
# Zone: SAFE
# ---------------------------------------------------------------------------

class TestSafeZone:
    def test_zero_l3(self):
        inv = _inv(l3=0, l4=5, total=100)
        assert inv.zone == "SAFE"
        assert inv.l3_pct == 0.0

    def test_below_warn_threshold(self):
        # 2 L3 out of 100 valid = 2.0% — below 3.0% warn
        inv = _inv(l3=2, l4=5, total=100)
        assert inv.zone == "SAFE"
        assert inv.l3_pct == 2.0

    def test_just_below_warn_threshold(self):
        # 2.99 L3% — just below 3.0%
        inv = _inv(l3=299, l4=5, total=10000)
        assert inv.zone == "SAFE"
        assert inv.l3_pct < WARN_THRESHOLD_PCT

    def test_reason_mentions_safe_threshold(self):
        inv = _inv(l3=1, l4=0, total=100)
        assert "WARNING threshold" in inv.reason
        assert inv.zone == "SAFE"


# ---------------------------------------------------------------------------
# Zone: WARNING
# ---------------------------------------------------------------------------

class TestWarningZone:
    def test_at_warn_threshold(self):
        # Exactly 3.0% L3
        inv = _inv(l3=30, l4=5, total=1000)
        assert inv.zone == "WARNING"
        assert inv.l3_pct == 3.0

    def test_between_warn_and_red(self):
        # 4.0% — in WARNING band
        inv = _inv(l3=40, l4=5, total=1000)
        assert inv.zone == "WARNING"
        assert inv.l3_pct == 4.0

    def test_just_below_red_threshold(self):
        # 4.499% — below 4.5% red
        inv = _inv(l3=4499, l4=10, total=100000)
        assert inv.zone == "WARNING"
        assert inv.l3_pct < RED_THRESHOLD_PCT

    def test_reason_mentions_warn_threshold(self):
        inv = _inv(l3=35, l4=5, total=1000)
        assert "WARNING threshold" in inv.reason
        assert inv.zone == "WARNING"


# ---------------------------------------------------------------------------
# Zone: RED (rate-based)
# ---------------------------------------------------------------------------

class TestRedZoneByRate:
    def test_at_red_threshold(self):
        # Exactly 4.5% L3
        inv = _inv(l3=45, l4=5, total=1000)
        assert inv.zone == "RED"
        assert inv.l3_pct == 4.5

    def test_above_red_threshold(self):
        inv = _inv(l3=100, l4=5, total=1000)
        assert inv.zone == "RED"
        assert inv.l3_pct == 10.0

    def test_red_reason_mentions_threshold(self):
        inv = _inv(l3=50, l4=5, total=1000)
        assert "RED threshold" in inv.reason
        assert inv.zone == "RED"


# ---------------------------------------------------------------------------
# Zone: RED (cost_exceeded)
# ---------------------------------------------------------------------------

class TestRedZoneByCost:
    def test_spent_equals_budget(self):
        # spent == budget → cost_exceeded → RED
        inv = _inv(l3=1, l4=0, total=100, spent=10.0, budget=10.0)
        assert inv.cost_exceeded is True
        assert inv.zone == "RED"

    def test_spent_exceeds_budget(self):
        inv = _inv(l3=1, l4=0, total=100, spent=10.005, budget=10.0)
        assert inv.cost_exceeded is True
        assert inv.zone == "RED"

    def test_cost_exceeded_overrides_safe_rate(self):
        # L3 rate is only 1% (SAFE by rate), but budget was hit
        inv = _inv(l3=1, l4=0, total=100, spent=10.0, budget=10.0)
        assert inv.l3_pct == 1.0  # would be SAFE by rate alone
        assert inv.zone == "RED"   # overridden by cost

    def test_cost_exceeded_reason_mentions_budget(self):
        inv = _inv(l3=1, l4=0, total=100, spent=10.0, budget=10.0)
        assert "budget cap" in inv.reason
        assert "$10.000" in inv.reason or "10.000" in inv.reason

    def test_budget_zero_no_cost_exceeded(self):
        # budget_usd=0 disables the cost check (avoids division edge)
        inv = _inv(l3=1, l4=0, total=100, spent=5.0, budget=0.0)
        assert inv.cost_exceeded is False

    def test_spent_below_budget_no_cost_exceeded(self):
        inv = _inv(l3=1, l4=0, total=100, spent=9.999, budget=10.0)
        assert inv.cost_exceeded is False


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_zero_valid_records_returns_safe(self):
        inv = _inv(l3=0, l4=0, total=0)
        assert inv.zone == "SAFE"
        assert inv.l3_pct == 0.0
        assert inv.l4_pct == 0.0
        assert inv.total_records == 0

    def test_zero_valid_records_passthrough_counts(self):
        # Counts are preserved even if total is 0
        inv = _inv(l3=5, l4=3, total=0)
        assert inv.total_l3 == 5
        assert inv.total_l4 == 3

    def test_l3_exceeds_total_valid(self):
        # Degenerate case: l3 > total (shouldn't happen, but shouldn't crash)
        inv = _inv(l3=200, l4=0, total=100)
        assert inv.l3_pct == 200.0
        assert inv.zone == "RED"

    def test_l4_pct_calculation(self):
        # 15 L4 out of 100 valid = 15.0%
        inv = _inv(l3=2, l4=15, total=100)
        assert inv.l4_pct == 15.0


# ---------------------------------------------------------------------------
# Output field correctness
# ---------------------------------------------------------------------------

class TestOutputFields:
    def test_budget_and_spent_passthrough(self):
        inv = _inv(l3=5, l4=2, total=1000, spent=3.75, budget=10.0)
        assert inv.budget_usd == 10.0
        assert inv.spent_usd == 3.75

    def test_total_counts_passthrough(self):
        inv = _inv(l3=10, l4=5, total=200)
        assert inv.total_l3 == 10
        assert inv.total_l4 == 5
        assert inv.total_records == 200

    def test_spent_rounded_to_4dp(self):
        inv = _inv(l3=1, l4=0, total=100, spent=0.00501234, budget=10.0)
        assert inv.spent_usd == 0.005  # round(0.00501234, 4) = 0.005

    def test_l3_pct_rounded_to_3dp(self):
        # 1/3 * 100 = 33.333...
        inv = _inv(l3=1, l4=0, total=3)
        assert inv.l3_pct == 33.333

    def test_cost_exceeded_false_by_default(self):
        # No spent_usd provided (defaults to 0.0), budget=10.0 → not exceeded
        inv = compute_drift_invariant(
            total_l3=5, total_l4=2, total_valid_records=100,
            spent_usd=0.0, budget_usd=10.0
        )
        assert inv.cost_exceeded is False


# ---------------------------------------------------------------------------
# Custom thresholds
# ---------------------------------------------------------------------------

class TestCustomThresholds:
    def test_custom_warn_threshold(self):
        # warn at 5%, red at 8%
        inv = compute_drift_invariant(
            total_l3=6, total_l4=0, total_valid_records=100,
            spent_usd=0.0, budget_usd=10.0,
            warn_threshold_pct=5.0,
            red_threshold_pct=8.0,
        )
        assert inv.zone == "WARNING"
        assert inv.l3_pct == 6.0

    def test_custom_red_threshold(self):
        inv = compute_drift_invariant(
            total_l3=9, total_l4=0, total_valid_records=100,
            spent_usd=0.0, budget_usd=10.0,
            warn_threshold_pct=5.0,
            red_threshold_pct=8.0,
        )
        assert inv.zone == "RED"
        assert inv.l3_pct == 9.0

    def test_custom_thresholds_safe(self):
        inv = compute_drift_invariant(
            total_l3=4, total_l4=0, total_valid_records=100,
            spent_usd=0.0, budget_usd=10.0,
            warn_threshold_pct=5.0,
            red_threshold_pct=8.0,
        )
        assert inv.zone == "SAFE"


# ---------------------------------------------------------------------------
# Constant values
# ---------------------------------------------------------------------------

def test_warn_threshold_constant():
    assert WARN_THRESHOLD_PCT == 3.0

def test_red_threshold_constant():
    assert RED_THRESHOLD_PCT == 4.5
