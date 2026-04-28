#!/usr/bin/env python3
"""
drift_simulation.py — L3 Traffic Drift Economic Impact Simulation

Analysis-only utility. Read-only. Does not modify engine thresholds,
production config, or any code path.

Usage:
    python3 drift_simulation.py
    python3 drift_simulation.py --records 100000 --revenue-per-record 0.30

Engine constants sourced from:
    backend/app/server_enterprise_golden.py (AppConfig, L3BudgetTracker)
"""

import argparse
from dataclasses import dataclass, field
from typing import List, Optional


# ---------------------------------------------------------------------------
# Engine constants — mirrored from server_enterprise_golden.py AppConfig
# DO NOT MODIFY. These are read-only references.
# ---------------------------------------------------------------------------

ENGINE_L3_COST_PER_CALL_USD: float = 0.005     # AppConfig.L3_COST_PER_CALL_USD default
ENGINE_L3_MAX_COST_USD: float = 10.0           # AppConfig.L3_MAX_COST_USD default
ENGINE_L3_MIN_SIMILARITY: float = 0.30         # AppConfig.L3_MIN_SIMILARITY default

# Derived: max L3 calls before budget exhaustion (mirrors server_enterprise_golden.py:5134)
ENGINE_MAX_L3_CALLS: int = int(ENGINE_L3_MAX_COST_USD / ENGINE_L3_COST_PER_CALL_USD)  # 2000


# ---------------------------------------------------------------------------
# Baseline layer distribution (from production telemetry, CLAUDE.md)
# ---------------------------------------------------------------------------

BASELINE_L0_PCT: float = 5.0    # Garbage / PII quarantine
BASELINE_L1_PCT: float = 80.75  # Deterministic (exact + norm + parent)
BASELINE_L2_PCT: float = 8.0    # Vector similarity
BASELINE_L3_PCT: float = 2.1    # LLM inference (baseline)
BASELINE_L4_PCT: float = 4.15   # Human review
# Sum: 100.0

# L3 yield: proportion of L3 calls that resolve (vs returning UNKNOWN → L4)
# Source: production telemetry. Decreases as drift increases (noisier escalations).
BASELINE_L3_YIELD: float = 0.72  # 72% of L3 calls resolve at baseline

# Yield degradation model: as L3 pct increases, yield drops (more marginal escalations)
# At 2x baseline (4.2%), yield drops by ~10 pts. Configurable below.
YIELD_DEGRADATION_PER_PCT_ABOVE_BASELINE: float = 0.05  # 5 pp yield loss per 1% above baseline


# ---------------------------------------------------------------------------
# Zone thresholds — based on ENGINE_MAX_L3_CALLS relative to total_records
# ---------------------------------------------------------------------------

SAFE_THRESHOLD_PCT: float = 3.0    # L3 < 3.0%: within budget with margin
WARNING_THRESHOLD_PCT: float = 4.5  # 3.0–4.5%: approaching budget cap
# RED: ≥ 4.5% or budget exhausted


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class SimulationInputs:
    total_records: int = 40_000
    baseline_l3_pct: float = BASELINE_L3_PCT
    llm_cost_per_call: float = ENGINE_L3_COST_PER_CALL_USD
    l3_max_cost_usd: float = ENGINE_L3_MAX_COST_USD
    l3_max_calls: int = ENGINE_MAX_L3_CALLS
    baseline_l3_yield: float = BASELINE_L3_YIELD
    revenue_per_record_usd: float = 0.25  # configurable revenue model
    yield_degradation: float = YIELD_DEGRADATION_PER_PCT_ABOVE_BASELINE


@dataclass
class ScenarioResult:
    simulated_l3_pct: float

    # Desired calls (uncapped)
    l3_calls_desired: int
    # Actual calls served (capped by budget)
    l3_calls_served: int
    # Calls blocked by budget cap → forced to L4
    l3_calls_overflowed: int

    l3_yield: float              # Effective yield at this drift level
    l3_calls_resolved: int       # Calls that resolved (served × yield)
    l3_calls_unknown: int        # Calls that returned UNKNOWN (served, still charged)

    l3_cost_usd: float
    baseline_cost_usd: float
    cost_delta_usd: float

    auto_resolved_pct: float     # L0 + L1 + L2 + resolved L3 / total
    l4_pct: float                # Unresolved records escalated to human review
    budget_exhausted: bool

    batch_revenue_usd: float
    margin_impact_pct: float     # cost_delta / batch_revenue * 100

    zone: str
    zone_reason: str

    # Layer breakdown
    l0_count: int
    l1_count: int
    l2_count: int
    l3_count: int                # Records that entered L3 phase (desired)
    l4_count: int


