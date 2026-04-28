"""
Transparency Log Spine — Core orchestrator.

Coordinates:
- Leaf creation and hashing
- Merkle tree append
- Signed root publication
- Entry persistence
- Async insertion via background tasks
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import traceback
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.transparency.leaf import build_leaf_payload, hash_leaf
from app.transparency.merkle import MerkleTree, verify_inclusion_proof


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TRANSPARENCY_ENABLED = os.getenv("TRANSPARENCY_LOG_ENABLED", "false").lower() == "true"
TRANSPARENCY_BUCKET = os.getenv("TRANSPARENCY_BUCKET", "")
TRANSPARENCY_KMS_KEY_ID = os.getenv("TRANSPARENCY_KMS_KEY_ID", "")
ROOT_PUBLISH_ENTRY_THRESHOLD = int(os.getenv("TRANSPARENCY_ROOT_PUBLISH_ENTRIES", "1024"))
ROOT_PUBLISH_INTERVAL_SECONDS = int(os.getenv("TRANSPARENCY_ROOT_PUBLISH_INTERVAL", "300"))
MAX_RETRY_ATTEMPTS = 3
INCLUSION_SLA_SECONDS = 60

# ---------------------------------------------------------------------------
# Global state (in-memory for TEST runtime)
# ---------------------------------------------------------------------------

_tree = MerkleTree()
_entry_index: Dict[str, int] = {}  # entry_id -> leaf_index
_entry_payloads: Dict[str, Dict] = {}  # entry_id -> leaf_payload
_last_published_size = 0
_last_published_time = 0.0
_spine_lock = threading.Lock()

# Published roots history
_published_roots: List[Dict[str, Any]] = []


# ---------------------------------------------------------------------------
# Structured logging
# ---------------------------------------------------------------------------

def _slog(event: str, **kwargs: Any) -> None:
    """Emit structured transparency log."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stage": "transparency_spine",
        "event": event,
    }
    entry.update(kwargs)
    print(f"[transparency] {json.dumps(entry, default=str)}", flush=True)


# ---------------------------------------------------------------------------
# KMS signing for transparency roots (separate trust domain)
# ---------------------------------------------------------------------------

