"""
================================================================================
INTELLIGENT ANALYST - HASH CHAIN MODULE (Phase 2 + IAVP v1.0)
================================================================================

Implements per-batch cryptographic hash chain for tamper evidence.
Each event hash = SHA256(prev_hash + canonical_event_json)

IAVP v1.0 Compliance:
- STABLE_INPUT_ORDER_V2: Deterministic record ordering before chaining
- JCS canonicalization (RFC 8785)
- Replay verification for determinism proof

Structure:
- batch_root_hash: Last event hash in the chain
- Each event stores: prev_hash, event_hash, hash_algo, chain_scope

Verification:
- Recalculate chain from genesis
- Compare computed root with stored root
- Any mutation breaks the chain

================================================================================
"""

import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple, Optional

from .signing import canonicalize_json, sha256_bytes
from .iavp import (
    jcs_canonicalize, jcs_sha256,
    prepare_records_for_chain, sort_records_stable_order,
    build_decision_ledger, verify_determinism, ReplayVerificationResult,
    IAVP_ORDERING_METHOD, IAVP_HASH_CHAIN_METHOD, IAVP_REPLAY_RUNS
)


# Genesis hash (empty chain start)
GENESIS_HASH = "0" * 64  # 64 zeros

# Layer canonicalization: cache-topology variants → canonical layer for deterministic hashing.
# Without this, the same record resolved via cache vs fresh LLM would produce different hashes.
_LAYER_CANONICAL = {
    "L3_CACHED": "L3_LLM",
    "L3_FIRESTORE_CACHED": "L3_LLM",
    "L3_PERSON_CACHED": "L3_PERSON_LLM",
}


def _canonicalize_layer(layer: str) -> str:
    """Map cache-variant layer names to their canonical form for hashing."""
    return _LAYER_CANONICAL.get(layer, layer)


def normalize_event_for_hashing(event_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract minimal stable fields for hashing.
    These fields represent the DECISION (input → output) and are deterministic.

    IAVP v1.0 REPLAY DETERMINISM: Hash includes ONLY intrinsic decision fields:
    - original: the input entity name
    - resolved: the resolved canonical name (or None)
    - layer: which resolution layer produced the result
    - confidence: resolution confidence score
    - entity_type: detected entity type
    - decision_path: resolution decision path

    EXCLUDES (to ensure replay determinism):
    - source_timestamp: varies by execution time
    - source_system_id: contains batch_trace_id which changes per upload
    - Any other processing metadata
    """
    normalized = {
        "original": event_data.get("original", ""),
        "resolved": event_data.get("resolved"),
        "layer": _canonicalize_layer(event_data.get("layer", "")),
        "confidence": round(event_data.get("confidence", 0.0), 6),  # Normalize float precision
        "entity_type": event_data.get("entity_type", ""),
        "decision_path": event_data.get("decision_path", ""),
    }

    return normalized


def compute_event_hash(prev_hash: str, event_data: Dict[str, Any], use_jcs: bool = True) -> str:
    """
    Compute hash for a single event in the chain.

    event_hash = SHA256(prev_hash + canonical_event_json)

    IAVP v1.0: Uses JCS canonicalization (RFC 8785) by default.

    Args:
        prev_hash: Previous event hash in chain
        event_data: Event/record data
        use_jcs: Use JCS canonicalization (IAVP v1.0 compliant)

    Returns:
        Lowercase hex SHA-256 digest
    """
    normalized = normalize_event_for_hashing(event_data)

    if use_jcs:
        # IAVP v1.0: JCS canonicalization (RFC 8785)
        canonical = jcs_canonicalize(normalized)
    else:
        # Legacy: Sorted keys canonicalization
        canonical = canonicalize_json(normalized)

    combined = f"{prev_hash}:{canonical.decode('utf-8')}".encode('utf-8')
    return hashlib.sha256(combined).hexdigest().lower()


def build_hash_chain_entry(
    row_index: int,
    prev_hash: str,
    event_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Build a hash chain entry for an event.

    Returns entry with:
    - row_index
    - prev_hash
    - event_hash
    - hash_algo
    - chain_scope
    """
    event_hash = compute_event_hash(prev_hash, event_data)

    return {
        "row_index": row_index,
        "prev_hash": prev_hash,
        "event_hash": event_hash,
        "hash_algo": "SHA256",
        "chain_scope": "batch",
        "chained_at": datetime.now(timezone.utc).isoformat(),
    }


def compute_batch_hash_chain(
    batch_trace_id: str,
    events: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], str]:
    """
    Compute hash chain for all events in a batch.

    Returns:
        (chain_entries, batch_root_hash)
        - chain_entries: List of hash chain entries for each event
        - batch_root_hash: Final hash (last event's event_hash)
    """
    if not events:
        return [], GENESIS_HASH

    chain_entries = []
    prev_hash = GENESIS_HASH

    for i, event in enumerate(events):
        # Build entry
        entry = build_hash_chain_entry(i, prev_hash, event)
        chain_entries.append(entry)
        prev_hash = entry["event_hash"]

    # Root hash is the last event's hash
    batch_root_hash = prev_hash

    return chain_entries, batch_root_hash