def _classify_zone(
    l3_pct: float,
    budget_exhausted: bool,
    safe_threshold: float = SAFE_THRESHOLD_PCT,
    warning_threshold: float = WARNING_THRESHOLD_PCT,
) -> tuple[str, str]:
    if budget_exhausted or l3_pct >= warning_threshold:
        return "RED", f"L3={l3_pct:.1f}% — budget cap {'exhausted' if budget_exhausted else 'at risk'}; overflow to L4"
    if l3_pct >= safe_threshold:
        return "WARNING", f"L3={l3_pct:.1f}% — above safe threshold ({safe_threshold}%), monitor closely"
    return "SAFE", f"L3={l3_pct:.1f}% — within budget with margin"


def simulate_scenario(
    simulated_l3_pct: float,
    inputs: SimulationInputs,
) -> ScenarioResult:
    """
    Simulate economic impact of a single L3 drift scenario.

    Drift model:
    - Extra L3 volume comes from L2 (records that previously resolved via vector
      similarity now fall below L2 threshold and escalate to L3).
    - L1 and L0 are stable (deterministic layers, unaffected by input drift).
    - L3 yield degrades as drift increases (more marginal escalations, noisier inputs).
    - Calls exceeding the budget cap are blocked and forced to L4 (matches engine
      behavior in L3BudgetTracker.can_run_l3() → L3_BUDGET_EXHAUSTED / L3_CALL_CAP_REACHED).
    """
    n = inputs.total_records

    # --- Layer counts ---
    l0_count = int(n * BASELINE_L0_PCT / 100)
    l1_count = int(n * BASELINE_L1_PCT / 100)

    # L2 absorbs the drift source: when L3 grows, L2 shrinks proportionally
    drift = max(0.0, simulated_l3_pct - inputs.baseline_l3_pct)
    l2_pct = max(0.0, BASELINE_L2_PCT - drift)
    l2_count = int(n * l2_pct / 100)

    l3_desired_pct = simulated_l3_pct
    l3_calls_desired = int(n * l3_desired_pct / 100)

    # Budget cap: mirrors engine max_l3_calls computation
    l3_calls_served = min(l3_calls_desired, inputs.l3_max_calls)
    l3_calls_overflowed = max(0, l3_calls_desired - l3_calls_served)
    budget_exhausted = l3_calls_overflowed > 0

    # Yield degradation model
    effective_yield = max(
        0.10,  # floor: even in worst case, LLM resolves some
        inputs.baseline_l3_yield - (drift * inputs.yield_degradation),
    )

    l3_calls_resolved = int(l3_calls_served * effective_yield)
    l3_calls_unknown = l3_calls_served - l3_calls_resolved  # charged, not resolved

    # L3 count (records that entered L3 phase, regardless of outcome)
    l3_count = l3_calls_desired

    # L4: baseline L4 + L3 unknown + L3 overflow (cap-blocked)
    l4_from_baseline = int(n * BASELINE_L4_PCT / 100)
    l4_extra = l3_calls_unknown + l3_calls_overflowed
    l4_count = l4_from_baseline + l4_extra

    # Costs
    l3_cost_usd = l3_calls_served * inputs.llm_cost_per_call
    baseline_l3_calls = int(n * inputs.baseline_l3_pct / 100)
    baseline_cost_usd = min(baseline_l3_calls, inputs.l3_max_calls) * inputs.llm_cost_per_call
    cost_delta_usd = l3_cost_usd - baseline_cost_usd

    # Auto-resolved: everything except L4
    auto_resolved = l0_count + l1_count + l2_count + l3_calls_resolved
    auto_resolved_pct = (auto_resolved / n) * 100 if n > 0 else 0.0
    l4_pct = (l4_count / n) * 100 if n > 0 else 0.0

    # Revenue and margin
    batch_revenue_usd = n * inputs.revenue_per_record_usd
    margin_impact_pct = (cost_delta_usd / batch_revenue_usd * 100) if batch_revenue_usd > 0 else 0.0

    zone, zone_reason = _classify_zone(simulated_l3_pct, budget_exhausted)

    return ScenarioResult(
        simulated_l3_pct=simulated_l3_pct,
        l3_calls_desired=l3_calls_desired,
        l3_calls_served=l3_calls_served,
        l3_calls_overflowed=l3_calls_overflowed,
        l3_yield=round(effective_yield * 100, 1),
        l3_calls_resolved=l3_calls_resolved,
        l3_calls_unknown=l3_calls_unknown,
        l3_cost_usd=round(l3_cost_usd, 4),
        baseline_cost_usd=round(baseline_cost_usd, 4),
        cost_delta_usd=round(cost_delta_usd, 4),
        auto_resolved_pct=round(auto_resolved_pct, 2),
        l4_pct=round(l4_pct, 2),
        budget_exhausted=budget_exhausted,
        batch_revenue_usd=round(batch_revenue_usd, 2),
        margin_impact_pct=round(margin_impact_pct, 3),
        zone=zone,
        zone_reason=zone_reason,
        l0_count=l0_count,
        l1_count=l1_count,
        l2_count=l2_count,
        l3_count=l3_count,
        l4_count=l4_count,
    )


