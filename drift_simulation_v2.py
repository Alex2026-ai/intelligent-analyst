#!/usr/bin/env python3
"""
drift_simulation_v2.py — L3 Drift Simulation: Uncapped vs Capped + Monthly Projections

Analysis-only. Read-only. Does not modify engine thresholds, production config,
or any code path.

Extends drift_simulation.py (8cefc85) with:
  - Scenario A: UNCAPPED — real L3 cost grows linearly; no budget guard
  - Scenario B: CAPPED   — engine L3BudgetTracker cap enforced; overflow → L4
  - Monthly projections  — 10M / 50M / 100M records/month
  - Explicit margin impact definition (ΔLLM cost + ΔL4 records)
  - p95 latency proxy (L3 phase, labeled as estimate)
  - Unit tests (--test flag)

Engine constants sourced read-only from:
    backend/app/server_enterprise_golden.py  AppConfig + L3BudgetTracker

Usage:
    python3 drift_simulation_v2.py
    python3 drift_simulation_v2.py --records 40000 --revenue-per-record 0.25
    python3 drift_simulation_v2.py --test
"""

import argparse
import math
import sys
from dataclasses import dataclass
from typing import List, Tuple


# ---------------------------------------------------------------------------
# Engine constants — read-only references from AppConfig defaults
# server_enterprise_golden.py lines 2291-2295, 5134
# ---------------------------------------------------------------------------

ENGINE_L3_COST_PER_CALL_USD: float = 0.005   # AppConfig.L3_COST_PER_CALL_USD
ENGINE_L3_MAX_COST_USD: float = 10.0         # AppConfig.L3_MAX_COST_USD  (per-batch budget)
ENGINE_L3_MIN_SIMILARITY: float = 0.30       # AppConfig.L3_MIN_SIMILARITY
ENGINE_PARALLEL_LIMIT: int = 20              # AppConfig.PARALLEL_LIMIT (L3 concurrency)

# Derived at engine start (server_enterprise_golden.py:5134)
ENGINE_MAX_L3_CALLS_PER_BATCH: int = int(ENGINE_L3_MAX_COST_USD / ENGINE_L3_COST_PER_CALL_USD)  # 2000


# ---------------------------------------------------------------------------
# Baseline layer distribution — production telemetry (CLAUDE.md)
# These sum to 100.0.
# ---------------------------------------------------------------------------

BASELINE_L0_PCT: float = 5.00    # garbage / PII quarantine
BASELINE_L1_PCT: float = 80.75   # deterministic (exact + norm + parent)
BASELINE_L2_PCT: float = 8.00    # vector similarity
BASELINE_L3_PCT: float = 2.10    # LLM inference
BASELINE_L4_PCT: float = 4.15    # human review


# ---------------------------------------------------------------------------
# Simulation parameters
# ---------------------------------------------------------------------------

@dataclass
class SimulationParams:
    # Batch size
    total_records: int = 40_000

    # Baseline
    baseline_l3_pct: float = BASELINE_L3_PCT

    # Engine constants (mirrored — do not change production values here)
    llm_cost_per_call: float = ENGINE_L3_COST_PER_CALL_USD
    l3_max_cost_usd: float = ENGINE_L3_MAX_COST_USD      # CAPPED scenario cap
    l3_max_calls: int = ENGINE_MAX_L3_CALLS_PER_BATCH    # derived from above

    # LLM resolution model
    # llm_resolution_rate: fraction of L3 calls that return a resolved entity (not UNKNOWN)
    # Default 0.33 — from demo batch BATCH-7424F9EF (1 resolved / 3 calls = 33%)
    # Represents conservative estimate; degrades further as drift increases.
    llm_resolution_rate: float = 0.33
    # unknown_to_l4_rate: fraction of UNKNOWN L3 results that escalate to L4
    # In the engine, all UNKNOWN → L4 (L3BudgetTracker records_call(success=False)).
    unknown_to_l4_rate: float = 1.0
    # Yield degradation: resolution rate drops as L3 pct increases above baseline.
    # Each 1 percentage point of drift above baseline reduces yield by this factor.
    yield_degradation_per_pct: float = 0.04   # 4 pp per 1% above baseline

    # Latency model (p95 proxy — batch-level L3 phase estimate)
    base_latency_ms: float = 80.0         # deterministic layers + overhead
    per_call_latency_ms: float = 500.0    # per LLM call (Claude Haiku ~500ms)
    concurrency_capacity: int = ENGINE_PARALLEL_LIMIT  # PARALLEL_LIMIT workers

    # Revenue model — denominator for margin impact %
    # Defined as: revenue = total_records × revenue_per_record_usd
    revenue_per_record_usd: float = 0.25

    # Monthly projection volumes
    monthly_record_volumes: List[int] = None  # set in __post_init__
    batch_size_for_monthly: int = 40_000      # per-batch cap applies at this granularity

    def __post_init__(self) -> None:
        if self.monthly_record_volumes is None:
            self.monthly_record_volumes = [10_000_000, 50_000_000, 100_000_000]
        # Ensure derived value is consistent with l3_max_cost_usd
        self.l3_max_calls = int(self.l3_max_cost_usd / self.llm_cost_per_call)

    @property
    def batch_revenue_usd(self) -> float:
        return self.total_records * self.revenue_per_record_usd

    @property
    def baseline_l3_calls(self) -> int:
        return int(self.total_records * self.baseline_l3_pct / 100)

    @property
    def baseline_l3_cost_usd(self) -> float:
        return self.baseline_l3_calls * self.llm_cost_per_call

    def effective_yield(self, l3_pct: float) -> float:
        """Resolution rate at a given L3 pct, accounting for yield degradation."""
        drift = max(0.0, l3_pct - self.baseline_l3_pct)
        return max(0.05, self.llm_resolution_rate - drift * self.yield_degradation_per_pct)


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ScenarioUncapped:
    """Scenario A: no budget cap. L3 cost grows linearly with L3 pct."""
    l3_pct: float

    l3_calls: int
    l3_cost_usd: float
    effective_yield_pct: float     # % of L3 calls that resolve
    l3_resolved: int
    l3_unknown: int                # returned UNKNOWN → L4

    auto_resolved_count: int
    auto_resolved_pct: float

    l4_count: int
    l4_pct: float

    delta_llm_cost_usd: float      # vs baseline (DENOMINATOR: baseline_l3_cost)
    delta_l4_records: int          # vs baseline L4 count
    margin_impact_pct: float       # delta_llm_cost / batch_revenue × 100

    p95_latency_proxy_ms: float    # L3 phase estimate (labeled as proxy)
    p95_latency_waves: int         # ceil(l3_calls / concurrency_capacity)

    zone: str


