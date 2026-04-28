"""
Artifact hash populator for ia-attestation/v1.

Computes SHA-256 hashes and sizes for GCS evidence artifacts
(anchor record, evidence vault, hash chain vault) and returns
entries conforming to the manifest artifact_hashes schema.

This module does NOT modify the manifest — that is the caller's job.
"""

import hashlib
import time
from typing import Any, Dict, List, Optional, Tuple

# GCS client (lazy-loaded)
_gcs_client = None
_gcs_available = False

try:
    from google.cloud import storage
    _gcs_available = True
except ImportError:
    storage = None
    _gcs_available = False


def _get_gcs_client():
    """Lazy-load GCS client."""
    global _gcs_client
    if _gcs_client is None and _gcs_available:
        _gcs_client = storage.Client()
    return _gcs_client


# Artifact types that can appear in a finalized batch
ARTIFACT_TYPE_ANCHOR = "anchor_record"
ARTIFACT_TYPE_EVIDENCE = "evidence_vault"
ARTIFACT_TYPE_HASH_CHAIN = "hash_chain_vault"


def compute_artifact_hashes(
    artifact_list: List[Dict[str, str]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Compute SHA-256 hashes and sizes for a list of GCS artifacts.

    Args:
        artifact_list: List of dicts with:
            - artifact_type: str (e.g. "anchor_record")
            - bucket: str (GCS bucket name)
            - object_path: str (GCS object path within bucket)

    Returns:
        (hashes, errors) where:
        - hashes: list of artifact_hash entries for the manifest
        - errors: list of dicts describing any failures
    """
    client = _get_gcs_client()
    if not client:
        return [], [{"reason": "ARTIFACT_METADATA_MISSING", "detail": "GCS client not available"}]

    hashes = []
    errors = []

    for artifact in artifact_list:
        artifact_type = artifact.get("artifact_type", "unknown")
        bucket_name = artifact.get("bucket", "")
        object_path = artifact.get("object_path", "")

        if not bucket_name or not object_path:
            errors.append({
                "artifact_type": artifact_type,
                "reason": "ARTIFACT_METADATA_MISSING",
                "detail": "bucket or object_path is empty",
            })
            continue

        try:
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(object_path)

            # Stream download
            blob_bytes = blob.download_as_bytes()

            sha256_hash = hashlib.sha256(blob_bytes).hexdigest().lower()
            size_bytes = len(blob_bytes)

            hashes.append({
                "artifact_type": artifact_type,
                "hash_alg": "SHA-256",
                "hash": sha256_hash,
                "size_bytes": size_bytes,
            })

        except Exception as e:
            err_str = str(e)
            # Detect "not found" vs other errors
            is_not_found = "404" in err_str or "Not Found" in err_str or "NotFound" in err_str
            errors.append({
                "artifact_type": artifact_type,
                "reason": "ARTIFACT_METADATA_MISSING" if is_not_found else "ARTIFACT_READ_ERROR",
                "detail": err_str[:200],
                "bucket": bucket_name,
                "object_path": object_path,
            })

    return hashes, errors


def build_artifact_list_for_batch(
    anchor_bucket: str,
    anchor_object_path: str,
    vault_bucket: str,
    tenant_hash: str,
    batch_id: str,
) -> List[Dict[str, str]]:
    """
    Build the list of GCS artifacts to hash for a finalized batch.

    Returns a list of artifact descriptors. Only includes artifacts
    whose bucket is configured (non-empty).
    """
    artifacts = []

    # 1. Anchor record
    if anchor_bucket and anchor_object_path:
        artifacts.append({
            "artifact_type": ARTIFACT_TYPE_ANCHOR,
            "bucket": anchor_bucket,
            "object_path": anchor_object_path,
        })

    # 2. Evidence vault
    if vault_bucket and tenant_hash and batch_id:
        artifacts.append({
            "artifact_type": ARTIFACT_TYPE_EVIDENCE,
            "bucket": vault_bucket,
            "object_path": f"vaulted/{tenant_hash}/{batch_id}/evidence.json",
        })

    # 3. Hash chain vault
    if vault_bucket and tenant_hash and batch_id:
        artifacts.append({
            "artifact_type": ARTIFACT_TYPE_HASH_CHAIN,
            "bucket": vault_bucket,
            "object_path": f"vaulted/{tenant_hash}/{batch_id}/chain.json",
        })

    return artifacts
