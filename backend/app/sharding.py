"""
sharding.py — Shard planner and metadata persistence for Day 2 fan-out.

Splits large batches into fixed-size shards (default 1,000 records).
Each shard is processed independently by a Cloud Tasks worker.
Shard metadata is stored in Firestore: batches/{batch_id}/shards/{shard_id}

Day 2 scope: fan-out + shard metadata. Deterministic merge is Day 3.
"""

import os
import traceback
from datetime import datetime
from typing import List, Dict, Optional, Tuple

# TEST-only shard threshold override for Phase 9.5 validation.
# If ENVIRONMENT=test and IA_TEST_SHARD_SIZE_OVERRIDE is set, use it.
# PROD/STAGING behavior is unchanged.
_base_shard_size = int(os.getenv("SHARD_SIZE", "1000"))
_test_override = os.getenv("IA_TEST_SHARD_SIZE_OVERRIDE")
if os.getenv("ENVIRONMENT") == "test" and _test_override is not None:
    SHARD_SIZE = int(_test_override)
    print(f"[sharding] TEST override active: SHARD_SIZE={SHARD_SIZE} (base={_base_shard_size})", flush=True)
else:
    SHARD_SIZE = _base_shard_size


# ──────────────────────────────────────────────────────────────────────────────
# Pure function: compute shard ranges
# ──────────────────────────────────────────────────────────────────────────────

def compute_shard_ranges(total_records: int, shard_size: int = SHARD_SIZE) -> List[Dict]:
    """
    Given total_records, return a list of shard descriptors.

    Each shard: {shard_id, start_index, end_index, record_count}
    - shard_id is 0-indexed, monotonically increasing
    - start_index is inclusive, end_index is exclusive
    - Last shard may have fewer than shard_size records

    Returns empty list for total_records <= 0.
    """
    if total_records <= 0:
        return []

    if shard_size <= 0:
        raise ValueError(f"shard_size must be positive, got {shard_size}")

    shards = []
    shard_id = 0
    for start in range(0, total_records, shard_size):
        end = min(start + shard_size, total_records)
        shards.append({
            "shard_id": shard_id,
            "start_index": start,
            "end_index": end,
            "record_count": end - start,
        })
        shard_id += 1

    return shards


# ──────────────────────────────────────────────────────────────────────────────
# Firestore persistence: shard metadata
# ──────────────────────────────────────────────────────────────────────────────

def _shard_doc_id(shard_id: int) -> str:
    """Deterministic document ID for a shard."""
    return f"shard_{shard_id:04d}"


def create_shard_docs(batch_trace_id: str, shards: List[Dict], db) -> bool:
    """
    Create shard metadata documents in Firestore.
    Path: batches/{batch_trace_id}/shards/shard_XXXX

    Args:
        batch_trace_id: Parent batch ID
        shards: Output of compute_shard_ranges()
        db: Firestore client

    Returns True if all docs created successfully.
    """
    if not db:
        print("[sharding] No Firestore client, skipping shard doc creation", flush=True)
        return False

    try:
        shards_ref = db.collection("batches").document(batch_trace_id).collection("shards")

        for shard in shards:
            doc_id = _shard_doc_id(shard["shard_id"])
            doc = {
                "batch_id": batch_trace_id,
                "shard_id": shard["shard_id"],
                "start_index": shard["start_index"],
                "end_index": shard["end_index"],
                "record_count": shard["record_count"],
                "status": "queued",
                "attempts": 0,
                "last_error": None,
                "started_at": None,
                "finished_at": None,
                "counts": None,
                "l3_spent_usd": 0.0,
                "created_at": datetime.utcnow().isoformat(),
            }
            shards_ref.document(doc_id).set(doc)

        print(f"[sharding] Created {len(shards)} shard docs for {batch_trace_id}", flush=True)
        return True

    except Exception as e:
        print(f"[sharding] Failed to create shard docs: {e}", flush=True)
        traceback.print_exc()
        return False


