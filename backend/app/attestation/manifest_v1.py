"""
Attestation Manifest v1 builder.

Implements the ia-attestation/v1 manifest schema as defined in
docs/protocol/ia_attestation_manifest_v1.md (FROZEN v1).

This module builds the manifest object only. It does NOT:
- Sign the manifest (signing is done by the caller via signing.py)
- Write to Firestore (persistence is done by the finalization path)
- Call GCS (anchor binding is assembled from existing anchor data)
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.security.iavp import jcs_sha256

PROTOCOL_VERSION = "ia-attestation/v1"
SIGNATURE_ALGORITHM = "EC_SIGN_P256_SHA256"

# 17 required fields (source_blob_hash is optional, serialized as null when absent)
_REQUIRED_FIELDS = frozenset({
    "anchor_ref",
    "artifact_hashes",
    "artifact_mode",
    "batch_id",
    "config_hash",
    "dataset_hash",
    "engine_version",
    "environment",
    "key_id",
    "metrics",
    "protocol_version",
    "receipt_id",
    "registry_hash",
    "root_hash",
    "signature_algorithm",
    "tenant_scope",
    "timestamp",
})


def build_attestation_manifest_v1(
    *,
    batch_id: str,
    root_hash: str,
    artifact_mode: str,
    engine_version: str,
    environment: str,
    config_hash: str,
    dataset_hash: str,
    registry_hash: str,
    key_id: str,
    metrics: Dict[str, Any],
    tenant_scope: str,
    anchor_ref: Dict[str, Any],
    artifact_hashes: List[Dict[str, Any]],
    source_blob_hash: Optional[str] = None,
    receipt_id: Optional[str] = None,
    timestamp: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build the canonical attestation manifest v1 object.

    All parameters are keyword-only to prevent field misordering.
    Returns a dict with keys in JCS lexicographic order.

    Args:
        batch_id: Batch trace ID (e.g. "BATCH-D8917A6A").
        root_hash: 64-char hex SHA-256 batch root hash.
        artifact_mode: "PRODUCTION_REAL" or "DEMO_SIMULATED".
        engine_version: Semantic version (e.g. "8.2.2").
        environment: "prod" or "test".
        config_hash: 64-char hex SHA-256 of JCS config snapshot.
        dataset_hash: 64-char hex SHA-256 of JCS input array.
        registry_hash: 64-char hex SHA-256 of canonical company registry.
        key_id: Full KMS key resource path.
        metrics: Resolution layer distribution dict (see spec §1.4).
        tenant_scope: 16-char hex HMAC-based pseudonymous scope token.
        anchor_ref: Anchor binding object (see spec §5).
        artifact_hashes: Per-artifact integrity records (see spec §6).
        source_blob_hash: Optional SHA-256 hex of raw uploaded file. None for JSON batches.
        receipt_id: UUID v4. Auto-generated if not provided.
        timestamp: RFC 3339 UTC. Auto-generated if not provided.

    Returns:
        Manifest dict with keys in canonical (sorted) order.

    Raises:
        ValueError: If required inputs are missing or invalid.
    """
    _validate_inputs(
        batch_id=batch_id,
        root_hash=root_hash,
        artifact_mode=artifact_mode,
        environment=environment,
        config_hash=config_hash,
        dataset_hash=dataset_hash,
        registry_hash=registry_hash,
        key_id=key_id,
        tenant_scope=tenant_scope,
        engine_version=engine_version,
    )

    if receipt_id is None:
        receipt_id = str(uuid.uuid4())

    if timestamp is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    _validate_metrics(metrics)
    _validate_anchor_ref(anchor_ref)
    _validate_artifact_hashes(artifact_hashes)

    manifest = {
        "anchor_ref": anchor_ref,
        "artifact_hashes": artifact_hashes,
        "artifact_mode": artifact_mode,
        "batch_id": batch_id,
        "config_hash": config_hash,
        "dataset_hash": dataset_hash,
        "engine_version": engine_version,
        "environment": environment,
        "key_id": key_id,
        "metrics": metrics,
        "protocol_version": PROTOCOL_VERSION,
        "receipt_id": receipt_id,
        "registry_hash": registry_hash,
        "root_hash": root_hash,
        "signature_algorithm": SIGNATURE_ALGORITHM,
        "source_blob_hash": source_blob_hash,
        "tenant_scope": tenant_scope,
        "timestamp": timestamp,
    }

    assert list(manifest.keys()) == sorted(manifest.keys()), \
        "Manifest keys must be in lexicographic order"

    return manifest