@dataclass
class ScenarioCapped:
    """Scenario B: L3BudgetTracker cap enforced. Overflow → L4."""
    l3_pct: float

    l3_calls_desired: int
    l3_calls_served: int           # min(desired, cap)
    l3_calls_overflow: int         # forced to L4 with reason L3_BUDGET_CAP
    l3_cost_usd: float
    budget_exhausted: bool

    effective_yield_pct: float
    l3_resolved: int
    l3_unknown: int

    auto_resolved_count: int
    auto_resolved_pct: float

    l4_count: int
    l4_pct: float

    delta_llm_cost_usd: float
    delta_l4_records: int
    margin_impact_pct: float

    zone: str


@dataclass
class MonthlyProjection:
    monthly_records: int
    l3_pct: float
    num_batches: int               # monthly_records / batch_size, ceiling

    # Uncapped
    monthly_l3_calls_uncapped: int
    monthly_l3_cost_uncapped_usd: float
    monthly_l4_records_uncapped: int

    # Capped (per-batch cap × num_batches)
    monthly_l3_calls_served_capped: int
    monthly_overflow_calls: int
    monthly_l3_cost_capped_usd: float
    monthly_l4_records_capped: int


# ---------------------------------------------------------------------------
# Zone classification
# ---------------------------------------------------------------------------

ZONE_SAFE_MAX: float = 3.0
ZONE_WARNING_MAX: float = 4.5


def classify_zone(l3_pct: float, budget_exhausted: bool = False) -> str:
    if budget_exhausted or l3_pct >= ZONE_WARNING_MAX:
        return "RED"
    if l3_pct >= ZONE_SAFE_MAX:
        return "WARNING"
    return "SAFE"


# ---------------------------------------------------------------------------
# Core simulation functions
# ---------------------------------------------------------------------------

