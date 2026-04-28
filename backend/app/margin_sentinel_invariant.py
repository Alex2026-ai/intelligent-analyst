"""
margin_sentinel_invariant.py — Pure function module for the Margin Sentinel invariant.

Computes the margin zone (SAFE / WARNING / RED) based on cumulative L4 escalation
rate and total cost-per-record (LLM cost + human review cost).

Performance baseline (40K records):
  L3: 2.1%, L4: 5.0%, LLM cost: $0.21

Human review market rate:
  $0.50–$1.00 per document (remote). Default: $0.50.

Zone thresholds (env-configurable via caller):
  SAFE    — l4_pct < L4_WARNING_THRESHOLD_PCT
             AND cost_per_record < COST_PER_RECORD_RED_USD
  WARNING — l4_pct >= L4_WARNING_THRESHOLD_PCT (but not RED)
             OR cost_per_record approaching RED threshold (>= 80%)
  RED     — l4_pct >= L4_RED_THRESHOLD_PCT
             OR cost_per_record >= COST_PER_RECORD_RED_USD

No server imports. No side effects. Fully unit-testable in isolation.
"""

from dataclasses import dataclass
from typing import Dict

# Default thresholds — match environment variable defaults in Config
DEFAULT_HUMAN_COST_PER_RECORD_USD: float = 0.50
DEFAULT_L4_WARNING_THRESHOLD_PCT: float = 6.0
DEFAULT_L4_RED_THRESHOLD_PCT: float = 8.0
DEFAULT_COST_PER_RECORD_RED_USD: float = 0.05

# Cost approach fraction: fraction of RED threshold that triggers WARNING on cost
_COST_APPROACH_FRACTION: float = 0.80


@dataclass
class MarginInvariant:
    """Result of compute_margin_sentinel()."""

    zone: str                    # "SAFE", "WARNING", or "RED"
    reason: str                  # Human-readable explanation
    l4_pct: float                # Cumulative L4 records / valid_records × 100
    human_cost_usd: float        # total_l4 × human_cost_per_record_usd
    total_cost_usd: float        # total_llm_cost_usd + human_cost_usd
    cost_per_record_usd: float   # total_cost_usd / valid_records (0 if no records)
    invariant_pass: bool         # False only if zone == "RED"
    total_l4: int                # Cumulative L4 count
    total_records: int           # Cumulative valid records (excludes L0 garbage)
    human_cost_per_record_usd: float  # Human review rate in effect
    thresholds: Dict[str, float]  # l4_warning_pct, l4_red_pct, cost_per_record_red_usd


def compute_margin_sentinel(
    total_records: int,
    total_l3: int,
    total_l4: int,
    total_llm_cost_usd: float,
    human_cost_per_record_usd: float = DEFAULT_HUMAN_COST_PER_RECORD_USD,
    l4_warning_threshold_pct: float = DEFAULT_L4_WARNING_THRESHOLD_PCT,
    l4_red_threshold_pct: float = DEFAULT_L4_RED_THRESHOLD_PCT,
    cost_per_record_red_usd: float = DEFAULT_COST_PER_RECORD_RED_USD,
) -> MarginInvariant:
    """
    Compute the margin sentinel zone classification.

    Args:
        total_records: Cumulative valid records (excludes L0 garbage).
        total_l3: Cumulative count of records resolved at L3 (informational).
        total_l4: Cumulative count of records escalated to L4 (human review).
        total_llm_cost_usd: Cumulative L3 LLM spend.
        human_cost_per_record_usd: Per-record human review cost (HUMAN_COST_PER_RECORD_USD).
        l4_warning_threshold_pct: L4% that triggers WARNING zone (L4_WARNING_THRESHOLD_PCT).
        l4_red_threshold_pct: L4% that triggers RED zone (L4_RED_THRESHOLD_PCT).
        cost_per_record_red_usd: Cost/record that triggers RED zone (COST_PER_RECORD_RED_USD).

    Returns:
        MarginInvariant with zone, reason, and cost breakdown.
    """
    thresholds = {
        "l4_warning_pct": l4_warning_threshold_pct,
        "l4_red_pct": l4_red_threshold_pct,
        "cost_per_record_red_usd": cost_per_record_red_usd,
    }

    human_cost_usd = total_l4 * human_cost_per_record_usd
    total_cost_usd = total_llm_cost_usd + human_cost_usd

    if total_records <= 0:
        return MarginInvariant(
            zone="SAFE",
            reason="No valid records processed",
            l4_pct=0.0,
            human_cost_usd=round(human_cost_usd, 4),
            total_cost_usd=round(total_cost_usd, 4),
            cost_per_record_usd=0.0,
            invariant_pass=True,
            total_l4=total_l4,
            total_records=0,
            human_cost_per_record_usd=human_cost_per_record_usd,
            thresholds=thresholds,
        )

    l4_pct = total_l4 / total_records * 100.0
    cost_per_record_usd = total_cost_usd / total_records

    # Zone classification
    cost_red = cost_per_record_usd >= cost_per_record_red_usd
    l4_red = l4_pct >= l4_red_threshold_pct
    l4_warn = l4_pct >= l4_warning_threshold_pct
    cost_approaching = (
        cost_per_record_red_usd > 0
        and cost_per_record_usd >= cost_per_record_red_usd * _COST_APPROACH_FRACTION
    )

    if cost_red or l4_red:
        zone = "RED"
        if cost_red and l4_red:
            reason = (
                f"L4 rate {l4_pct:.1f}% >= RED threshold {l4_red_threshold_pct:.1f}% "
                f"AND cost/record ${cost_per_record_usd:.5f} >= ${cost_per_record_red_usd:.3f}"
            )
        elif l4_red:
            reason = (
                f"L4 rate {l4_pct:.1f}% >= RED threshold {l4_red_threshold_pct:.1f}%"
            )
        else:
            reason = (
                f"Cost/record ${cost_per_record_usd:.5f} >= RED threshold ${cost_per_record_red_usd:.3f}"
            )
    elif l4_warn or cost_approaching:
        zone = "WARNING"
        parts = []
        if l4_warn:
            parts.append(
                f"L4 rate {l4_pct:.1f}% >= WARNING threshold {l4_warning_threshold_pct:.1f}%"
            )
        if cost_approaching:
            parts.append(
                f"cost/record ${cost_per_record_usd:.5f} approaching "
                f"RED threshold ${cost_per_record_red_usd:.3f} "
                f"(>= {int(_COST_APPROACH_FRACTION * 100)}%)"
            )
        reason = "; ".join(parts)
    else:
        zone = "SAFE"
        reason = (
            f"L4 rate {l4_pct:.1f}% < WARNING threshold {l4_warning_threshold_pct:.1f}% "
            f"AND cost/record ${cost_per_record_usd:.5f} < RED threshold ${cost_per_record_red_usd:.3f}"
        )

    return MarginInvariant(
        zone=zone,
        reason=reason,
        l4_pct=round(l4_pct, 3),
        human_cost_usd=round(human_cost_usd, 4),
        total_cost_usd=round(total_cost_usd, 4),
        cost_per_record_usd=round(cost_per_record_usd, 5),
        invariant_pass=(zone != "RED"),
        total_l4=total_l4,
        total_records=total_records,
        human_cost_per_record_usd=human_cost_per_record_usd,
        thresholds=thresholds,
    )