def compute_suggested_l3_cap(inputs: SimulationInputs) -> dict:
    """
    Compute the recommended max L3 cap for a given batch size and budget.
    Target: 80% of budget utilization at cap.
    """
    target_spend_usd = inputs.l3_max_cost_usd * 0.80
    target_calls = int(target_spend_usd / inputs.llm_cost_per_call)
    target_pct = (target_calls / inputs.total_records) * 100
    return {
        "target_spend_usd": round(target_spend_usd, 2),
        "target_calls": target_calls,
        "target_pct": round(target_pct, 2),
        "l3_max_cost_usd_recommended": round(target_spend_usd, 2),
        "rationale": f"80% of ENGINE_L3_MAX_COST_USD (${inputs.l3_max_cost_usd:.2f}) "
                     f"= ${target_spend_usd:.2f} = {target_calls} calls = {target_pct:.1f}% of {inputs.total_records:,} records",
    }


# ---------------------------------------------------------------------------
# Console report
# ---------------------------------------------------------------------------

ZONE_LABELS = {
    "SAFE":    "[ SAFE ZONE    ]",
    "WARNING": "[ WARNING ZONE ]",
    "RED":     "[ RED ZONE     ]",
}

ZONE_DIVIDERS = {
    "SAFE":    "-",
    "WARNING": "=",
    "RED":     "#",
}


def _divider(char: str = "-", width: int = 72) -> str:
    return char * width