def manifest_to_public_projection(manifest: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a public-safe projection of the manifest for /verify responses.

    Redacts: anchor_ref.bucket, anchor_ref.object_path, key_id.
    Per spec §4.3.
    """
    public = dict(manifest)

    if "anchor_ref" in public and isinstance(public["anchor_ref"], dict):
        public["anchor_ref"] = {
            k: v for k, v in public["anchor_ref"].items()
            if k not in ("bucket", "object_path")
        }

    public.pop("key_id", None)

    return public


def _validate_inputs(
    *,
    batch_id: str,
    root_hash: str,
    artifact_mode: str,
    environment: str,
    config_hash: str,
    dataset_hash: str,
    registry_hash: str,
    key_id: str,
    tenant_scope: str,
    engine_version: str,
) -> None:
    """Validate required manifest inputs. Fail closed on bad data."""
    if not batch_id or not isinstance(batch_id, str):
        raise ValueError("batch_id is required and must be a non-empty string")

    if not root_hash or len(root_hash) != 64:
        raise ValueError("root_hash must be a 64-char hex string")

    if artifact_mode not in ("PRODUCTION_REAL", "DEMO_SIMULATED"):
        raise ValueError(f"artifact_mode must be PRODUCTION_REAL or DEMO_SIMULATED, got: {artifact_mode}")

    if environment not in ("prod", "test"):
        raise ValueError(f"environment must be prod or test, got: {environment}")

    if not config_hash or len(config_hash) != 64:
        raise ValueError("config_hash must be a 64-char hex string")

    if not dataset_hash or len(dataset_hash) != 64:
        raise ValueError("dataset_hash must be a 64-char hex string")

    if not registry_hash or len(registry_hash) != 64:
        raise ValueError("registry_hash must be a 64-char hex string")

    if not key_id or not isinstance(key_id, str):
        raise ValueError("key_id is required and must be a non-empty string")

    if not tenant_scope or len(tenant_scope) != 16:
        raise ValueError("tenant_scope must be a 16-char hex string")

    if not engine_version or not isinstance(engine_version, str):
        raise ValueError("engine_version is required and must be a non-empty string")


def _validate_metrics(metrics: Dict[str, Any]) -> None:
    """Validate metrics object per spec §1.4."""
    if not isinstance(metrics, dict):
        raise ValueError("metrics must be a dict")

    required_keys = {"l1_pct", "l2_pct", "l3_pct", "l4_pct", "record_count",
                     "replay_method", "replay_runs", "replay_variance"}
    missing = required_keys - set(metrics.keys())
    if missing:
        raise ValueError(f"metrics missing required keys: {missing}")


def _validate_anchor_ref(anchor_ref: Dict[str, Any]) -> None:
    """Validate anchor_ref object per spec §5.1."""
    if not isinstance(anchor_ref, dict):
        raise ValueError("anchor_ref must be a dict")

    required_keys = {"anchor_hash", "anchor_timestamp", "bucket", "object_path"}
    missing = required_keys - set(anchor_ref.keys())
    if missing:
        raise ValueError(f"anchor_ref missing required keys: {missing}")


def _validate_artifact_hashes(artifact_hashes: List[Dict[str, Any]]) -> None:
    """Validate artifact_hashes array per spec §6.2."""
    if not isinstance(artifact_hashes, list):
        raise ValueError("artifact_hashes must be a list")

    for i, entry in enumerate(artifact_hashes):
        if not isinstance(entry, dict):
            raise ValueError(f"artifact_hashes[{i}] must be a dict")
        required_keys = {"artifact_type", "hash", "size_bytes"}
        missing = required_keys - set(entry.keys())
        if missing:
            raise ValueError(f"artifact_hashes[{i}] missing required keys: {missing}")
