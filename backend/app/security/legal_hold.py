"""
================================================================================
INTELLIGENT ANALYST - LEGAL HOLD + WORM VAULTING MODULE (Phase 5 + Week 2)
================================================================================

Implements legal hold lifecycle and WORM vaulting for regulatory compliance.

Features:
1. Legal Hold Registry (Firestore) - Track hold status per batch
2. WORM Vaulting (GCS Bucket Lock) - Immutable evidence storage
3. Hold/Release API - Audit trail for all hold operations
4. Append-only hold event history (Week 2 governance)
5. Role-based access control for hold operations

Architecture:
- When hold is placed: vault evidence to GCS with bucket-level retention lock
- While on hold: evidence cannot be deleted or modified
- When hold is released: retention policy continues to apply
- All hold events are recorded immutably

Compliance: SEC 17a-4, FINRA, MiFID II, eDiscovery, GDPR

Roles:
- tenant_admin: Can place holds on tenant's batches
- platform_admin: Can place/release holds on any batch

================================================================================
"""

import os
import json
import hashlib
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple, List
from enum import Enum


class HoldEventType(str, Enum):
    """Legal hold event types for audit trail."""
    HOLD_PLACED = "HOLD_PLACED"
    HOLD_RELEASED = "HOLD_RELEASED"
    HOLD_EXTENDED = "HOLD_EXTENDED"


class HoldRole(str, Enum):
    """Roles authorized for hold operations."""
    TENANT_ADMIN = "tenant_admin"
    PLATFORM_ADMIN = "platform_admin"


# Roles that can place holds
HOLD_PLACEMENT_ROLES = [HoldRole.TENANT_ADMIN.value, HoldRole.PLATFORM_ADMIN.value]
# Roles that can release holds (more restrictive)
HOLD_RELEASE_ROLES = [HoldRole.PLATFORM_ADMIN.value]

# GCS client - lazy loaded
_gcs_client = None
_gcs_available = False

try:
    from google.cloud import storage
    _gcs_available = True
except ImportError:
    _gcs_available = False
    print("[LegalHold] google-cloud-storage not available", flush=True)


# Configuration
LEGAL_HOLD_ENABLED = os.getenv("LEGAL_HOLD_ENABLED", "false").lower() == "true"
VAULT_BUCKET = os.getenv("VAULT_BUCKET", "")
VAULT_RETENTION_DAYS = int(os.getenv("VAULT_RETENTION_DAYS", "2555"))  # ~7 years


def _get_gcs_client():
    """Lazy-load GCS client."""
    global _gcs_client
    if _gcs_client is None and _gcs_available:
        _gcs_client = storage.Client()
    return _gcs_client


def _hash_tenant_id(tenant_id: str) -> str:
    """Hash tenant_id for path construction (privacy)."""
    if not tenant_id:
        return "unknown"
    return hashlib.sha256(tenant_id.encode()).hexdigest()[:16]


def build_hold_record(
    batch_id: str,
    tenant_id: str,
    actor_id: str,
    hold_type: str,
    matter_id: str,
    reason: str
) -> Dict[str, Any]:
    """
    Build a legal hold record for storage.

    hold_type: LITIGATION | REGULATORY | AUDIT | INTERNAL
    """
    return {
        "batch_id": batch_id,
        "tenant_id_hash": _hash_tenant_id(tenant_id),
        "hold_type": hold_type,
        "matter_id": matter_id,
        "reason": reason,
        "placed_by": actor_id,
        "placed_at": datetime.now(timezone.utc).isoformat(),
        "status": "ACTIVE",
        "released_at": None,
        "released_by": None,
        "release_reason": None,
    }