def verify_hash_chain(
    events: List[Dict[str, Any]],
    chain_entries: List[Dict[str, Any]],
    expected_root_hash: str
) -> Dict[str, Any]:
    """
    Verify hash chain integrity.

    Checks:
    1. Chain length matches events length
    2. Each event_hash is correctly computed
    3. prev_hash links are correct
    4. Root hash matches expected

    Returns verification result with details.
    """
    if len(events) != len(chain_entries):
        return {
            "valid": False,
            "error": "chain_length_mismatch",
            "expected_length": len(events),
            "actual_length": len(chain_entries),
        }

    if not events:
        return {
            "valid": expected_root_hash == GENESIS_HASH,
            "error": None if expected_root_hash == GENESIS_HASH else "empty_chain_root_mismatch",
            "computed_root": GENESIS_HASH,
            "expected_root": expected_root_hash,
        }

    prev_hash = GENESIS_HASH
    broken_at = None

    for i, (event, entry) in enumerate(zip(events, chain_entries)):
        # Check prev_hash link
        if entry.get("prev_hash") != prev_hash:
            broken_at = i
            return {
                "valid": False,
                "error": "prev_hash_link_broken",
                "broken_at_index": i,
                "expected_prev_hash": prev_hash,
                "actual_prev_hash": entry.get("prev_hash"),
            }

        # Recompute event hash
        computed_hash = compute_event_hash(prev_hash, event)
        stored_hash = entry.get("event_hash")

        if computed_hash != stored_hash:
            return {
                "valid": False,
                "error": "event_hash_mismatch",
                "broken_at_index": i,
                "computed_hash": computed_hash,
                "stored_hash": stored_hash,
            }

        prev_hash = computed_hash

    # Check root hash
    computed_root = prev_hash
    if computed_root != expected_root_hash:
        return {
            "valid": False,
            "error": "root_hash_mismatch",
            "computed_root": computed_root,
            "expected_root": expected_root_hash,
        }

    return {
        "valid": True,
        "error": None,
        "computed_root": computed_root,
        "chain_length": len(events),
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }


def verify_hash_chain_iavp(
    events: List[Dict[str, Any]],
    chain_entries: List[Dict[str, Any]],
    expected_root_hash: str,
    batch_trace_id: str
) -> Dict[str, Any]:
    """
    Verify hash chain with IAVP v1.0 compliance.

    During chain computation, events are sorted with STABLE_INPUT_ORDER_V2
    before hashing. The stored chain_entries are in that sorted order.
    This function sorts the raw events (which may be in upload order) to
    match the chain entry order before verification.

    Args:
        events: Raw result records (may be in upload order)
        chain_entries: Stored chain entries (in V2-sorted order)
        expected_root_hash: Stored batch root hash
        batch_trace_id: Batch identifier (for source_system_id generation)

    Returns:
        Verification result dict (same schema as verify_hash_chain)
    """
    if not events:
        return verify_hash_chain(events, chain_entries, expected_root_hash)

    # Sort events using the same STABLE_INPUT_ORDER_V2 logic as chain build.
    # prepare_records_for_chain assigns a single ingestion timestamp to all
    # records, so the V2 sort is deterministic from SHA256(original) + row_index.
    sorted_events = prepare_records_for_chain(list(events), batch_trace_id)

    return verify_hash_chain(sorted_events, chain_entries, expected_root_hash)