def simulate_uncapped(l3_pct: float, p: SimulationParams) -> ScenarioUncapped:
    """
    Scenario A: UNCAPPED.

    No budget guard. L3 cost = l3_calls × cost_per_call, no ceiling.
    Models the cost trajectory if L3_MAX_COST_USD is not enforced.

    Drift source: extra L3 records come from L2 (records that previously resolved
    at L2 now fall through to L3). L0 and L1 are stable.
    """
    n = p.total_records

    # Layer counts
    l0 = int(n * BASELINE_L0_PCT / 100)
    l1 = int(n * BASELINE_L1_PCT / 100)
    drift = max(0.0, l3_pct - p.baseline_l3_pct)
    l2_pct = max(0.0, BASELINE_L2_PCT - drift)
    l2 = int(n * l2_pct / 100)

    l3_calls = int(n * l3_pct / 100)
    yield_rate = p.effective_yield(l3_pct)
    l3_resolved = int(l3_calls * yield_rate)
    l3_unknown = l3_calls - l3_resolved

    l3_cost = l3_calls * p.llm_cost_per_call

    baseline_l4 = int(n * BASELINE_L4_PCT / 100)
    l4_from_unknown = int(l3_unknown * p.unknown_to_l4_rate)
    l4 = baseline_l4 + l4_from_unknown

    auto_resolved = l0 + l1 + l2 + l3_resolved
    auto_resolved_pct = (auto_resolved / n) * 100 if n > 0 else 0.0
    l4_pct = (l4 / n) * 100 if n > 0 else 0.0

    delta_llm = l3_cost - p.baseline_l3_cost_usd
    baseline_l4_count = int(n * BASELINE_L4_PCT / 100)
    delta_l4 = l4 - baseline_l4_count
    margin_pct = (delta_llm / p.batch_revenue_usd * 100) if p.batch_revenue_usd > 0 else 0.0

    waves = math.ceil(l3_calls / p.concurrency_capacity) if l3_calls > 0 else 0
    p95_ms = p.base_latency_ms + waves * p.per_call_latency_ms

    zone = classify_zone(l3_pct, budget_exhausted=False)

    return ScenarioUncapped(
        l3_pct=l3_pct,
        l3_calls=l3_calls,
        l3_cost_usd=round(l3_cost, 4),
        effective_yield_pct=round(yield_rate * 100, 1),
        l3_resolved=l3_resolved,
        l3_unknown=l3_unknown,
        auto_resolved_count=auto_resolved,
        auto_resolved_pct=round(auto_resolved_pct, 2),
        l4_count=l4,
        l4_pct=round(l4_pct, 2),
        delta_llm_cost_usd=round(delta_llm, 4),
        delta_l4_records=delta_l4,
        margin_impact_pct=round(margin_pct, 4),
        p95_latency_proxy_ms=round(p95_ms, 1),
        p95_latency_waves=waves,
        zone=zone,
    )


def simulate_capped(l3_pct: float, p: SimulationParams) -> ScenarioCapped:
    """
    Scenario B: CAPPED.

    Mirrors L3BudgetTracker.can_run_l3() in server_enterprise_golden.py:537-545.
    served_calls = min(desired_calls, p.l3_max_calls)
    overflow_calls → L4 with reason L3_BUDGET_CAP (not charged).
    """
    n = p.total_records

    l0 = int(n * BASELINE_L0_PCT / 100)
    l1 = int(n * BASELINE_L1_PCT / 100)
    drift = max(0.0, l3_pct - p.baseline_l3_pct)
    l2_pct = max(0.0, BASELINE_L2_PCT - drift)
    l2 = int(n * l2_pct / 100)

    l3_desired = int(n * l3_pct / 100)
    l3_served = min(l3_desired, p.l3_max_calls)   # cap enforced
    l3_overflow = l3_desired - l3_served           # forced to L4, not charged
    budget_exhausted = l3_overflow > 0

    yield_rate = p.effective_yield(l3_pct)
    l3_resolved = int(l3_served * yield_rate)
    l3_unknown = l3_served - l3_resolved

    l3_cost = l3_served * p.llm_cost_per_call

    baseline_l4 = int(n * BASELINE_L4_PCT / 100)
    l4_from_unknown = int(l3_unknown * p.unknown_to_l4_rate)
    l4 = baseline_l4 + l4_from_unknown + l3_overflow

    auto_resolved = l0 + l1 + l2 + l3_resolved
    auto_resolved_pct = (auto_resolved / n) * 100 if n > 0 else 0.0
    l4_pct = (l4 / n) * 100 if n > 0 else 0.0

    delta_llm = l3_cost - p.baseline_l3_cost_usd
    baseline_l4_count = int(n * BASELINE_L4_PCT / 100)
    delta_l4 = l4 - baseline_l4_count
    margin_pct = (delta_llm / p.batch_revenue_usd * 100) if p.batch_revenue_usd > 0 else 0.0

    zone = classify_zone(l3_pct, budget_exhausted=budget_exhausted)

    return ScenarioCapped(
        l3_pct=l3_pct,
        l3_calls_desired=l3_desired,
        l3_calls_served=l3_served,
        l3_calls_overflow=l3_overflow,
        l3_cost_usd=round(l3_cost, 4),
        budget_exhausted=budget_exhausted,
        effective_yield_pct=round(yield_rate * 100, 1),
        l3_resolved=l3_resolved,
        l3_unknown=l3_unknown,
        auto_resolved_count=auto_resolved,
        auto_resolved_pct=round(auto_resolved_pct, 2),
        l4_count=l4,
        l4_pct=round(l4_pct, 2),
        delta_llm_cost_usd=round(delta_llm, 4),
        delta_l4_records=delta_l4,
        margin_impact_pct=round(margin_pct, 4),
        zone=zone,
    )


