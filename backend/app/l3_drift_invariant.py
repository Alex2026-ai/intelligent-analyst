"""
l3_drift_invariant.py — Pure function module for L3 drift zone classification.

Computes the drift zone (SAFE / WARNING / RED) based on cumulative L3 and L4
record counts and the most recent batch's L3 cost against the per-batch budget.

Zone thresholds match drift_simulation_v2.py:
  SAFE    — L3 rate < 3.0%
  WARNING — L3 rate >= 3.0% and < 4.5%
  RED     — L3 rate >= 4.5% OR budget cap was hit in the last batch

No server imports. No side effects. Fully unit-testable in isolation.
"""

from dataclasses import dataclass

# Zone threshold constants (shared with drift_simulation_v2.py)
WARN_THRESHOLD_PCT: float = 3.0
RED_THRESHOLD_PCT: float = 4.5


@dataclass
class DriftInvariant:
    """Result of compute_drift_invariant()."""

    zone: str           # "SAFE", "WARNING", or "RED"
    reason: str         # Human-readable explanation for the zone classification
    l3_pct: float       # Cumulative L3 records / valid_records × 100
    l4_pct: float       # Cumulative L4 records / valid_records × 100
    cost_exceeded: bool  # True if last batch spent_usd >= budget_usd
    total_l3: int       # Cumulative L3 record count
    total_l4: int       # Cumulative L4 record count
    total_records: int  # Cumulative valid records (excludes L0 garbage)
    budget_usd: float   # Per-batch L3 budget cap (L3_MAX_COST_USD)
    spent_usd: float    # L3 spend for the most recent batch


def compute_drift_invariant(
    total_l3: int,
    total_l4: int,
    total_valid_records: int,
    spent_usd: float,
    budget_usd: float,
    warn_threshold_pct: float = WARN_THRESHOLD_PCT,
    red_threshold_pct: float = RED_THRESHOLD_PCT,
) -> DriftInvariant:
    """
    Compute the L3 drift zone classification.

    Args:
        total_l3: Cumulative count of records resolved at L3 (LLM).
        total_l4: Cumulative count of records escalated to L4 (human review).
        total_valid_records: Cumulative valid records (excludes L0 garbage).
        spent_usd: L3 spend for the most recent batch.
        budget_usd: Per-batch L3 budget cap (L3_MAX_COST_USD).
        warn_threshold_pct: L3% that triggers WARNING zone (default 3.0).
        red_threshold_pct: L3% that triggers RED zone (default 4.5).

    Returns:
        DriftInvariant with zone, reason, and supporting metrics.
    """
    if total_valid_records <= 0:
        return DriftInvariant(
            zone="SAFE",
            reason="No valid records processed",
            l3_pct=0.0,
            l4_pct=0.0,
            cost_exceeded=False,
            total_l3=total_l3,
            total_l4=total_l4,
            total_records=0,
            budget_usd=budget_usd,
            spent_usd=round(spent_usd, 4),
        )

    l3_pct = total_l3 / total_valid_records * 100.0
    l4_pct = total_l4 / total_valid_records * 100.0
    cost_exceeded = budget_usd > 0 and spent_usd >= budget_usd

    if cost_exceeded:
        zone = "RED"
        reason = (
            f"L3 budget cap hit (${spent_usd:.3f} >= ${budget_usd:.2f}); "
            f"L3={l3_pct:.1f}%"
        )
    elif l3_pct >= red_threshold_pct:
        zone = "RED"
        reason = (
            f"L3 rate {l3_pct:.1f}% >= RED threshold {red_threshold_pct:.1f}%"
        )
    elif l3_pct >= warn_threshold_pct:
        zone = "WARNING"
        reason = (
            f"L3 rate {l3_pct:.1f}% >= WARNING threshold {warn_threshold_pct:.1f}%"
        )
    else:
        zone = "SAFE"
        reason = (
            f"L3 rate {l3_pct:.1f}% < WARNING threshold {warn_threshold_pct:.1f}%"
        )

    return DriftInvariant(
        zone=zone,
        reason=reason,
        l3_pct=round(l3_pct, 3),
        l4_pct=round(l4_pct, 3),
        cost_exceeded=cost_exceeded,
        total_l3=total_l3,
        total_l4=total_l4,
        total_records=total_valid_records,
        budget_usd=budget_usd,
        spent_usd=round(spent_usd, 4),
    )