def update_shard_status(
    batch_trace_id: str,
    shard_id: int,
    status: str,
    db,
    counts: Optional[Dict] = None,
    error: Optional[str] = None,
    l3_spent_usd: float = 0.0,
    results_chunks: Optional[List[str]] = None,
    duration_ms: Optional[float] = None,
) -> bool:
    """
    Update a single shard's status and optional counts/error.

    Args:
        status: "running" | "completed" | "failed"
        counts: Layer counts dict (l0, l1, l2, l3, l4, etc.)
        error: Sanitized error message (no PII)
        l3_spent_usd: Actual L3 spend for this shard
        results_chunks: List of chunk doc IDs written by this shard (shard receipt)
        duration_ms: Shard processing wall time in milliseconds
    """
    if not db:
        return False

    try:
        doc_ref = (db.collection("batches").document(batch_trace_id)
                   .collection("shards").document(_shard_doc_id(shard_id)))

        update = {"status": status}

        if status == "running":
            update["started_at"] = datetime.utcnow().isoformat()
            # Increment attempts atomically
            from google.cloud.firestore_v1 import Increment
            update["attempts"] = Increment(1)
        elif status in ("completed", "failed"):
            update["finished_at"] = datetime.utcnow().isoformat()

        if counts is not None:
            update["counts"] = counts
        if error is not None:
            update["last_error"] = error[:500]  # Truncate for safety
        if l3_spent_usd > 0:
            update["l3_spent_usd"] = l3_spent_usd
        if results_chunks is not None:
            update["results_chunks"] = results_chunks
        if duration_ms is not None:
            update["duration_ms"] = round(duration_ms, 1)

        doc_ref.update(update)
        return True

    except Exception as e:
        print(f"[sharding] Failed to update shard {shard_id} status: {e}", flush=True)
        return False


def get_all_shard_statuses(batch_trace_id: str, db) -> List[Dict]:
    """
    Read all shard docs for a batch, ordered by shard_id.
    Returns list of shard dicts.
    """
    if not db:
        return []

    try:
        shards_ref = (db.collection("batches").document(batch_trace_id)
                      .collection("shards"))
        docs = shards_ref.order_by("shard_id").stream()
        return [doc.to_dict() for doc in docs]
    except Exception as e:
        print(f"[sharding] Failed to read shard statuses: {e}", flush=True)
        return []


def build_shard_receipts(shard_statuses: List[Dict]) -> List[Dict]:
    """
    Extract shard receipt data from shard docs. Pure function.

    Each receipt contains the fields needed for veracity receipt aggregation:
    shard_id, results_chunks, counts, l3_spent_usd, duration_ms, finished_at.

    Returns list of receipts ordered by shard_id.
    """
    receipts = []
    for shard in sorted(shard_statuses, key=lambda s: s.get("shard_id", 0)):
        receipts.append({
            "shard_id": shard.get("shard_id"),
            "start_index": shard.get("start_index"),
            "end_index": shard.get("end_index"),
            "record_count": shard.get("record_count", 0),
            "results_chunks": shard.get("results_chunks", []),
            "counts": shard.get("counts") or {},
            "l3_spent_usd": shard.get("l3_spent_usd", 0.0),
            "duration_ms": shard.get("duration_ms"),
            "finished_at": shard.get("finished_at"),
        })
    return receipts