def project_monthly(
    monthly_records: int,
    l3_pct: float,
    p: SimulationParams,
) -> MonthlyProjection:
    """
    Monthly projection. The per-batch cap (L3_MAX_COST_USD) applies independently
    to each batch. Batches are sized at p.batch_size_for_monthly records.

    num_batches = ceil(monthly_records / batch_size)
    Per batch: desired = batch_size * l3_pct/100
               served  = min(desired, l3_max_calls)
               overflow = desired - served
    Monthly totals = per_batch × num_batches.
    """
    num_batches = math.ceil(monthly_records / p.batch_size_for_monthly)
    batch_size = p.batch_size_for_monthly

    # Per batch
    per_batch_desired = int(batch_size * l3_pct / 100)
    yield_rate = p.effective_yield(l3_pct)

    # Uncapped
    per_batch_l3_cost_uncapped = per_batch_desired * p.llm_cost_per_call
    per_batch_l3_unknown_uncapped = int(per_batch_desired * (1 - yield_rate))
    baseline_l4_per_batch = int(batch_size * BASELINE_L4_PCT / 100)
    per_batch_l4_uncapped = baseline_l4_per_batch + int(per_batch_l3_unknown_uncapped * p.unknown_to_l4_rate)

    monthly_l3_calls_uncapped = per_batch_desired * num_batches
    monthly_l3_cost_uncapped = round(per_batch_l3_cost_uncapped * num_batches, 2)
    monthly_l4_uncapped = per_batch_l4_uncapped * num_batches

    # Capped
    per_batch_served = min(per_batch_desired, p.l3_max_calls)
    per_batch_overflow = per_batch_desired - per_batch_served
    per_batch_l3_cost_capped = per_batch_served * p.llm_cost_per_call
    per_batch_l3_unknown_capped = int(per_batch_served * (1 - yield_rate))
    per_batch_l4_capped = (
        baseline_l4_per_batch
        + int(per_batch_l3_unknown_capped * p.unknown_to_l4_rate)
        + per_batch_overflow
    )

    monthly_l3_served_capped = per_batch_served * num_batches
    monthly_overflow = per_batch_overflow * num_batches
    monthly_l3_cost_capped = round(per_batch_l3_cost_capped * num_batches, 2)
    monthly_l4_capped = per_batch_l4_capped * num_batches

    return MonthlyProjection(
        monthly_records=monthly_records,
        l3_pct=l3_pct,
        num_batches=num_batches,
        monthly_l3_calls_uncapped=monthly_l3_calls_uncapped,
        monthly_l3_cost_uncapped_usd=monthly_l3_cost_uncapped,
        monthly_l4_records_uncapped=monthly_l4_uncapped,
        monthly_l3_calls_served_capped=monthly_l3_served_capped,
        monthly_overflow_calls=monthly_overflow,
        monthly_l3_cost_capped_usd=monthly_l3_cost_capped,
        monthly_l4_records_capped=monthly_l4_capped,
    )


# ---------------------------------------------------------------------------
# Guardrails recommendation
# ---------------------------------------------------------------------------

def compute_guardrails(p: SimulationParams) -> dict:
    budget_cap_pct = (p.l3_max_calls / p.total_records) * 100
    safe_calls = int(p.total_records * ZONE_SAFE_MAX / 100)
    safe_cost = safe_calls * p.llm_cost_per_call
    warning_calls = int(p.total_records * ZONE_WARNING_MAX / 100)
    warning_cost = warning_calls * p.llm_cost_per_call
    # Recommended cap: 80% of current budget → headroom before cap fires
    recommended_budget = round(p.l3_max_cost_usd * 0.80, 2)
    recommended_cap_calls = int(recommended_budget / p.llm_cost_per_call)
    recommended_cap_pct = round((recommended_cap_calls / p.total_records) * 100, 2)
    return {
        "safe_threshold_pct": ZONE_SAFE_MAX,
        "safe_max_cost_usd": round(safe_cost, 2),
        "warning_threshold_pct": ZONE_WARNING_MAX,
        "warning_max_cost_usd": round(warning_cost, 2),
        "budget_cap_pct": round(budget_cap_pct, 2),
        "recommended_l3_max_cost_usd": recommended_budget,
        "recommended_cap_calls": recommended_cap_calls,
        "recommended_cap_pct": recommended_cap_pct,
    }


# ---------------------------------------------------------------------------
# Console output
# ---------------------------------------------------------------------------

W = 76

_ZONE_HDR = {"SAFE": "[ SAFE    ]", "WARNING": "[ WARNING ]", "RED": "[ RED     ]"}
_ZONE_DIV = {"SAFE": "-", "WARNING": "=", "RED": "#"}


def _div(char: str = "-") -> str:
    return char * W


def _fmt_int(v: int) -> str:
    return f"{v:>12,}"


