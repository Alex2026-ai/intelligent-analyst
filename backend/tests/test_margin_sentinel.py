"""
Tests for backend/app/margin_sentinel_invariant.py

Covers: human_cost calculation, cost_per_record calculation,
SAFE/WARNING/RED zone classification, invariant_pass flag,
edge cases (zero records), and threshold boundary conditions.
"""

import pytest
from app.margin_sentinel_invariant import (
    compute_margin_sentinel,
    MarginInvariant,
    DEFAULT_HUMAN_COST_PER_RECORD_USD,
    DEFAULT_L4_WARNING_THRESHOLD_PCT,
    DEFAULT_L4_RED_THRESHOLD_PCT,
    DEFAULT_COST_PER_RECORD_RED_USD,
    _COST_APPROACH_FRACTION,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _ms(
    records: int,
    l4: int,
    llm_cost: float = 0.0,
    l3: int = 0,
    human_rate: float = DEFAULT_HUMAN_COST_PER_RECORD_USD,
    l4_warn: float = DEFAULT_L4_WARNING_THRESHOLD_PCT,
    l4_red: float = DEFAULT_L4_RED_THRESHOLD_PCT,
    cost_red: float = DEFAULT_COST_PER_RECORD_RED_USD,
) -> MarginInvariant:
    return compute_margin_sentinel(
        total_records=records,
        total_l3=l3,
        total_l4=l4,
        total_llm_cost_usd=llm_cost,
        human_cost_per_record_usd=human_rate,
        l4_warning_threshold_pct=l4_warn,
        l4_red_threshold_pct=l4_red,
        cost_per_record_red_usd=cost_red,
    )


# ---------------------------------------------------------------------------
# Human cost calculation
# ---------------------------------------------------------------------------

class TestHumanCostCalculation:
    def test_human_cost_zero_l4(self):
        inv = _ms(records=1000, l4=0, llm_cost=1.0)
        assert inv.human_cost_usd == 0.0

    def test_human_cost_default_rate(self):
        # 10 L4 × $0.50 = $5.00
        inv = _ms(records=1000, l4=10, llm_cost=0.0)
        assert inv.human_cost_usd == 5.0

    def test_human_cost_custom_rate(self):
        # 10 L4 × $1.00 = $10.00
        inv = _ms(records=1000, l4=10, llm_cost=0.0, human_rate=1.00)
        assert inv.human_cost_usd == 10.0

    def test_human_cost_high_volume(self):
        # 500 L4 × $0.50 = $250
        inv = _ms(records=10000, l4=500, llm_cost=0.0)
        assert inv.human_cost_usd == 250.0

    def test_total_cost_is_llm_plus_human(self):
        # LLM: $2.00, human: 10 × $0.50 = $5.00 → total $7.00
        inv = _ms(records=1000, l4=10, llm_cost=2.0)
        assert inv.total_cost_usd == pytest.approx(7.0, abs=0.0001)

    def test_total_cost_llm_only(self):
        inv = _ms(records=1000, l4=0, llm_cost=3.75)
        assert inv.total_cost_usd == pytest.approx(3.75, abs=0.0001)


# ---------------------------------------------------------------------------
# Cost-per-record calculation
# ---------------------------------------------------------------------------

class TestCostPerRecordCalculation:
    def test_cost_per_record_zero_cost(self):
        inv = _ms(records=1000, l4=0, llm_cost=0.0)
        assert inv.cost_per_record_usd == 0.0

    def test_cost_per_record_basic(self):
        # total_cost = 0 LLM + 10 × 0.50 = 5.0 → 5.0/1000 = 0.005
        inv = _ms(records=1000, l4=10, llm_cost=0.0)
        assert inv.cost_per_record_usd == pytest.approx(0.005, abs=0.000001)

    def test_cost_per_record_baseline(self):
        # Performance baseline: 40K records, L4=5%, LLM=$0.21
        # L4 count = 40000 * 0.05 = 2000; human = 2000 × 0.50 = 1000; llm = 0.21
        # total = 1000.21; cost/record = round(1000.21/40000, 5)
        # Note: stored value is rounded to 5dp so compare with 1e-5 tolerance
        inv = _ms(records=40000, l4=2000, llm_cost=0.21)
        assert inv.cost_per_record_usd == pytest.approx(1000.21 / 40000, abs=0.00001)

    def test_cost_per_record_rounded_to_5dp(self):
        # 1/(3*1000) = 0.00033333... → round to 5dp = 0.00033
        inv = _ms(records=3000, l4=2, llm_cost=0.0, human_rate=0.50)
        # human = 2 × 0.50 = 1.0; cost/record = 1.0/3000 ≈ 0.000333
        assert inv.cost_per_record_usd == round(1.0 / 3000, 5)

    def test_cost_per_record_zero_records(self):
        inv = _ms(records=0, l4=0, llm_cost=0.0)
        assert inv.cost_per_record_usd == 0.0


# ---------------------------------------------------------------------------
# Zone: SAFE
# ---------------------------------------------------------------------------

class TestSafeZone:
    def test_safe_zero_l4_zero_cost(self):
        inv = _ms(records=1000, l4=0, llm_cost=0.0)
        assert inv.zone == "SAFE"
        assert inv.invariant_pass is True

    def test_safe_below_warning_threshold(self):
        # 5% L4 — below 6.0% warning; cost well below $0.05/record
        inv = _ms(records=1000, l4=50, llm_cost=0.0)
        assert inv.l4_pct == 5.0
        assert inv.zone == "SAFE"

    def test_safe_just_below_warning(self):
        # 5.99% L4
        inv = _ms(records=10000, l4=599, llm_cost=0.0)
        assert inv.l4_pct < DEFAULT_L4_WARNING_THRESHOLD_PCT
        assert inv.zone == "SAFE"

    def test_safe_cost_well_below_threshold(self):
        # cost/record = 0.0001 — far below $0.05 threshold
        inv = _ms(records=10000, l4=2, llm_cost=0.0)
        assert inv.cost_per_record_usd < DEFAULT_COST_PER_RECORD_RED_USD * _COST_APPROACH_FRACTION
        assert inv.zone == "SAFE"

    def test_safe_invariant_pass_true(self):
        inv = _ms(records=1000, l4=10, llm_cost=0.0)
        assert inv.invariant_pass is True


# ---------------------------------------------------------------------------
# Zone: WARNING
# ---------------------------------------------------------------------------

class TestWarningZone:
    def test_warning_at_l4_threshold(self):
        # Exactly 6.0% L4
        inv = _ms(records=1000, l4=60, llm_cost=0.0)
        assert inv.l4_pct == 6.0
        assert inv.zone == "WARNING"
        assert inv.invariant_pass is True

    def test_warning_between_thresholds(self):
        # 7.0% L4 — above warning (6%) but below red (8%)
        inv = _ms(records=1000, l4=70, llm_cost=0.0)
        assert inv.zone == "WARNING"

    def test_warning_just_below_red_threshold(self):
        # 7.99%
        inv = _ms(records=10000, l4=799, llm_cost=0.0)
        assert inv.l4_pct < DEFAULT_L4_RED_THRESHOLD_PCT
        assert inv.zone == "WARNING"

    def test_warning_cost_approaching_threshold(self):
        # cost approaching: need cost/record strictly above 80% of $0.05 = $0.04.
        # Use 0.041 to avoid the floating-point edge of exactly 0.05 * 0.80.
        # 10 L4 out of 10000 = 0.1% (SAFE by L4); human = 10 × 0.50 = 5.0
        # need total = 410 → llm = 405.0; cost/rec = 410/10000 = 0.041
        inv = _ms(records=10000, l4=10, llm_cost=405.0)
        # human = 5.0; total = 410.0; cost/rec = 0.041 > 0.05 * 0.80 = 0.04
        assert inv.cost_per_record_usd == pytest.approx(0.041, abs=0.000001)
        assert inv.zone == "WARNING"

    def test_warning_reason_mentions_threshold(self):
        inv = _ms(records=1000, l4=65, llm_cost=0.0)
        assert "WARNING threshold" in inv.reason
        assert inv.zone == "WARNING"

    def test_warning_invariant_pass_true(self):
        inv = _ms(records=1000, l4=60, llm_cost=0.0)
        assert inv.invariant_pass is True  # WARNING is not a failure


# ---------------------------------------------------------------------------
# Zone: RED
# ---------------------------------------------------------------------------

class TestRedZone:
    def test_red_at_l4_red_threshold(self):
        # Exactly 8.0% L4
        inv = _ms(records=1000, l4=80, llm_cost=0.0)
        assert inv.l4_pct == 8.0
        assert inv.zone == "RED"
        assert inv.invariant_pass is False

    def test_red_above_l4_threshold(self):
        inv = _ms(records=1000, l4=100, llm_cost=0.0)
        assert inv.zone == "RED"

    def test_red_by_cost_per_record(self):
        # cost/record = $0.05 exactly (the threshold)
        # 1 L4 out of 1000 = 0.1% (SAFE by L4)
        # human: 1 × 0.50 = 0.50; need total = 50.0 → llm = 49.50
        inv = _ms(records=1000, l4=1, llm_cost=49.50)
        # human = 0.50; total = 50.00; cost/rec = 0.05
        assert inv.cost_per_record_usd == pytest.approx(0.05, abs=0.000001)
        assert inv.zone == "RED"

    def test_red_cost_exceeds_threshold(self):
        inv = _ms(records=1000, l4=1, llm_cost=100.0)
        assert inv.cost_per_record_usd > DEFAULT_COST_PER_RECORD_RED_USD
        assert inv.zone == "RED"

    def test_red_both_conditions(self):
        # Both L4 >= red AND cost >= threshold
        inv = _ms(records=1000, l4=100, llm_cost=100.0)
        assert inv.zone == "RED"
        assert "AND" in inv.reason

    def test_red_invariant_pass_false(self):
        inv = _ms(records=1000, l4=80, llm_cost=0.0)
        assert inv.invariant_pass is False

    def test_red_reason_mentions_threshold(self):
        inv = _ms(records=1000, l4=90, llm_cost=0.0)
        assert "RED threshold" in inv.reason


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_zero_records_returns_safe(self):
        inv = _ms(records=0, l4=0, llm_cost=0.0)
        assert inv.zone == "SAFE"
        assert inv.l4_pct == 0.0
        assert inv.cost_per_record_usd == 0.0
        assert inv.total_records == 0
        assert inv.invariant_pass is True

    def test_zero_records_passthrough_l4_count(self):
        inv = _ms(records=0, l4=5, llm_cost=1.0)
        assert inv.total_l4 == 5
        assert inv.human_cost_usd > 0.0  # computed even when records=0

    def test_l4_pct_precision(self):
        # 1/3 * 100 = 33.333...
        inv = _ms(records=3, l4=1, llm_cost=0.0, human_rate=0.0)
        assert inv.l4_pct == round(100 / 3, 3)

    def test_l3_argument_ignored_in_cost(self):
        # total_l3 is informational — shouldn't affect cost calculation
        a = _ms(records=1000, l4=50, l3=0, llm_cost=1.0)
        b = _ms(records=1000, l4=50, l3=200, llm_cost=1.0)
        assert a.total_cost_usd == b.total_cost_usd
        assert a.zone == b.zone


# ---------------------------------------------------------------------------
# Output fields
# ---------------------------------------------------------------------------

class TestOutputFields:
    def test_thresholds_passthrough(self):
        inv = _ms(records=1000, l4=10, llm_cost=0.0, l4_warn=5.0, l4_red=9.0, cost_red=0.10)
        assert inv.thresholds["l4_warning_pct"] == 5.0
        assert inv.thresholds["l4_red_pct"] == 9.0
        assert inv.thresholds["cost_per_record_red_usd"] == 0.10

    def test_human_cost_per_record_passthrough(self):
        inv = _ms(records=1000, l4=10, llm_cost=0.0, human_rate=0.75)
        assert inv.human_cost_per_record_usd == 0.75

    def test_total_l4_passthrough(self):
        inv = _ms(records=1000, l4=77, llm_cost=0.0)
        assert inv.total_l4 == 77

    def test_total_records_passthrough(self):
        inv = _ms(records=5000, l4=50, llm_cost=0.0)
        assert inv.total_records == 5000

    def test_human_cost_rounded_to_4dp(self):
        # 3 × $0.33333 = 0.99999; round(0.99999, 4) = 1.0
        inv = _ms(records=1000, l4=3, llm_cost=0.0, human_rate=1/3)
        assert inv.human_cost_usd == round(3 * (1/3), 4)


# ---------------------------------------------------------------------------
# Baseline validation (from performance doc)
# ---------------------------------------------------------------------------

class TestBaselineValidation:
    def test_baseline_40k_is_safe(self):
        """40K baseline: L3=2.1%, L4=5.0%, LLM=$0.21 → should be SAFE."""
        records = 40000
        l4 = int(records * 0.05)       # 2000
        l3 = int(records * 0.021)      # 840
        llm_cost = 0.21
        inv = _ms(records=records, l4=l4, l3=l3, llm_cost=llm_cost)
        assert inv.zone == "SAFE"
        assert inv.l4_pct == pytest.approx(5.0, abs=0.01)
        assert inv.invariant_pass is True

    def test_double_l4_rate_triggers_warning(self):
        """2× L4 baseline (10%) should trigger RED (above 8% threshold)."""
        records = 40000
        l4 = int(records * 0.10)       # 4000
        inv = _ms(records=records, l4=l4, llm_cost=0.21)
        assert inv.zone == "RED"
        assert inv.invariant_pass is False


# ---------------------------------------------------------------------------
# Default constant values
# ---------------------------------------------------------------------------

def test_default_human_cost():
    assert DEFAULT_HUMAN_COST_PER_RECORD_USD == 0.50

def test_default_l4_warning_threshold():
    assert DEFAULT_L4_WARNING_THRESHOLD_PCT == 6.0

def test_default_l4_red_threshold():
    assert DEFAULT_L4_RED_THRESHOLD_PCT == 8.0

def test_default_cost_per_record_red():
    assert DEFAULT_COST_PER_RECORD_RED_USD == 0.05

def test_cost_approach_fraction():
    assert _COST_APPROACH_FRACTION == 0.80