def try_complete_batch(batch_trace_id: str, tenant_id: str, db):
    """
    Atomically check if all shards are done. If yes, set status to "finalizing"
    and return finalize data. If any failed, mark batch as failed.

    Uses Firestore transaction to prevent race conditions when multiple
    shards finish concurrently.

    Returns:
        dict with action="finalize" + shard_receipts + aggregated data → ready for finalize
        True  → batch was marked as failed
        False → still running (not all shards done)
    """
    if not db:
        return False

    try:
        @_firestore_transactional
        def _check_and_complete(transaction):
            # Read all shard docs in transaction
            shards_ref = (db.collection("batches").document(batch_trace_id)
                          .collection("shards"))
            shard_docs = list(shards_ref.stream(transaction=transaction))

            if not shard_docs:
                return False

            shard_statuses = [doc.to_dict() for doc in shard_docs]
            total_shards = len(shard_statuses)

            # Check if all done
            completed = [s for s in shard_statuses if s.get("status") == "completed"]
            failed = [s for s in shard_statuses if s.get("status") == "failed"]
            still_running = total_shards - len(completed) - len(failed)

            if still_running > 0:
                return False  # Not all done yet

            # All shards finished — aggregate
            batch_ref = db.collection("batches").document(batch_trace_id)

            if failed:
                # At least one shard failed
                error_msgs = [s.get("last_error", "unknown") for s in failed]
                transaction.update(batch_ref, {
                    "status": "failed",
                    "error_reason": f"SHARD_FAILURE: {len(failed)}/{total_shards} shards failed. "
                                    f"First error: {error_msgs[0][:200]}",
                    "finished_at": datetime.utcnow().isoformat(),
                })
                print(f"[sharding] Batch {batch_trace_id}: {len(failed)}/{total_shards} shards FAILED", flush=True)
                return True

            # All completed — aggregate counts + build shard receipts
            agg_counts = {}
            total_records = 0
            total_l3_spent = 0.0

            for shard in shard_statuses:
                counts = shard.get("counts") or {}
                total_records += shard.get("record_count", 0)
                total_l3_spent += shard.get("l3_spent_usd", 0.0)

                for key, val in counts.items():
                    if isinstance(val, (int, float)):
                        agg_counts[key] = agg_counts.get(key, 0) + val

            shard_receipts = build_shard_receipts(shard_statuses)

            # Set status to "finalizing" — NOT "completed"
            # The /internal/finalize-batch endpoint will run forensic pipeline
            # and set status to "completed" only after full proof is computed.
            transaction.update(batch_ref, {
                "status": "finalizing",
                "finished_at": datetime.utcnow().isoformat(),
                "counts": agg_counts,
                "total_l3_spent_usd": total_l3_spent,
                "shards_completed": total_shards,
                "error_reason": None,
            })

            # Phase 2A: Create dedicated finalize state doc (contention isolation)
            finalize_state_ref = db.collection("batch_finalize_state").document(batch_trace_id)
            transaction.set(finalize_state_ref, {
                "finalize_state": "none",
                "finalize_lock": None,
                "batch_trace_id": batch_trace_id,
                "updated_at": datetime.utcnow().isoformat(),
            })

            print(f"[sharding] Batch {batch_trace_id}: all {total_shards} shards done → FINALIZING, "
                  f"total_records={total_records}, l3_spent=${total_l3_spent:.4f}", flush=True)

            return {
                "action": "finalize",
                "shard_receipts": shard_receipts,
                "agg_counts": agg_counts,
                "total_l3_spent": total_l3_spent,
                "total_records": total_records,
                "shards_completed": total_shards,
            }

        _max = int(os.getenv("FINALIZE_TXN_MAX_ATTEMPTS", "5"))
        return _check_and_complete(db.transaction(max_attempts=_max))

    except Exception as e:
        print(f"[sharding] try_complete_batch error: {e}", flush=True)
        traceback.print_exc()
        return False


def _firestore_transactional(func):
    """Decorator for Firestore transactional functions."""
    from google.cloud import firestore
    return firestore.transactional(func)


def fetch_shard_rows(
    batch_trace_id: str,
    start_index: int,
    end_index: int,
    db,
) -> List[str]:
    """
    Load a shard's row slice from the input_rows subcollection.

    The input_rows are stored in 500-row chunks by store_batch_rows_to_firestore().
    We need to read the appropriate chunks and extract the correct slice.

    Args:
        start_index: Inclusive start index (relative to full batch)
        end_index: Exclusive end index (relative to full batch)

    Returns list of row strings for this shard.
    """
    if not db:
        return []

    try:
        INPUT_CHUNK_SIZE = 500  # Matches store_batch_rows_to_firestore()
        rows_ref = (db.collection("batches").document(batch_trace_id)
                    .collection("input_rows"))

        # Determine which chunks we need to read
        first_chunk_start = (start_index // INPUT_CHUNK_SIZE) * INPUT_CHUNK_SIZE
        last_chunk_start = ((end_index - 1) // INPUT_CHUNK_SIZE) * INPUT_CHUNK_SIZE

        all_rows = []
        for chunk_start in range(first_chunk_start, last_chunk_start + INPUT_CHUNK_SIZE, INPUT_CHUNK_SIZE):
            doc_id = f"chunk_{chunk_start:06d}"
            doc = rows_ref.document(doc_id).get()
            if doc.exists:
                chunk_data = doc.to_dict()
                chunk_rows = chunk_data.get("rows", [])
                chunk_start_idx = chunk_data.get("start_index", chunk_start)

                # Extract only the rows within our shard's range
                for i, row in enumerate(chunk_rows):
                    global_idx = chunk_start_idx + i
                    if start_index <= global_idx < end_index:
                        all_rows.append(row)

        print(f"[sharding] Loaded {len(all_rows)} rows for shard "
              f"[{start_index}:{end_index}] of {batch_trace_id}", flush=True)
        return all_rows

    except Exception as e:
        print(f"[sharding] Failed to fetch shard rows: {e}", flush=True)
        traceback.print_exc()
        return []
