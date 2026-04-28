"""
system_metrics.py — Day 6: Bounded-buffer metrics persistence for cross-batch observability.

Stores finalize latency, shard duration, L3 cache stats, LLM failover frequency,
and ledger integrity snapshots in Firestore. All writes are non-fatal: failures
return False and never break finalize.

Firestore paths:
  system_metrics/finalize   — bounded buffer of finalize latency samples (ms)
  system_metrics/shards     — bounded buffer of shard duration samples (ms)
  system_metrics/l3_cache   — cumulative L3 cache hit/miss/unknown counters
  system_metrics/failover   — cumulative failover + total L3 counters
  system_metrics/ledger     — latest tenant ledger snapshot

Receives `db` (Firestore client) as parameter — no imports from server.
"""

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Maximum samples retained in bounded buffer
_BUFFER_MAX = 100


def compute_p95(samples: List[float]) -> float:
    """Compute p95 from a list of numeric samples. Empty → 0.0."""
    if not samples:
        return 0.0
    sorted_s = sorted(samples)
    idx = math.ceil(0.95 * len(sorted_s)) - 1
    idx = max(0, min(idx, len(sorted_s) - 1))
    return float(sorted_s[idx])


def record_finalize_latency(db, duration_ms: float) -> bool:
    """Append finalize latency sample to bounded buffer in system_metrics/finalize."""
    if not db:
        return False
    try:
        ref = db.collection("system_metrics").document("finalize")
        doc = ref.get()
        if doc.exists:
            data = doc.to_dict()
            samples = data.get("samples", [])
            total_count = data.get("sample_count", len(samples))
        else:
            samples = []
            total_count = 0

        samples.append(duration_ms)
        if len(samples) > _BUFFER_MAX:
            samples = samples[-_BUFFER_MAX:]
        total_count += 1

        ref.set({
            "samples": samples,
            "sample_count": total_count,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        })
        return True
    except Exception:
        return False


def record_shard_latency(db, duration_ms: float) -> bool:
    """Append shard latency sample to bounded buffer in system_metrics/shards."""
    if not db:
        return False
    try:
        ref = db.collection("system_metrics").document("shards")
        doc = ref.get()
        if doc.exists:
            data = doc.to_dict()
            samples = data.get("samples", [])
            total_count = data.get("sample_count", len(samples))
        else:
            samples = []
            total_count = 0

        samples.append(duration_ms)
        if len(samples) > _BUFFER_MAX:
            samples = samples[-_BUFFER_MAX:]
        total_count += 1

        ref.set({
            "samples": samples,
            "sample_count": total_count,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        })
        return True
    except Exception:
        return False


def record_l3_cache_stats(db, l3_total_calls: int, l3_cache_hits: int, l3_unknown_cached: int) -> bool:
    """Increment cumulative L3 cache counters in system_metrics/l3_cache."""
    if not db:
        return False
    try:
        ref = db.collection("system_metrics").document("l3_cache")
        doc = ref.get()
        if doc.exists:
            data = doc.to_dict()
            prev_total = data.get("l3_total_calls", 0)
            prev_hits = data.get("l3_cache_hits", 0)
            prev_unknown = data.get("l3_unknown_cached", 0)
        else:
            prev_total = 0
            prev_hits = 0
            prev_unknown = 0

        ref.set({
            "l3_total_calls": prev_total + l3_total_calls,
            "l3_cache_hits": prev_hits + l3_cache_hits,
            "l3_unknown_cached": prev_unknown + l3_unknown_cached,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        })
        return True
    except Exception:
        return False


def record_failover_stats(db, failover_count: int, total_l3_calls: int) -> bool:
    """Increment cumulative failover counters in system_metrics/failover."""
    if not db:
        return False
    try:
        ref = db.collection("system_metrics").document("failover")
        doc = ref.get()
        if doc.exists:
            data = doc.to_dict()
            prev_failover = data.get("failover_count", 0)
            prev_total = data.get("total_l3_calls", 0)
            outcomes = data.get("outcomes", [])
        else:
            prev_failover = 0
            prev_total = 0
            outcomes = []

        # Track per-batch failover outcomes in bounded list
        outcomes.append(failover_count)
        if len(outcomes) > _BUFFER_MAX:
            outcomes = outcomes[-_BUFFER_MAX:]

        ref.set({
            "failover_count": prev_failover + failover_count,
            "total_l3_calls": prev_total + total_l3_calls,
            "outcomes": outcomes,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        })
        return True
    except Exception:
        return False