def build_chain_metadata(
    batch_trace_id: str,
    chain_entries: List[Dict[str, Any]],
    batch_root_hash: str,
    iavp_compliant: bool = False,
    replay_result: Optional[ReplayVerificationResult] = None
) -> Dict[str, Any]:
    """
    Build metadata for storing with batch.

    IAVP v1.0: Includes method and ordering fields.
    """
    meta = {
        "chain_enabled": True,
        "chain_scope": "batch",
        "chain_algo": "SHA256",
        "chain_length": len(chain_entries),
        "genesis_hash": GENESIS_HASH,
        "batch_root_hash": batch_root_hash,
        "chained_at": datetime.now(timezone.utc).isoformat(),
    }

    if iavp_compliant:
        meta["method"] = IAVP_HASH_CHAIN_METHOD
        meta["ordering"] = IAVP_ORDERING_METHOD

        if replay_result:
            meta["replay_runs"] = replay_result.to_dict()["replay_runs"]
            meta["replay_variance"] = replay_result.to_dict()["replay_variance"]
            meta["replay_method"] = replay_result.to_dict()["replay_method"]
            meta["replay_passed"] = replay_result.passed

    return meta


# =============================================================================
# IAVP v1.0 COMPLIANT CHAIN COMPUTATION
# =============================================================================

def compute_batch_hash_chain_iavp(
    batch_trace_id: str,
    events: List[Dict[str, Any]],
    enable_replay_verification: bool = True
) -> Tuple[List[Dict[str, Any]], str, ReplayVerificationResult]:
    """
    Compute hash chain with IAVP v1.0 compliance.

    STABLE_INPUT_ORDER_V2:
    1. Assigns source_timestamp and source_system_id
    2. Sorts records deterministically (by timestamp, SHA256(original), row_index)
    3. Computes chain with JCS canonicalization
    4. Performs replay verification

    Args:
        batch_trace_id: Batch identifier
        events: Raw resolution results
        enable_replay_verification: Perform replay runs (default: True)

    Returns:
        (chain_entries, batch_root_hash, replay_result)
    """
    if not events:
        return [], GENESIS_HASH, ReplayVerificationResult()

    # Prepare records (assigns timestamps, sorts per STABLE_INPUT_ORDER_V2)
    sorted_events = prepare_records_for_chain(events, batch_trace_id)

    # Build decision ledger ONCE from prepared records (minimal intrinsic fields).
    # Replay uses shallow copies of this ledger instead of deepcopy of full results.
    ledger = build_decision_ledger(sorted_events)

    # Define chain computation function for replay
    def compute_chain_root(records: List[Dict[str, Any]]) -> str:
        _, root = _compute_chain_internal(records)
        return root

    # Perform replay verification (rehash-only from ledger)
    if enable_replay_verification:
        replay_result = verify_determinism(
            events,
            batch_trace_id,
            compute_chain_root,
            runs=IAVP_REPLAY_RUNS,
            ledger=ledger
        )

        if not replay_result.passed:
            # Log variance but don't fail - caller decides
            print(f"[HashChain] REPLAY VARIANCE DETECTED: {replay_result.variance} mismatched runs", flush=True)
    else:
        replay_result = ReplayVerificationResult()
        replay_result.add_run("skipped")

    # Final chain computation
    chain_entries, batch_root_hash = _compute_chain_internal(sorted_events)

    return chain_entries, batch_root_hash, replay_result


def _compute_chain_internal(
    sorted_events: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], str]:
    """
    Internal chain computation on pre-sorted events.

    Uses JCS canonicalization per IAVP v1.0.
    """
    if not sorted_events:
        return [], GENESIS_HASH

    chain_entries = []
    prev_hash = GENESIS_HASH

    for i, event in enumerate(sorted_events):
        # Compute hash using JCS
        event_hash = compute_event_hash(prev_hash, event, use_jcs=True)

        entry = {
            "row_index": i,
            "prev_hash": prev_hash,
            "event_hash": event_hash,
            "hash_algo": "SHA256",
            "chain_scope": "batch",
            "method": IAVP_HASH_CHAIN_METHOD,
            "ordering": IAVP_ORDERING_METHOD,
            "chained_at": datetime.now(timezone.utc).isoformat(),
        }

        # Include IAVP fields if present
        if event.get("source_timestamp"):
            entry["source_timestamp"] = event["source_timestamp"]
        if event.get("source_system_id"):
            entry["source_system_id"] = event["source_system_id"]
        if event.get("_record_hash"):
            entry["record_hash"] = event["_record_hash"]

        chain_entries.append(entry)
        prev_hash = event_hash

    batch_root_hash = prev_hash
    return chain_entries, batch_root_hash


class ReplayVarianceError(Exception):
    """Raised when replay verification detects variance."""
    def __init__(self, variance: int, run_hashes: List[str]):
        self.variance = variance
        self.run_hashes = run_hashes
        super().__init__(
            f"Replay variance detected: {variance} mismatched runs out of {len(run_hashes)}. "
            f"Hashes: {run_hashes}"
        )