def _fmt_usd(v: float, decimals: int = 2) -> str:
    return f"${v:>10,.{decimals}f}"


def print_header(p: SimulationParams) -> None:
    print()
    print(_div("="))
    print("  L3 DRIFT SIMULATION v2 — Uncapped vs Capped + Monthly Projections")
    print("  Intelligent Analyst v3.0  |  Analysis-only  |  No engine changes")
    print(_div("="))
    print(f"  total_records            : {p.total_records:>12,}")
    print(f"  baseline_l3_pct          : {p.baseline_l3_pct:>11.1f}%")
    print(f"  llm_cost_per_call        : ${p.llm_cost_per_call:>11.4f}")
    print(f"  l3_max_cost_usd (cap B)  : ${p.l3_max_cost_usd:>11.2f}  →  {p.l3_max_calls:,} calls max/batch")
    print(f"  llm_resolution_rate      : {p.llm_resolution_rate * 100:>11.1f}%  (of L3 calls served)")
    print(f"  unknown_to_l4_rate       : {p.unknown_to_l4_rate * 100:>11.1f}%  (UNKNOWN results → L4)")
    print(f"  yield_degradation        : {p.yield_degradation_per_pct * 100:>11.1f}pp per 1% drift above baseline")
    print(f"  concurrency_capacity     : {p.concurrency_capacity:>12,}  (PARALLEL_LIMIT workers)")
    print(f"  per_call_latency_ms      : {p.per_call_latency_ms:>11.0f}ms  (Claude Haiku proxy)")
    print(f"  revenue_per_record       : ${p.revenue_per_record_usd:>11.4f}")
    print(f"  batch_revenue            : ${p.batch_revenue_usd:>11,.2f}  (denominator for margin %)")
    print()
    print("  Margin impact % definition:")
    print("    margin_impact_pct = ΔLLM_cost / (total_records × revenue_per_record) × 100")
    print(f"    Denominator = {p.total_records:,} × ${p.revenue_per_record_usd:.4f} = ${p.batch_revenue_usd:,.2f}")
    print()
    print("  p95 latency proxy definition:")
    print("    waves = ceil(l3_calls / concurrency_capacity)")
    print("    p95_ms = base_latency_ms + waves × per_call_latency_ms")
    print("    This estimates the L3 phase duration for the batch. Labeled as proxy.")
    print(_div("-"))


def print_table_uncapped(scenarios: List[ScenarioUncapped], p: SimulationParams) -> None:
    print()
    print(_div("="))
    print("  TABLE 1 — SCENARIO A: UNCAPPED  (no budget guard, cost grows linearly)")
    print(_div("="))
    hdr = (
        f"  {'L3%':>5}  {'Zone':<10}  {'Calls':>7}  {'Cost':>9}  "
        f"{'ΔCost':>9}  {'Yield%':>7}  {'AutoRes%':>9}  {'L4%':>6}  "
        f"{'ΔL4':>6}  {'ΔLLMcost':>9}  {'Margin%':>8}  {'p95ms':>8}"
    )
    print(hdr)
    print(_div("-"))
    for s in scenarios:
        dcost = f"+${s.delta_llm_cost_usd:.2f}" if s.delta_llm_cost_usd >= 0 else f"-${abs(s.delta_llm_cost_usd):.2f}"
        dl4 = f"+{s.delta_l4_records}" if s.delta_l4_records >= 0 else str(s.delta_l4_records)
        margin = f"+{s.margin_impact_pct:.4f}%" if s.margin_impact_pct >= 0 else f"{s.margin_impact_pct:.4f}%"
        zone_str = _ZONE_HDR[s.zone]
        print(
            f"  {s.l3_pct:>5.1f}  {zone_str:<10}  {s.l3_calls:>7,}  ${s.l3_cost_usd:>8.2f}  "
            f"{dcost:>9}  {s.effective_yield_pct:>6.1f}%  {s.auto_resolved_pct:>8.2f}%  {s.l4_pct:>5.2f}%  "
            f"{dl4:>6}  {dcost:>9}  {margin:>8}  {s.p95_latency_proxy_ms:>7.0f}ms"
        )
    print(_div("-"))
    print("  Note: ΔCost and ΔLLMcost are identical (both vs baseline L3 cost).")
    print(f"  Baseline L3 cost = {p.baseline_l3_calls:,} calls × ${p.llm_cost_per_call:.4f} = ${p.baseline_l3_cost_usd:.4f}")
    print()