def record_ledger_snapshot(
    db,
    tenant_id: str,
    credits_reserved_usd: float,
    credits_spent_usd: float,
    credits_released_usd: float,
    integrity_ok: bool,
) -> bool:
    """Overwrite latest ledger snapshot in system_metrics/ledger."""
    if not db:
        return False
    try:
        ref = db.collection("system_metrics").document("ledger")
        ref.set({
            "tenant_id": tenant_id,
            "credits_reserved_usd": credits_reserved_usd,
            "credits_spent_usd": credits_spent_usd,
            "credits_released_usd": credits_released_usd,
            "integrity_ok": integrity_ok,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        })
        return True
    except Exception:
        return False


def get_system_vitals(db) -> Dict[str, Any]:
    """
    Read all 5 metric documents and compute aggregate vitals.

    Returns dict with:
      finalize_p95_ms, shard_p95_ms, l3_cache_hit_rate, l3_unknown_cache_rate,
      failover_rate_percent, ledger_integrity, finalize_sample_count,
      shard_sample_count, collected_at
    """
    result = {
        "finalize_p95_ms": 0.0,
        "shard_p95_ms": 0.0,
        "l3_cache_hit_rate": 0.0,
        "l3_unknown_cache_rate": 0.0,
        "failover_rate_percent": 0.0,
        "ledger_integrity": "PASS",
        "finalize_sample_count": 0,
        "shard_sample_count": 0,
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }

    if not db:
        return result

    try:
        # Finalize latency
        fin_doc = db.collection("system_metrics").document("finalize").get()
        if fin_doc.exists:
            fin_data = fin_doc.to_dict()
            samples = fin_data.get("samples", [])
            result["finalize_p95_ms"] = compute_p95(samples)
            result["finalize_sample_count"] = fin_data.get("sample_count", len(samples))
    except Exception:
        pass

    try:
        # Shard latency
        shard_doc = db.collection("system_metrics").document("shards").get()
        if shard_doc.exists:
            shard_data = shard_doc.to_dict()
            samples = shard_data.get("samples", [])
            result["shard_p95_ms"] = compute_p95(samples)
            result["shard_sample_count"] = shard_data.get("sample_count", len(samples))
    except Exception:
        pass

    try:
        # L3 cache
        cache_doc = db.collection("system_metrics").document("l3_cache").get()
        if cache_doc.exists:
            cache_data = cache_doc.to_dict()
            total = cache_data.get("l3_total_calls", 0)
            hits = cache_data.get("l3_cache_hits", 0)
            unknown = cache_data.get("l3_unknown_cached", 0)
            if total > 0:
                result["l3_cache_hit_rate"] = round(hits / total * 100, 1)
                result["l3_unknown_cache_rate"] = round(unknown / total * 100, 1)
    except Exception:
        pass

    try:
        # Failover
        fo_doc = db.collection("system_metrics").document("failover").get()
        if fo_doc.exists:
            fo_data = fo_doc.to_dict()
            fo_count = fo_data.get("failover_count", 0)
            fo_total = fo_data.get("total_l3_calls", 0)
            if fo_total > 0:
                result["failover_rate_percent"] = round(fo_count / fo_total * 100, 1)
    except Exception:
        pass

    try:
        # Ledger
        ledger_doc = db.collection("system_metrics").document("ledger").get()
        if ledger_doc.exists:
            ledger_data = ledger_doc.to_dict()
            reserved = ledger_data.get("credits_reserved_usd", 0.0)
            if reserved < 0:
                result["ledger_integrity"] = "FAIL"
    except Exception:
        pass

    return result
