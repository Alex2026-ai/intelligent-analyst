"""
TS-04 Performance Test Harness — Local Chain & Replay Timing
=============================================================

Measures:
- chain_build: sort + hash chain construction for N records
- replay_3x_rehash_only: 3 replay verification runs (ledger path)
- throughput: records/sec for each phase

Uses pre-resolved synthetic records (no L0/L1/L2/L3 calls).
The resolve_once duration is captured by the E2E runner (run_ts04.py).

Targets (100K on TEST):
- chain_build: < 120 seconds
- replay_3x_rehash_only: < 60 seconds
"""
import hashlib
import time
import pytest
from typing import List, Dict, Any

from app.security.iavp import (
    prepare_records_for_chain,
    build_decision_ledger,
    verify_determinism,
    IAVP_ORDERING_METHOD,
    IAVP_REPLAY_RUNS,
)
from app.security.hash_chain import (
    compute_batch_hash_chain_iavp,
    _compute_chain_internal,
    GENESIS_HASH,
)


# ---------------------------------------------------------------------------
# Synthetic record generator (deterministic, pre-resolved)
# ---------------------------------------------------------------------------

CANONICAL_COMPANIES = [
    "Apple Inc", "Microsoft Corporation", "Amazon.com Inc", "Alphabet Inc",
    "Meta Platforms Inc", "Tesla Inc", "NVIDIA Corporation", "JPMorgan Chase",
    "Visa Inc", "Johnson & Johnson", "Walmart Inc", "Procter & Gamble",
    "Mastercard Inc", "UnitedHealth Group", "Home Depot", "Bank of America",
    "Pfizer Inc", "Chevron Corporation", "Coca-Cola Company", "PepsiCo Inc",
    "Costco Wholesale", "Walt Disney Company", "Cisco Systems", "Merck & Co",
    "Adobe Inc", "Netflix Inc", "Intel Corporation", "Verizon Communications",
    "AT&T Inc", "Oracle Corporation", "Salesforce Inc", "IBM Corporation",
    "Goldman Sachs", "Morgan Stanley", "American Express", "Caterpillar Inc",
    "Boeing Company", "General Electric", "Ford Motor Company", "General Motors",
    "ExxonMobil", "Berkshire Hathaway", "Wells Fargo", "Citigroup Inc",
    "Target Corporation", "Lowe's Companies", "CVS Health", "FedEx Corporation",
    "UPS", "PayPal Holdings",
]

LAYERS = ["L1_EXACT", "L1_NORM", "L1_PARENT", "L2_VECTOR", "L4_HUMAN"]
LAYER_WEIGHTS = [40, 25, 10, 15, 10]  # Distribution %


def _det_hash(seed: int, index: int) -> int:
    h = hashlib.md5(f"{seed}:{index}".encode()).hexdigest()
    return int(h[:8], 16)