def print_report(
    scenarios: List[ScenarioResult],
    inputs: SimulationInputs,
    cap: dict,
) -> None:
    w = 72
    print()
    print(_divider("=", w))
    print("  L3 DRIFT SIMULATION REPORT")
    print(f"  Intelligent Analyst v3.0 — Engine Hardening Analysis")
    print(_divider("=", w))
    print(f"  total_records          : {inputs.total_records:>10,}")
    print(f"  baseline_l3_pct        : {inputs.baseline_l3_pct:>9.1f}%")
    print(f"  llm_cost_per_call      : ${inputs.llm_cost_per_call:>9.4f}")
    print(f"  l3_max_cost_usd        : ${inputs.l3_max_cost_usd:>9.2f}")
    print(f"  engine_max_l3_calls    : {inputs.l3_max_calls:>10,}")
    print(f"  budget_cap_pct         : {inputs.l3_max_calls / inputs.total_records * 100:>9.2f}%")
    print(f"  baseline_l3_yield      : {inputs.baseline_l3_yield * 100:>9.1f}%")
    print(f"  revenue_per_record     : ${inputs.revenue_per_record_usd:>9.2f}")
    print(f"  batch_revenue          : ${inputs.total_records * inputs.revenue_per_record_usd:>9,.2f}")
    print(_divider("-", w))
    print(f"  {'Scenario':<10} {'L3%':>5}  {'Calls':>6}  {'Served':>6}  {'Overflow':>8}  "
          f"{'Cost':>7}  {'Delta':>7}  {'AutoRes%':>8}  {'L4%':>5}  {'Margin':>7}")
    print(_divider("-", w))

    for s in scenarios:
        overflow_str = f"{s.l3_calls_overflowed:>8,}" if s.l3_calls_overflowed > 0 else f"{'—':>8}"
        delta_str = f"+${s.cost_delta_usd:.2f}" if s.cost_delta_usd >= 0 else f"-${abs(s.cost_delta_usd):.2f}"
        margin_str = f"+{s.margin_impact_pct:.2f}%" if s.margin_impact_pct >= 0 else f"{s.margin_impact_pct:.2f}%"
        print(
            f"  {s.simulated_l3_pct:<10.1f}  {s.simulated_l3_pct:>4.1f}%  "
            f"{s.l3_calls_desired:>6,}  {s.l3_calls_served:>6,}  {overflow_str}  "
            f"${s.l3_cost_usd:>6.2f}  {delta_str:>8}  {s.auto_resolved_pct:>7.2f}%  "
            f"{s.l4_pct:>4.2f}%  {margin_str:>7}"
        )

    print(_divider("=", w))
    print()

    # Per-scenario detail blocks
    for s in scenarios:
        div_char = ZONE_DIVIDERS[s.zone]
        print(_divider(div_char, w))
        print(f"  {ZONE_LABELS[s.zone]}  L3 = {s.simulated_l3_pct:.1f}%")
        print(_divider(div_char, w))
        print(f"  Zone reason     : {s.zone_reason}")
        print()
        print(f"  Layer breakdown ({inputs.total_records:,} records):")
        print(f"    L0 garbage      : {s.l0_count:>8,}  ({s.l0_count / inputs.total_records * 100:.1f}%)")
        print(f"    L1 deterministic: {s.l1_count:>8,}  ({s.l1_count / inputs.total_records * 100:.1f}%)")
        print(f"    L2 vector       : {s.l2_count:>8,}  ({s.l2_count / inputs.total_records * 100:.1f}%)")
        print(f"    L3 desired      : {s.l3_calls_desired:>8,}  ({s.simulated_l3_pct:.1f}%)")
        print(f"    L3 served       : {s.l3_calls_served:>8,}  (yield {s.l3_yield:.1f}%  → {s.l3_calls_resolved:,} resolved / {s.l3_calls_unknown:,} UNKNOWN)")
        if s.l3_calls_overflowed > 0:
            print(f"    L3 overflowed   : {s.l3_calls_overflowed:>8,}  ** BUDGET CAP — forced to L4 **")
        print(f"    L4 human review : {s.l4_count:>8,}  ({s.l4_pct:.2f}%)")
        print()
        print(f"  Economics:")
        print(f"    L3 cost         : ${s.l3_cost_usd:.4f}")
        print(f"    Baseline cost   : ${s.baseline_cost_usd:.4f}")
        print(f"    Cost delta      : ${s.cost_delta_usd:+.4f}")
        print(f"    Batch revenue   : ${s.batch_revenue_usd:,.2f}")
        print(f"    Margin impact   : {s.margin_impact_pct:+.3f}%")
        print(f"    Auto-resolved   : {s.auto_resolved_pct:.2f}%")
        print(f"    Budget exhausted: {'YES — calls capped at ' + str(inputs.l3_max_calls) if s.budget_exhausted else 'No'}")
        print()

    # Suggested cap
    print(_divider("=", w))
    print("  SUGGESTED MAX L3 CAP")
    print(_divider("=", w))
    print(f"  {cap['rationale']}")
    print()
    print(f"  Recommended L3_MAX_COST_USD : ${cap['l3_max_cost_usd_recommended']:.2f}")
    print(f"  Effective call cap          : {cap['target_calls']:,}")
    print(f"  Effective L3 rate cap       : {cap['target_pct']:.1f}% of {inputs.total_records:,} records")
    print()
    print("  To apply (without deploy — env var override at runtime):")
    print(f"    L3_MAX_COST_USD={cap['l3_max_cost_usd_recommended']:.2f}")
    print()
    print("  Note: This does not change engine thresholds. It adjusts the per-batch")
    print("  budget guard in L3BudgetTracker. The L3 resolution path is unchanged.")
    print(_divider("=", w))
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="L3 Drift Economic Impact Simulation — analysis only, no engine changes",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--records", type=int, default=40_000, help="Total records per batch")
    parser.add_argument("--baseline-l3-pct", type=float, default=BASELINE_L3_PCT, help="Baseline L3 percentage")
    parser.add_argument("--revenue-per-record", type=float, default=0.25, help="Revenue per record (USD)")
    parser.add_argument("--l3-max-cost", type=float, default=ENGINE_L3_MAX_COST_USD, help="L3 budget cap (USD)")
    parser.add_argument(
        "--scenarios", type=float, nargs="+",
        default=[2.1, 4.0, 6.0, 10.0],
        help="L3 percentages to simulate",
    )
    args = parser.parse_args()

    inputs = SimulationInputs(
        total_records=args.records,
        baseline_l3_pct=args.baseline_l3_pct,
        llm_cost_per_call=ENGINE_L3_COST_PER_CALL_USD,
        l3_max_cost_usd=args.l3_max_cost,
        l3_max_calls=int(args.l3_max_cost / ENGINE_L3_COST_PER_CALL_USD),
        baseline_l3_yield=BASELINE_L3_YIELD,
        revenue_per_record_usd=args.revenue_per_record,
        yield_degradation=YIELD_DEGRADATION_PER_PCT_ABOVE_BASELINE,
    )

    scenarios = [simulate_scenario(pct, inputs) for pct in args.scenarios]
    cap = compute_suggested_l3_cap(inputs)
    print_report(scenarios, inputs, cap)


if __name__ == "__main__":
    main()