def _sign_root_kms(root_hash_hex: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Sign a tree root with the dedicated transparency KMS key.

    Uses a SEPARATE key from receipt signing (trust domain isolation).

    Returns (signature_b64, error_message).
    """
    if not TRANSPARENCY_KMS_KEY_ID:
        return None, "TRANSPARENCY_KMS_KEY_ID not configured"

    try:
        from google.cloud import kms
        client = kms.KeyManagementServiceClient()
        key_version = f"{TRANSPARENCY_KMS_KEY_ID}/cryptoKeyVersions/1"
        digest_bytes = bytes.fromhex(root_hash_hex)

        response = client.asymmetric_sign(
            request={
                "name": key_version,
                "digest": {"sha256": digest_bytes},
            }
        )

        import base64
        sig_b64 = base64.b64encode(response.signature).decode("utf-8")
        return sig_b64, None
    except Exception as e:
        return None, str(e)


# ---------------------------------------------------------------------------
# Entry insertion
# ---------------------------------------------------------------------------

def insert_entry(
    entry_type: str,
    entry_id: str,
    root_hash: str,
    timestamp: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Insert a new transparency log entry.

    This is the synchronous core. For async insertion, use enqueue_entry().

    Returns:
        {
            "success": bool,
            "leaf_index": int or None,
            "leaf_hash": str or None,
            "tree_size": int,
            "error": str or None,
        }
    """
    global _last_published_size, _last_published_time

    try:
        leaf_payload = build_leaf_payload(
            entry_type=entry_type,
            entry_id=entry_id,
            root_hash=root_hash,
            timestamp=timestamp,
        )
        leaf_hash = hash_leaf(leaf_payload)

        with _spine_lock:
            # Idempotent: skip if already inserted
            if entry_id in _entry_index:
                existing_idx = _entry_index[entry_id]
                _slog("leaf_skipped_duplicate", entry_id=entry_id, leaf_index=existing_idx)
                return {
                    "success": True,
                    "leaf_index": existing_idx,
                    "leaf_hash": leaf_hash,
                    "tree_size": _tree.tree_size,
                    "error": None,
                }

            leaf_index = _tree.append(leaf_hash)
            _entry_index[entry_id] = leaf_index
            _entry_payloads[entry_id] = leaf_payload

        _slog("leaf_appended",
              entry_type=entry_type, entry_id=entry_id,
              leaf_index=leaf_index, leaf_hash=leaf_hash,
              tree_size=_tree.tree_size)

        # Check if root publication is needed
        _maybe_publish_root()

        return {
            "success": True,
            "leaf_index": leaf_index,
            "leaf_hash": leaf_hash,
            "tree_size": _tree.tree_size,
            "error": None,
        }
    except Exception as e:
        _slog("insertion_failure",
              entry_type=entry_type, entry_id=entry_id,
              error=str(e), severity="critical")
        return {
            "success": False,
            "leaf_index": None,
            "leaf_hash": None,
            "tree_size": _tree.tree_size,
            "error": str(e),
        }


def enqueue_entry(
    entry_type: str,
    entry_id: str,
    root_hash: str,
    timestamp: Optional[str] = None,
) -> None:
    """
    Enqueue a transparency log entry for async insertion.

    Fires a background thread. Does not block the caller.
    On failure, retries up to MAX_RETRY_ATTEMPTS with backoff.
    """
    _slog("leaf_enqueued", entry_type=entry_type, entry_id=entry_id)

    def _worker() -> None:
        for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
            result = insert_entry(entry_type, entry_id, root_hash, timestamp)
            if result["success"]:
                return
            _slog("insertion_retry",
                  entry_type=entry_type, entry_id=entry_id,
                  attempt=attempt, max_attempts=MAX_RETRY_ATTEMPTS,
                  error=result["error"], severity="critical")
            time.sleep(min(2 ** attempt, 10))

        _slog("insertion_exhausted",
              entry_type=entry_type, entry_id=entry_id,
              severity="critical")

    t = threading.Thread(target=_worker, daemon=True)
    t.start()


# ---------------------------------------------------------------------------
# Root publication
# ---------------------------------------------------------------------------

def _maybe_publish_root() -> None:
    """Publish root if threshold or interval exceeded."""
    global _last_published_size, _last_published_time

    current_size = _tree.tree_size
    now = time.time()

    entries_since = current_size - _last_published_size
    time_since = now - _last_published_time if _last_published_time > 0 else float("inf")

    if entries_since >= ROOT_PUBLISH_ENTRY_THRESHOLD or time_since >= ROOT_PUBLISH_INTERVAL_SECONDS:
        publish_root()


def publish_root() -> Dict[str, Any]:
    """
    Publish the current tree root.

    Signs the root with the transparency KMS key and records it.

    Returns published root metadata.
    """
    global _last_published_size, _last_published_time

    root_hash = _tree.root()
    tree_size = _tree.tree_size
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    # Sign root
    signature, sign_error = _sign_root_kms(root_hash)
    if sign_error:
        _slog("signing_failure", root_hash=root_hash, tree_size=tree_size,
              error=sign_error, severity="critical")

    root_record = {
        "tree_size": tree_size,
        "root_hash": root_hash,
        "signature": signature,
        "algorithm": "EC_SIGN_P256_SHA256",
        "key_id": TRANSPARENCY_KMS_KEY_ID or None,
        "timestamp": timestamp,
        "sign_error": sign_error,
    }

    with _spine_lock:
        _published_roots.append(root_record)
        _last_published_size = tree_size
        _last_published_time = time.time()

    _slog("root_published", tree_size=tree_size, root_hash=root_hash,
          signed=signature is not None)

    # Persist to GCS if configured
    _persist_root_to_gcs(root_record)

    return root_record


def _persist_root_to_gcs(root_record: Dict[str, Any]) -> None:
    """Persist signed root to GCS transparency bucket."""
    if not TRANSPARENCY_BUCKET:
        return
    try:
        from google.cloud import storage as _gcs
        client = _gcs.Client()
        bucket = client.bucket(TRANSPARENCY_BUCKET)

        ts = root_record["timestamp"].replace(":", "-").replace(".", "-")
        path = f"transparency/roots/{ts}_size{root_record['tree_size']}.json"
        blob = bucket.blob(path)
        blob.upload_from_string(
            json.dumps(root_record, indent=2),
            content_type="application/json",
        )
    except Exception as e:
        _slog("root_gcs_persist_failure", error=str(e), severity="warning")


# ---------------------------------------------------------------------------
# Proof retrieval
# ---------------------------------------------------------------------------

def get_inclusion_proof(entry_id: str) -> Dict[str, Any]:
    """
    Get an inclusion proof for an entry.

    Returns:
        {
            "found": bool,
            "entry_id": str,
            "leaf_index": int or None,
            "leaf_hash": str or None,
            "tree_size": int,
            "inclusion_proof": [...] or [],
            "root_hash": str,
            "root_timestamp": str or None,
        }
    """
    with _spine_lock:
        if entry_id not in _entry_index:
            return {
                "found": False,
                "entry_id": entry_id,
                "leaf_index": None,
                "leaf_hash": None,
                "tree_size": _tree.tree_size,
                "inclusion_proof": [],
                "root_hash": _tree.root(),
                "root_timestamp": None,
            }

        leaf_index = _entry_index[entry_id]
        leaf_payload = _entry_payloads.get(entry_id, {})
        leaf_hash = hash_leaf(leaf_payload) if leaf_payload else None

    proof = _tree.inclusion_proof(leaf_index)
    root_hash = _tree.root()

    # Find latest published root timestamp
    root_timestamp = None
    if _published_roots:
        root_timestamp = _published_roots[-1].get("timestamp")

    _slog("proof_requested", entry_id=entry_id, leaf_index=leaf_index,
          tree_size=_tree.tree_size, proof_depth=len(proof))

    return {
        "found": True,
        "entry_id": entry_id,
        "leaf_index": leaf_index,
        "leaf_hash": leaf_hash,
        "tree_size": _tree.tree_size,
        "inclusion_proof": proof,
        "root_hash": root_hash,
        "root_timestamp": root_timestamp,
    }


def get_latest_root() -> Dict[str, Any]:
    """Get the latest tree root and metadata."""
    root_hash = _tree.root()
    tree_size = _tree.tree_size

    latest_published = None
    if _published_roots:
        latest_published = _published_roots[-1]

    return {
        "tree_size": tree_size,
        "root_hash": root_hash,
        "latest_published": latest_published,
    }


# ---------------------------------------------------------------------------
# State management (for testing)
# ---------------------------------------------------------------------------

def reset_spine() -> None:
    """Reset all spine state. TEST ONLY."""
    global _tree, _entry_index, _entry_payloads
    global _last_published_size, _last_published_time, _published_roots
    with _spine_lock:
        _tree = MerkleTree()
        _entry_index = {}
        _entry_payloads = {}
        _last_published_size = 0
        _last_published_time = 0.0
        _published_roots = []