def vault_evidence_to_gcs(
    batch_id: str,
    tenant_id: str,
    evidence_package: Dict[str, Any]
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Vault evidence package to GCS with retention lock.

    Evidence is stored in: vaulted/<tenant_hash>/<batch_id>/evidence.json

    Returns:
        (success, vault_path, error)
    """
    if not LEGAL_HOLD_ENABLED:
        return False, None, "legal_hold_disabled"

    if not _gcs_available:
        return False, None, "gcs_not_available"

    if not VAULT_BUCKET:
        return False, None, "vault_bucket_not_configured"

    client = _get_gcs_client()
    if not client:
        return False, None, "gcs_client_init_failed"

    try:
        bucket = client.bucket(VAULT_BUCKET)
        tenant_hash = _hash_tenant_id(tenant_id)
        vault_path = f"vaulted/{tenant_hash}/{batch_id}/evidence.json"

        blob = bucket.blob(vault_path)

        # Add metadata
        evidence_with_meta = {
            "vaulted_at": datetime.now(timezone.utc).isoformat(),
            "batch_id": batch_id,
            "tenant_id_hash": tenant_hash,
            "retention_days": VAULT_RETENTION_DAYS,
            "evidence": evidence_package,
        }

        # Write to vault (bucket-level retention policy applies)
        evidence_json = json.dumps(evidence_with_meta, indent=2, sort_keys=True)
        blob.upload_from_string(
            evidence_json,
            content_type="application/json"
        )

        full_path = f"gs://{VAULT_BUCKET}/{vault_path}"
        print(f"[LegalHold] Vaulted evidence for {batch_id} to {full_path}", flush=True)
        return True, full_path, None

    except Exception as e:
        error_msg = f"vault_write_error: {str(e)}"
        print(f"[LegalHold] Error: {error_msg}", flush=True)
        return False, None, error_msg


def vault_hash_chain_to_gcs(
    batch_id: str,
    tenant_id: str,
    chain_entries: List[Dict[str, Any]],
    batch_root_hash: str
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Vault hash chain to GCS with retention lock.

    Chain is stored in: vaulted/<tenant_hash>/<batch_id>/chain.json

    Returns:
        (success, vault_path, error)
    """
    if not LEGAL_HOLD_ENABLED:
        return False, None, "legal_hold_disabled"

    if not _gcs_available:
        return False, None, "gcs_not_available"

    if not VAULT_BUCKET:
        return False, None, "vault_bucket_not_configured"

    client = _get_gcs_client()
    if not client:
        return False, None, "gcs_client_init_failed"

    try:
        bucket = client.bucket(VAULT_BUCKET)
        tenant_hash = _hash_tenant_id(tenant_id)
        vault_path = f"vaulted/{tenant_hash}/{batch_id}/chain.json"

        blob = bucket.blob(vault_path)

        # Build chain package
        chain_package = {
            "vaulted_at": datetime.now(timezone.utc).isoformat(),
            "batch_id": batch_id,
            "tenant_id_hash": tenant_hash,
            "retention_days": VAULT_RETENTION_DAYS,
            "batch_root_hash": batch_root_hash,
            "chain_length": len(chain_entries),
            "chain_entries": chain_entries,
        }

        # Write to vault
        chain_json = json.dumps(chain_package, indent=2, sort_keys=True)
        blob.upload_from_string(
            chain_json,
            content_type="application/json"
        )

        full_path = f"gs://{VAULT_BUCKET}/{vault_path}"
        print(f"[LegalHold] Vaulted chain for {batch_id} to {full_path}", flush=True)
        return True, full_path, None

    except Exception as e:
        error_msg = f"chain_vault_error: {str(e)}"
        print(f"[LegalHold] Error: {error_msg}", flush=True)
        return False, None, error_msg


def verify_vaulted_evidence(
    batch_id: str,
    tenant_id: str
) -> Dict[str, Any]:
    """
    Verify that evidence exists in vault and is intact.
    """
    if not _gcs_available:
        return {"verified": False, "error": "gcs_not_available"}

    if not VAULT_BUCKET:
        return {"verified": False, "error": "vault_bucket_not_configured"}

    client = _get_gcs_client()
    if not client:
        return {"verified": False, "error": "gcs_client_init_failed"}

    try:
        bucket = client.bucket(VAULT_BUCKET)
        tenant_hash = _hash_tenant_id(tenant_id)

        # Check evidence
        evidence_path = f"vaulted/{tenant_hash}/{batch_id}/evidence.json"
        evidence_blob = bucket.blob(evidence_path)
        evidence_exists = evidence_blob.exists()

        # Check chain
        chain_path = f"vaulted/{tenant_hash}/{batch_id}/chain.json"
        chain_blob = bucket.blob(chain_path)
        chain_exists = chain_blob.exists()

        if not evidence_exists and not chain_exists:
            return {"verified": False, "error": "vault_not_found"}

        result = {
            "verified": True,
            "error": None,
            "evidence_path": f"gs://{VAULT_BUCKET}/{evidence_path}" if evidence_exists else None,
            "chain_path": f"gs://{VAULT_BUCKET}/{chain_path}" if chain_exists else None,
            "evidence_exists": evidence_exists,
            "chain_exists": chain_exists,
        }

        # Get metadata if exists
        if evidence_exists:
            evidence_blob.reload()
            result["evidence_size_bytes"] = evidence_blob.size
            result["evidence_created"] = evidence_blob.time_created.isoformat() if evidence_blob.time_created else None
            result["evidence_retention_expiration"] = evidence_blob.retention_expiration_time.isoformat() if evidence_blob.retention_expiration_time else None

        return result

    except Exception as e:
        return {"verified": False, "error": f"verify_error: {str(e)}"}


def build_release_record(
    hold_record: Dict[str, Any],
    actor_id: str,
    reason: str
) -> Dict[str, Any]:
    """
    Build updated hold record for release.
    """
    updated = hold_record.copy()
    updated["status"] = "RELEASED"
    updated["released_at"] = datetime.now(timezone.utc).isoformat()
    updated["released_by"] = actor_id
    updated["release_reason"] = reason
    return updated


def get_legal_hold_status() -> Dict[str, Any]:
    """Get legal hold status for /health endpoint."""
    return {
        "enabled": LEGAL_HOLD_ENABLED,
        "gcs_available": _gcs_available,
        "vault_bucket": VAULT_BUCKET if LEGAL_HOLD_ENABLED else None,
        "retention_days": VAULT_RETENTION_DAYS if LEGAL_HOLD_ENABLED else None,
    }


# =============================================================================
# HOLD GOVERNANCE FUNCTIONS (Week 2)
# =============================================================================

def generate_hold_id() -> str:
    """Generate unique hold ID for tracking."""
    return f"HOLD-{uuid.uuid4().hex[:12].upper()}"


def generate_event_id() -> str:
    """Generate unique event ID for audit trail."""
    return f"EVT-{uuid.uuid4().hex[:12].upper()}"


def check_hold_placement_role(role: str) -> bool:
    """Check if role is authorized to place holds."""
    return role in HOLD_PLACEMENT_ROLES


def check_hold_release_role(role: str) -> bool:
    """Check if role is authorized to release holds."""
    return role in HOLD_RELEASE_ROLES


def build_hold_event(
    event_type: HoldEventType,
    batch_id: str,
    tenant_id: str,
    actor_id: str,
    actor_role: str,
    reason: str,
    hold_id: str,
    previous_state: Optional[str] = None,
    new_state: Optional[str] = None,
    vault_refs: Optional[List[Dict[str, Any]]] = None,
    expires_at: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build an immutable hold event record.

    These events are append-only and form the legal audit trail.
    """
    event_id = generate_event_id()
    timestamp = datetime.now(timezone.utc).isoformat()

    return {
        "event_id": event_id,
        "event_type": event_type.value,
        "hold_id": hold_id,
        "batch_id": batch_id,
        "tenant_id_hash": _hash_tenant_id(tenant_id),
        "actor": actor_id,
        "actor_role": actor_role,
        "timestamp": timestamp,
        "reason": reason,
        "previous_state": previous_state,
        "new_state": new_state,
        "expires_at": expires_at,
        "vault_refs_summary": {
            "count": len(vault_refs) if vault_refs else 0,
            "paths": [v.get("path") for v in vault_refs] if vault_refs else [],
        },
    }


def build_enhanced_hold_record(
    batch_id: str,
    tenant_id: str,
    actor_id: str,
    actor_role: str,
    reason: str,
    expires_at: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build enhanced legal hold record with governance fields.
    """
    hold_id = generate_hold_id()
    timestamp = datetime.now(timezone.utc).isoformat()

    return {
        "hold_id": hold_id,
        "batch_id": batch_id,
        "tenant_id": tenant_id,
        "tenant_id_hash": _hash_tenant_id(tenant_id),
        "status": "ACTIVE",
        "reason": reason,
        "expires_at": expires_at,
        "requested_by": actor_id,
        "requested_by_role": actor_role,
        "requested_at_utc": timestamp,
        "released_by": None,
        "released_by_role": None,
        "released_at_utc": None,
        "release_reason": None,
        "vault_objects": [],
        "vault_objects_written_count": 0,
    }


def compute_content_hash(content: str) -> str:
    """Compute SHA256 hash of content for vault integrity."""
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def vault_object_with_hash(
    bucket,
    vault_path: str,
    content: str,
    batch_id: str,
    tenant_id: str,
    object_type: str
) -> Dict[str, Any]:
    """
    Vault a single object with hash tracking.

    Returns vault reference with path, hash, size.
    """
    blob = bucket.blob(vault_path)
    content_hash = compute_content_hash(content)

    blob.upload_from_string(content, content_type="application/json")

    # Reload to get generation/version
    blob.reload()

    return {
        "path": f"gs://{VAULT_BUCKET}/{vault_path}",
        "object_type": object_type,
        "sha256": content_hash,
        "size_bytes": len(content.encode('utf-8')),
        "generation": blob.generation,
        "vaulted_at": datetime.now(timezone.utc).isoformat(),
    }


def vault_all_for_hold(
    batch_id: str,
    tenant_id: str,
    evidence_blobs: List[Dict],
    chain_entries: List[Dict],
    root_hash: str,
    certificate_data: Optional[Dict] = None,
    verify_output: Optional[Dict] = None,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Vault all artifacts for a legal hold.

    Returns:
        (list of vault references, error message or None)
    """
    if not LEGAL_HOLD_ENABLED:
        return [], "legal_hold_disabled"

    if not _gcs_available:
        return [], "gcs_not_available"

    if not VAULT_BUCKET:
        return [], "vault_bucket_not_configured"

    client = _get_gcs_client()
    if not client:
        return [], "gcs_client_init_failed"

    bucket = client.bucket(VAULT_BUCKET)
    tenant_hash = _hash_tenant_id(tenant_id)
    base_path = f"vault/{tenant_hash}/{batch_id}"

    vault_refs = []

    try:
        # 1. Vault evidence blobs
        if evidence_blobs:
            evidence_package = {
                "vaulted_at": datetime.now(timezone.utc).isoformat(),
                "batch_id": batch_id,
                "evidence_count": len(evidence_blobs),
                "blobs": evidence_blobs,
            }
            content = json.dumps(evidence_package, indent=2, sort_keys=True)
            ref = vault_object_with_hash(
                bucket, f"{base_path}/evidence.json", content,
                batch_id, tenant_id, "evidence"
            )
            vault_refs.append(ref)

        # 2. Vault hash chain
        if chain_entries:
            chain_package = {
                "vaulted_at": datetime.now(timezone.utc).isoformat(),
                "batch_id": batch_id,
                "batch_root_hash": root_hash,
                "chain_length": len(chain_entries),
                "chain_entries": chain_entries,
            }
            content = json.dumps(chain_package, indent=2, sort_keys=True)
            ref = vault_object_with_hash(
                bucket, f"{base_path}/chain.json", content,
                batch_id, tenant_id, "chain"
            )
            vault_refs.append(ref)

        # 3. Vault certificate (if provided)
        if certificate_data:
            content = json.dumps(certificate_data, indent=2, sort_keys=True)
            ref = vault_object_with_hash(
                bucket, f"{base_path}/certificate.json", content,
                batch_id, tenant_id, "certificate"
            )
            vault_refs.append(ref)

        # 4. Vault verify output (if provided)
        if verify_output:
            content = json.dumps(verify_output, indent=2, sort_keys=True)
            ref = vault_object_with_hash(
                bucket, f"{base_path}/verify.json", content,
                batch_id, tenant_id, "verify"
            )
            vault_refs.append(ref)

        print(f"[LegalHold] Vaulted {len(vault_refs)} objects for {batch_id}", flush=True)
        return vault_refs, None

    except Exception as e:
        error_msg = f"vault_error: {str(e)}"
        print(f"[LegalHold] Error: {error_msg}", flush=True)
        return vault_refs, error_msg