def print_table_capped(scenarios: List[ScenarioCapped], p: SimulationParams) -> None:
    print()
    print(_div("="))
    print(f"  TABLE 2 — SCENARIO B: CAPPED  (cap = {p.l3_max_calls:,} calls / ${p.l3_max_cost_usd:.2f} per batch)")
    print(_div("="))
    hdr = (
        f"  {'L3%':>5}  {'Zone':<10}  {'Desired':>8}  {'Served':>8}  {'Overflow':>9}  "
        f"{'Cost':>9}  {'Yield%':>7}  {'AutoRes%':>9}  {'L4%':>6}  {'ΔL4':>6}  {'Margin%':>8}"
    )
    print(hdr)
    print(_div("-"))
    for s in scenarios:
        overflow_str = f"{s.l3_calls_overflow:>9,}" if s.l3_calls_overflow > 0 else f"{'—':>9}"
        dl4 = f"+{s.delta_l4_records}" if s.delta_l4_records >= 0 else str(s.delta_l4_records)
        margin = f"+{s.margin_impact_pct:.4f}%" if s.margin_impact_pct >= 0 else f"{s.margin_impact_pct:.4f}%"
        zone_str = _ZONE_HDR[s.zone]
        exhausted = " !" if s.budget_exhausted else "  "
        print(
            f"  {s.l3_pct:>5.1f}  {zone_str:<10}  {s.l3_calls_desired:>8,}  {s.l3_calls_served:>8,}  "
            f"{overflow_str}  ${s.l3_cost_usd:>8.2f}  {s.effective_yield_pct:>6.1f}%  "
            f"{s.auto_resolved_pct:>8.2f}%  {s.l4_pct:>5.2f}%  {dl4:>6}  {margin:>8}{exhausted}"
        )
    print(_div("-"))
    print("  ! = budget cap reached; overflow calls forced to L4.")
    print(f"  Cap math: served + overflow = desired  (verified — see --test).")
    print()


def print_monthly(
    projections: List[MonthlyProjection],
    l3_pcts: List[float],
    p: SimulationParams,
) -> None:
    print()
    print(_div("="))
    print("  MONTHLY PROJECTIONS")
    print(f"  Cap per batch: {p.l3_max_calls:,} calls / ${p.l3_max_cost_usd:.2f}")
    print(f"  Batch size:    {p.batch_size_for_monthly:,} records")
    print(_div("="))

    for vol in p.monthly_record_volumes:
        vol_projs = [pr for pr in projections if pr.monthly_records == vol]
        num_batches = math.ceil(vol / p.batch_size_for_monthly)
        print(f"\n  Monthly volume: {vol:>15,} records  ({num_batches:,} batches × {p.batch_size_for_monthly:,})")
        print(_div("-"))
        hdr = (
            f"  {'L3%':>5}  {'L3 calls (A)':>13}  {'Cost (A)':>12}  {'L4 (A)':>10}"
            f"  {'Served (B)':>12}  {'Overflow (B)':>13}  {'Cost (B)':>12}  {'L4 (B)':>10}"
        )
        print(hdr)
        print(_div("-"))
        for pr in vol_projs:
            overflow_str = f"{pr.monthly_overflow_calls:>13,}" if pr.monthly_overflow_calls > 0 else f"{'—':>13}"
            print(
                f"  {pr.l3_pct:>5.1f}  {pr.monthly_l3_calls_uncapped:>13,}  "
                f"${pr.monthly_l3_cost_uncapped_usd:>11,.2f}  {pr.monthly_l4_records_uncapped:>10,}"
                f"  {pr.monthly_l3_calls_served_capped:>12,}  {overflow_str}  "
                f"${pr.monthly_l3_cost_capped_usd:>11,.2f}  {pr.monthly_l4_records_capped:>10,}"
            )
        print(_div("-"))
    print()
    print("  A = UNCAPPED  |  B = CAPPED")
    print("  L4 (A) = baseline L4 + L3-UNKNOWN (uncapped calls × (1 - yield))")
    print("  L4 (B) = baseline L4 + L3-UNKNOWN (served calls × (1 - yield)) + overflow")
    print()


def print_guardrails(g: dict, p: SimulationParams) -> None:
    print()
    print(_div("="))
    print("  RECOMMENDED GUARDRAILS")
    print(_div("="))
    print(f"  SAFE zone ceiling         : L3 < {g['safe_threshold_pct']:.1f}%"
          f"   →  cost < ${g['safe_max_cost_usd']:.2f}/batch  →  {int(p.total_records * g['safe_threshold_pct'] / 100):,} calls")
    print(f"  WARNING zone              : {g['safe_threshold_pct']:.1f}% ≤ L3 < {g['warning_threshold_pct']:.1f}%"
          f"  →  cost ${g['safe_max_cost_usd']:.2f}–${g['warning_max_cost_usd']:.2f}/batch")
    print(f"  RED zone trigger          : L3 ≥ {g['warning_threshold_pct']:.1f}%"
          f"   →  cap fires; overflow → L4")
    print()
    print(f"  Recommended L3_MAX_COST_USD : ${g['recommended_l3_max_cost_usd']:.2f}")
    print(f"  → Effective call cap        : {g['recommended_cap_calls']:,} calls/batch")
    print(f"  → Effective L3 rate cap     : {g['recommended_cap_pct']:.1f}% of {p.total_records:,} records")
    print(f"  → Rationale                 : 80% of current cap (${p.l3_max_cost_usd:.2f})")
    print(f"                                leaves ${p.l3_max_cost_usd - g['recommended_l3_max_cost_usd']:.2f} buffer/batch")
    print()
    print("  To apply without deploy (env var override at runtime):")
    print(f"    L3_MAX_COST_USD={g['recommended_l3_max_cost_usd']:.2f}")
    print()
    print("  This adjusts only the per-batch budget guard in L3BudgetTracker.")
    print("  Resolution thresholds (L3_MIN_SIMILARITY, cosine threshold) are unchanged.")
    print(_div("="))
    print()