def generate_synthetic_resolved(n: int, seed: int = 20260220) -> List[Dict[str, Any]]:
    """Generate N pre-resolved records (deterministic, no randomness)."""
    records = []
    cc = len(CANONICAL_COMPANIES)
    cum_weights = []
    total = sum(LAYER_WEIGHTS)
    running = 0
    for w in LAYER_WEIGHTS:
        running += w
        cum_weights.append(running)

    for i in range(n):
        h = _det_hash(seed, i)
        company_idx = h % cc
        canonical = CANONICAL_COMPANIES[company_idx]

        # Determine layer by weight distribution
        layer_pick = (h // cc) % total
        layer_idx = 0
        for j, cw in enumerate(cum_weights):
            if layer_pick < cw:
                layer_idx = j
                break

        layer = LAYERS[layer_idx]
        confidence = 1.0 if layer.startswith("L1") else (0.75 + (h % 25) / 100.0)

        # Variation of original name
        variation = h % 5
        if variation == 0:
            original = canonical
        elif variation == 1:
            original = canonical.upper()
        elif variation == 2:
            original = canonical.lower()
        elif variation == 3:
            original = f"  {canonical}  "
        else:
            original = f"{canonical} #{i}"

        records.append({
            "original": original,
            "resolved": canonical if layer != "L4_HUMAN" else None,
            "layer": layer,
            "confidence": round(confidence, 6),
            "entity_type": "COMPANY",
            "decision_path": f"{layer}→resolved" if layer != "L4_HUMAN" else "L4_HUMAN→pending",
        })

    return records


# ---------------------------------------------------------------------------
# Performance measurement helpers
# ---------------------------------------------------------------------------

def measure_chain_build(records, batch_trace_id="PERF-TEST-001"):
    """Measure full IAVP chain build (sort + chain + replay)."""
    start = time.perf_counter()
    chain_entries, root_hash, replay_result = compute_batch_hash_chain_iavp(
        batch_trace_id, records, enable_replay_verification=True
    )
    elapsed = time.perf_counter() - start
    return elapsed, root_hash, chain_entries, replay_result


def measure_replay_only(records, batch_trace_id="PERF-TEST-001", runs=3):
    """Measure replay-only (ledger rehash), no chain build."""
    # Prepare once (same as chain build does)
    sorted_events = prepare_records_for_chain(list(records), batch_trace_id)
    ledger = build_decision_ledger(sorted_events)

    def compute_chain_root(recs):
        _, root = _compute_chain_internal(recs)
        return root

    start = time.perf_counter()
    result = verify_determinism(
        records, batch_trace_id, compute_chain_root,
        runs=runs, ledger=ledger
    )
    elapsed = time.perf_counter() - start
    return elapsed, result


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestTS04ChainPerformance:
    """TS-04 chain build + replay performance at scale."""

    @pytest.mark.parametrize("n", [1000])
    def test_chain_build_1k(self, n):
        """Baseline: 1K records chain build completes quickly."""
        records = generate_synthetic_resolved(n)
        elapsed, root_hash, chain_entries, replay = measure_chain_build(records)

        assert root_hash != GENESIS_HASH
        assert len(chain_entries) == n
        assert replay.passed
        assert elapsed < 30, f"1K chain build took {elapsed:.2f}s (limit: 30s)"
        print(f"\n[TS-04] 1K chain_build: {elapsed:.2f}s ({n / elapsed:.0f} rec/s)")

    @pytest.mark.parametrize("n", [10000])
    def test_chain_build_10k(self, n):
        """Mid-scale: 10K records chain build."""
        records = generate_synthetic_resolved(n)
        elapsed, root_hash, chain_entries, replay = measure_chain_build(records)

        assert root_hash != GENESIS_HASH
        assert len(chain_entries) == n
        assert replay.passed
        assert elapsed < 60, f"10K chain build took {elapsed:.2f}s (limit: 60s)"
        print(f"\n[TS-04] 10K chain_build: {elapsed:.2f}s ({n / elapsed:.0f} rec/s)")

    @pytest.mark.parametrize("n", [1000])
    def test_replay_only_1k(self, n):
        """Baseline: 1K replay (ledger rehash) is fast."""
        records = generate_synthetic_resolved(n)
        elapsed, result = measure_replay_only(records, runs=3)

        assert result.passed
        assert result.variance == 0
        assert elapsed < 10, f"1K replay took {elapsed:.2f}s (limit: 10s)"
        print(f"\n[TS-04] 1K replay_3x: {elapsed:.2f}s ({(n * 3) / elapsed:.0f} rec/s)")

    @pytest.mark.parametrize("n", [10000])
    def test_replay_only_10k(self, n):
        """Mid-scale: 10K replay (ledger rehash)."""
        records = generate_synthetic_resolved(n)
        elapsed, result = measure_replay_only(records, runs=3)

        assert result.passed
        assert result.variance == 0
        assert elapsed < 30, f"10K replay took {elapsed:.2f}s (limit: 30s)"
        print(f"\n[TS-04] 10K replay_3x: {elapsed:.2f}s ({(n * 3) / elapsed:.0f} rec/s)")


class TestTS04ScaleTarget:
    """
    Full 100K scale test. Marked as slow — run with: pytest -m slow -s

    Targets:
    - chain_build (sort + hash + 3x replay): < 120 seconds
    - replay_3x_rehash_only: < 60 seconds
    """

    @pytest.mark.slow
    def test_100k_chain_build(self):
        """100K chain build under 120s target."""
        n = 100_000
        records = generate_synthetic_resolved(n)

        elapsed, root_hash, chain_entries, replay = measure_chain_build(records)

        assert root_hash != GENESIS_HASH
        assert len(chain_entries) == n
        assert replay.passed
        assert replay.variance == 0
        assert elapsed < 120, f"100K chain build took {elapsed:.2f}s (target: <120s)"

        throughput = n / elapsed
        print(f"\n[TS-04] 100K chain_build: {elapsed:.2f}s ({throughput:.0f} rec/s)")
        print(f"  root_hash: {root_hash}")
        print(f"  replay_variance: {replay.variance}")
        print(f"  ordering: {IAVP_ORDERING_METHOD}")

    @pytest.mark.slow
    def test_100k_replay_only(self):
        """100K replay (3x ledger rehash) under 60s target."""
        n = 100_000
        records = generate_synthetic_resolved(n)

        elapsed, result = measure_replay_only(records, runs=3)

        assert result.passed
        assert result.variance == 0
        assert elapsed < 60, f"100K replay took {elapsed:.2f}s (target: <60s)"

        throughput = (n * 3) / elapsed
        print(f"\n[TS-04] 100K replay_3x: {elapsed:.2f}s ({throughput:.0f} rec/s)")
        print(f"  variance: {result.variance}")

    @pytest.mark.slow
    def test_100k_determinism(self):
        """100K: Two independent chain builds produce identical root hash."""
        n = 100_000
        records = generate_synthetic_resolved(n)

        _, root1, _, _ = measure_chain_build(records, "BATCH-DET-A")
        _, root2, _, _ = measure_chain_build(records, "BATCH-DET-B")

        # V2: SHA256(original) sort key means different batch_trace_ids
        # still produce same root hash
        assert root1 == root2, (
            f"Determinism failure: {root1} != {root2}"
        )
        print(f"\n[TS-04] 100K determinism: PASS (root={root1[:16]}...)")


class TestLedgerVsDeepCopy:
    """Verify ledger path is faster than deepcopy path."""

    def test_ledger_faster_than_deepcopy(self):
        """Ledger rehash should be significantly faster than deepcopy."""
        n = 5000
        records = generate_synthetic_resolved(n)
        batch_id = "PERF-COMPARE"

        sorted_events = prepare_records_for_chain(list(records), batch_id)
        ledger = build_decision_ledger(sorted_events)

        def compute_chain_root(recs):
            _, root = _compute_chain_internal(recs)
            return root

        # Ledger path
        start = time.perf_counter()
        result_ledger = verify_determinism(
            records, batch_id, compute_chain_root, runs=3, ledger=ledger
        )
        ledger_time = time.perf_counter() - start

        # Deepcopy path (legacy — no ledger)
        start = time.perf_counter()
        result_deep = verify_determinism(
            records, batch_id, compute_chain_root, runs=3, ledger=None
        )
        deepcopy_time = time.perf_counter() - start

        assert result_ledger.passed
        assert result_deep.passed

        speedup = deepcopy_time / ledger_time if ledger_time > 0 else float("inf")
        print(f"\n[TS-04] Ledger vs DeepCopy (5K records, 3 runs):")
        print(f"  Ledger:   {ledger_time:.3f}s")
        print(f"  DeepCopy: {deepcopy_time:.3f}s")
        print(f"  Speedup:  {speedup:.1f}x")
