"""
Transparency Log Spine — Leaf canonicalization and hashing.

Deterministic leaf schema v1.0:
{
  "version": "1.0",
  "entry_type": "receipt|assertion|tombstone",
  "entry_id": "...",
  "root_hash": "...",
  "timestamp": "...Z",
  "nonce": "..."
}

Leaf hash: SHA256(JCS(leaf_payload))
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.security.iavp import jcs_canonicalize


LEAF_VERSION = "1.0"
VALID_ENTRY_TYPES = {"receipt", "assertion", "tombstone"}


def build_leaf_payload(
    entry_type: str,
    entry_id: str,
    root_hash: str,
    timestamp: Optional[str] = None,
    nonce: Optional[str] = None,
) -> Dict[str, str]:
    """
    Build a canonical leaf payload for the transparency log.

    Args:
        entry_type: One of "receipt", "assertion", "tombstone".
        entry_id: The receipt_id or assertion_id.
        root_hash: The root_hash from the manifest or assertion chain.
        timestamp: ISO 8601 UTC timestamp. Auto-generated if not provided.
        nonce: Random nonce for uniqueness. Auto-generated if not provided.

    Returns:
        Canonical leaf payload dict.

    Raises:
        ValueError: If entry_type is invalid or required fields are empty.
    """
    if entry_type not in VALID_ENTRY_TYPES:
        raise ValueError(f"Invalid entry_type: {entry_type}. Must be one of {VALID_ENTRY_TYPES}")
    if not entry_id or not entry_id.strip():
        raise ValueError("entry_id must not be empty")
    if not root_hash or not root_hash.strip():
        raise ValueError("root_hash must not be empty")

    if timestamp is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    if nonce is None:
        nonce = secrets.token_hex(16)

    return {
        "version": LEAF_VERSION,
        "entry_type": entry_type,
        "entry_id": entry_id,
        "root_hash": root_hash,
        "timestamp": timestamp,
        "nonce": nonce,
    }


def hash_leaf(leaf_payload: Dict[str, str]) -> str:
    """
    Compute the leaf hash: SHA256(JCS(leaf_payload)).

    Returns lowercase hex digest (64 chars).
    """
    canonical = jcs_canonicalize(leaf_payload)
    return hashlib.sha256(canonical).hexdigest()