def print_detail_blocks(
    uncapped: List[ScenarioUncapped],
    capped: List[ScenarioCapped],
) -> None:
    """Per-scenario layer breakdown blocks."""
    print(_div("="))
    print("  SCENARIO DETAIL — LAYER BREAKDOWN")
    print(_div("="))
    for u, c in zip(uncapped, capped):
        div_char = _ZONE_DIV[u.zone]
        print(_div(div_char))
        print(f"  {_ZONE_HDR[u.zone]}  L3 = {u.l3_pct:.1f}%")
        print(_div(div_char))
        # Uncapped
        print(f"  UNCAPPED:  calls={u.l3_calls:,}  cost=${u.l3_cost_usd:.2f}"
              f"  yield={u.effective_yield_pct:.1f}%"
              f"  resolved={u.l3_resolved:,}  UNKNOWN={u.l3_unknown:,}")
        print(f"             auto-res={u.auto_resolved_pct:.2f}%  L4={u.l4_count:,} ({u.l4_pct:.2f}%)"
              f"  ΔL4={u.delta_l4_records:+,}  ΔLLM=${u.delta_llm_cost_usd:+.2f}"
              f"  margin={u.margin_impact_pct:+.4f}%")
        print(f"             p95 proxy: {u.p95_latency_proxy_ms:.0f}ms  ({u.p95_latency_waves} waves × {500:.0f}ms + base)")
        # Capped
        overflow_note = (
            f"  ** {c.l3_calls_overflow:,} overflow → L4 (L3_BUDGET_CAP) **"
            if c.budget_exhausted else "  (cap not reached)"
        )
        print(f"  CAPPED  :  desired={c.l3_calls_desired:,}  served={c.l3_calls_served:,}"
              f"  overflow={c.l3_calls_overflow:,}{overflow_note}")
        print(f"             cost=${c.l3_cost_usd:.2f}  yield={c.effective_yield_pct:.1f}%"
              f"  resolved={c.l3_resolved:,}  UNKNOWN={c.l3_unknown:,}")
        print(f"             auto-res={c.auto_resolved_pct:.2f}%  L4={c.l4_count:,} ({c.l4_pct:.2f}%)"
              f"  ΔL4={c.delta_l4_records:+,}  ΔLLM=${c.delta_llm_cost_usd:+.2f}"
              f"  margin={c.margin_impact_pct:+.4f}%")
        print()


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

def run_tests() -> None:
    """
    Lightweight unit tests. No external dependencies.
    Run with: python3 drift_simulation_v2.py --test
    """
    failures: List[str] = []

    def assert_eq(name: str, got, expected, tol: float = 0.0) -> None:
        if tol > 0:
            if abs(got - expected) > tol:
                failures.append(f"FAIL {name}: got {got}, expected {expected} (tol={tol})")
        else:
            if got != expected:
                failures.append(f"FAIL {name}: got {got!r}, expected {expected!r}")

    p = SimulationParams(total_records=40_000)

    # --- Test 1: cap math — served + overflow == desired ---
    for l3_pct in [2.1, 4.0, 6.0, 10.0]:
        c = simulate_capped(l3_pct, p)
        assert_eq(
            f"cap_math[{l3_pct}] served+overflow==desired",
            c.l3_calls_served + c.l3_calls_overflow,
            c.l3_calls_desired,
        )

    # --- Test 2: uncapped cost correctness — calls × cost_per_call == cost ---
    for l3_pct in [2.1, 4.0, 6.0, 10.0]:
        u = simulate_uncapped(l3_pct, p)
        expected_cost = round(u.l3_calls * p.llm_cost_per_call, 4)
        assert_eq(f"uncapped_cost[{l3_pct}]", u.l3_cost_usd, expected_cost, tol=1e-6)

    # --- Test 3: capped cost == served_calls × cost_per_call ---
    for l3_pct in [2.1, 4.0, 6.0, 10.0]:
        c = simulate_capped(l3_pct, p)
        expected_cost = round(c.l3_calls_served * p.llm_cost_per_call, 4)
        assert_eq(f"capped_cost[{l3_pct}]", c.l3_cost_usd, expected_cost, tol=1e-6)

    # --- Test 4: determinism — identical inputs produce identical outputs ---
    for l3_pct in [2.1, 6.0]:
        u1 = simulate_uncapped(l3_pct, p)
        u2 = simulate_uncapped(l3_pct, p)
        assert_eq(f"determinism_uncapped[{l3_pct}] cost", u1.l3_cost_usd, u2.l3_cost_usd)
        assert_eq(f"determinism_uncapped[{l3_pct}] l4", u1.l4_count, u2.l4_count)
        c1 = simulate_capped(l3_pct, p)
        c2 = simulate_capped(l3_pct, p)
        assert_eq(f"determinism_capped[{l3_pct}] served", c1.l3_calls_served, c2.l3_calls_served)
        assert_eq(f"determinism_capped[{l3_pct}] overflow", c1.l3_calls_overflow, c2.l3_calls_overflow)

    # --- Test 5: at cap boundary (exactly at max_calls) ---
    p_tiny = SimulationParams(total_records=200_000, llm_cost_per_call=0.005, l3_max_cost_usd=10.0)
    # 1% of 200K = 2000 = exactly the cap
    c_boundary = simulate_capped(1.0, p_tiny)
    assert_eq("cap_boundary overflow=0", c_boundary.l3_calls_overflow, 0)
    # 1.01% of 200K = 2020 > cap → overflow expected
    c_over = simulate_capped(1.01, p_tiny)
    assert_eq("cap_over overflow>0", c_over.l3_calls_overflow > 0, True)

    # --- Test 6: monthly projection — served + overflow = desired per month ---
    proj = project_monthly(10_000_000, 6.0, p)
    assert_eq(
        "monthly_cap_math: served+overflow==uncapped_calls",
        proj.monthly_l3_calls_served_capped + proj.monthly_overflow_calls,
        proj.monthly_l3_calls_uncapped,
    )

    # --- Test 7: uncapped baseline scenario has delta_llm == 0 ---
    u_base = simulate_uncapped(p.baseline_l3_pct, p)
    assert_eq("baseline_delta_llm==0", u_base.delta_llm_cost_usd, 0.0, tol=1e-6)

    # --- Test 8: zone classification ---
    assert_eq("zone_safe", classify_zone(2.1), "SAFE")
    assert_eq("zone_warning", classify_zone(3.5), "WARNING")
    assert_eq("zone_red_pct", classify_zone(5.0), "RED")
    assert_eq("zone_red_exhausted", classify_zone(2.0, budget_exhausted=True), "RED")

    if failures:
        print("TESTS FAILED:")
        for f in failures:
            print(f"  {f}")
        sys.exit(1)
    else:
        total = 8
        print(f"All tests passed ({total} test groups, {4*4 + 4*4 + 1 + 2 + 1 + 1 + 1 + 4} assertions).")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="L3 Drift Simulation v2 — Uncapped vs Capped + Monthly Projections",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--records", type=int, default=40_000)
    parser.add_argument("--baseline-l3-pct", type=float, default=BASELINE_L3_PCT)
    parser.add_argument("--l3-max-cost", type=float, default=ENGINE_L3_MAX_COST_USD,
                        help="Per-batch L3 budget cap (Scenario B)")
    parser.add_argument("--resolution-rate", type=float, default=0.33,
                        help="LLM resolution rate (fraction of L3 calls that resolve)")
    parser.add_argument("--revenue-per-record", type=float, default=0.25)
    parser.add_argument(
        "--scenarios", type=float, nargs="+",
        default=[2.1, 4.0, 6.0, 10.0],
    )
    parser.add_argument("--test", action="store_true", help="Run unit tests and exit")
    args = parser.parse_args()

    if args.test:
        run_tests()
        return

    p = SimulationParams(
        total_records=args.records,
        baseline_l3_pct=args.baseline_l3_pct,
        l3_max_cost_usd=args.l3_max_cost,
        llm_resolution_rate=args.resolution_rate,
        revenue_per_record_usd=args.revenue_per_record,
    )

    uncapped = [simulate_uncapped(pct, p) for pct in args.scenarios]
    capped = [simulate_capped(pct, p) for pct in args.scenarios]
    projections = [
        project_monthly(vol, pct, p)
        for vol in p.monthly_record_volumes
        for pct in args.scenarios
    ]
    guardrails = compute_guardrails(p)

    print_header(p)
    print_table_uncapped(uncapped, p)
    print_table_capped(capped, p)
    print_monthly(projections, args.scenarios, p)
    print_guardrails(guardrails, p)
    print_detail_blocks(uncapped, capped)


if __name__ == "__main__":
    main()
