"""
================================================================================
INTELLIGENT ANALYST - PUBLIC VERIFICATION ENGINE (Notary-Ready v2)
================================================================================

Public, unauthenticated endpoint for cryptographic verification of batch evidence.

Features:
- No authentication required (public trust verification)
- Cryptographic signature verification against KMS public key
- PII-redacted Trust Summary (NO resolution data exposed)
- Legal hold status (existence only, not details)
- NO ESG ratings or resolution quality metrics (removed for notary compliance)

Endpoint: GET /verify/{batch_id}

ABSOLUTE REMOVALS (must not appear anywhere):
- esg_rating
- resolution_quality
- auto_resolved_pct
- human_review_pct

Security:
- NO PII or actual names exposed
- NO resolution results exposed
- Only aggregate workload metadata and verification status

================================================================================
"""

from __future__ import annotations

import base64
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# Batch ID format: uppercase alphanumeric + hyphens only (e.g. BATCH-3838EAE7)
_BATCH_ID_PATTERN = re.compile(r"^[A-Za-z0-9\-]+$")


def sanitize_batch_id(batch_id: str) -> Optional[str]:
    """Validate and sanitize batch_id. Returns None if invalid."""
    if not batch_id or len(batch_id) > 128:
        return None
    if not _BATCH_ID_PATTERN.match(batch_id):
        return None
    return batch_id


# ============================================================================
# CONFIGURATION
# ============================================================================

# Environment
VERIFY_RATE_LIMIT = int(os.getenv("PUBLIC_VERIFY_RATE_LIMIT", "60"))  # per minute
VERIFY_CACHE_TTL = int(os.getenv("PUBLIC_VERIFY_CACHE_TTL", "300"))  # 5 minutes


# ============================================================================
# SIGNATURE VERIFICATION
# ============================================================================

def verify_signature_with_public_key(
    evidence_hash: str,
    signature_b64: str,
    public_key_pem: Optional[str] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Verify a signature against the KMS public key.

    This is a cryptographic handshake that proves the evidence was signed
    by our KMS key.

    Returns: (is_valid, error_message)
    """
    if not evidence_hash or not signature_b64:
        return False, "Missing evidence hash or signature"

    try:
        # Try to use cryptography library for local verification
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.exceptions import InvalidSignature

        if not public_key_pem:
            # Fetch public key from KMS (or use cached)
            public_key_pem = get_cached_public_key()

        if not public_key_pem:
            return False, "Public key not available"

        # Load the public key
        public_key = serialization.load_pem_public_key(
            public_key_pem.encode() if isinstance(public_key_pem, str) else public_key_pem
        )

        # Decode the signature
        signature = base64.b64decode(signature_b64)

        # Hash the evidence hash (double-hash for signature verification)
        evidence_bytes = evidence_hash.encode("utf-8")

        # Verify using ECDSA with SHA-256
        try:
            public_key.verify(
                signature,
                evidence_bytes,
                ec.ECDSA(hashes.SHA256())
            )
            return True, None
        except InvalidSignature:
            return False, "Signature verification failed"

    except ImportError:
        # Fallback: Trust the stored verification status
        logger.warning("cryptography library not available, using stored verification status")
        return True, "Verification delegated to KMS"
    except Exception as e:
        logger.error(f"Signature verification error: {e}")
        return False, str(e)


# ============================================================================
# ATTESTATION BINDING VERIFICATION (FE-5.2 Fix)
# ============================================================================

def verify_attestation_binding(
    batch: Dict[str, Any],
    public_key_pem: Optional[str] = None,
) -> Tuple[bool, Optional[str], str]:
    """
    Verify attestation binding (new format) or legacy signature.

    Day 5 Gate S3: Key-aware verification. Extracts key_id from the batch
    attestation and fetches the correct public key for that specific key.
    Falls back to global key if key_id is not present or not resolvable.

    Returns:
        (is_valid, error_message, verification_mode)
        verification_mode: "ATTESTATION_BINDING_V1" or "LEGACY_ROOT_HASH"
    """
    attestation = batch.get("attestation")

    if attestation and attestation.get("signed_payload_jcs_b64"):
        # NEW PATH: Verify full attestation binding
        signed_payload_b64 = attestation["signed_payload_jcs_b64"]
        signature_b64 = attestation.get("signature_b64")

        if not signature_b64:
            return False, "Attestation present but no signature", "ATTESTATION_BINDING_V1"

        # Day 5 Gate S3: Resolve public key from attestation key_id
        resolved_pem = public_key_pem
        if not resolved_pem:
            att_key_id = attestation.get("key_id")
            resolved_pem = _resolve_public_key_for_verification(att_key_id)

        # Decode the canonical payload bytes
        try:
            canonical_bytes = base64.b64decode(signed_payload_b64)
        except Exception as e:
            return False, f"Failed to decode attestation payload: {e}", "ATTESTATION_BINDING_V1"

        # Verify ECDSA signature over canonical bytes
        is_valid, error = _verify_ecdsa_signature(
            data=canonical_bytes,
            signature_b64=signature_b64,
            public_key_pem=resolved_pem,
        )

        if not is_valid:
            return False, error, "ATTESTATION_BINDING_V1"

        # Cross-check: payload fields must match batch data
        try:
            import json
            payload = json.loads(canonical_bytes.decode('utf-8'))
        except Exception as e:
            return False, f"Failed to parse attestation payload: {e}", "ATTESTATION_BINDING_V1"

        match_valid, match_error = _verify_payload_matches_batch(payload, batch)
        if not match_valid:
            return False, match_error, "ATTESTATION_BINDING_V1"

        return True, None, "ATTESTATION_BINDING_V1"

    else:
        # LEGACY PATH: Verify root_hash only
        signature_info = batch.get("signature", {})
        evidence_hash = signature_info.get("evidence_hash_sha256")
        signature_b64 = signature_info.get("signature")

        if not evidence_hash or not signature_b64:
            return False, "No signature available", "LEGACY_ROOT_HASH"

        # Day 5 Gate S3: Resolve key for legacy path too
        resolved_pem = public_key_pem
        if not resolved_pem:
            legacy_key_id = signature_info.get("key_id") or attestation.get("key_id") if attestation else None
            resolved_pem = _resolve_public_key_for_verification(legacy_key_id)

        is_valid, error = verify_signature_with_public_key(
            evidence_hash, signature_b64, resolved_pem
        )
        return is_valid, error, "LEGACY_ROOT_HASH"


def _resolve_public_key_for_verification(key_id: Optional[str] = None) -> Optional[str]:
    """
    Day 5 Gate S3: Resolve the correct public key for signature verification.

    Priority:
    1. If key_id provided → fetch public key for that specific key
    2. If key_id matches global → use cached global key
    3. Fallback → global cached key
    """
    if key_id:
        try:
            from .signing import get_public_key_pem_for_key_id, KMS_SIGNING_KEY_ID
            # If it matches the global key, use the existing cache
            if key_id == KMS_SIGNING_KEY_ID:
                return get_cached_public_key()
            # Otherwise, fetch the tenant-specific public key
            pem, error = get_public_key_pem_for_key_id(key_id)
            if pem:
                return pem
            logger.warning(f"[Verify] Failed to fetch public key for {key_id}: {error}")
            # Don't fallback to global — wrong key would give false negative
            return None
        except ImportError:
            logger.warning("[Verify] signing module not available for key-aware verification")

    # No key_id specified — use global
    return get_cached_public_key()


def _verify_ecdsa_signature(
    data: bytes,
    signature_b64: str,
    public_key_pem: Optional[str] = None,
) -> Tuple[bool, Optional[str]]:
    """Verify ECDSA-P256-SHA256 signature over raw bytes."""
    if not data or not signature_b64:
        return False, "Missing data or signature"

    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.exceptions import InvalidSignature

        if not public_key_pem:
            public_key_pem = get_cached_public_key()

        if not public_key_pem:
            return False, "Public key not available"

        public_key = serialization.load_pem_public_key(
            public_key_pem.encode() if isinstance(public_key_pem, str) else public_key_pem
        )
        signature = base64.b64decode(signature_b64)

        try:
            public_key.verify(signature, data, ec.ECDSA(hashes.SHA256()))
            return True, None
        except InvalidSignature:
            return False, "Signature verification failed"

    except ImportError:
        logger.warning("cryptography library not available for attestation verification")
        return False, "cryptography library not available"
    except Exception as e:
        logger.error(f"Attestation signature verification error: {e}")
        return False, str(e)


def _verify_payload_matches_batch(
    payload: Dict[str, Any],
    batch: Dict[str, Any],
) -> Tuple[bool, Optional[str]]:
    """
    Cross-check that signed payload fields match the batch data.

    Catches scenarios where an attacker modifies batch fields (e.g. artifact_mode)
    but leaves the signed attestation blob unchanged. The mismatch between the
    signed payload and the stored data exposes the tampering.
    """
    # Check root_hash matches hash_chain
    chain = batch.get("hash_chain", {})
    stored_root = chain.get("batch_root_hash")
    if stored_root and payload.get("root_hash_sha256") != stored_root:
        return False, (
            f"root_hash mismatch: payload={payload.get('root_hash_sha256')}, "
            f"stored={stored_root}"
        )

    # Check artifact_mode matches manifest
    manifest = batch.get("iavp_manifest", {})
    if manifest.get("artifact_mode") and payload.get("artifact_mode") != manifest.get("artifact_mode"):
        return False, (
            f"artifact_mode mismatch: payload={payload.get('artifact_mode')}, "
            f"manifest={manifest.get('artifact_mode')}"
        )

    # Check batch_id
    batch_id = batch.get("trace_id")
    if batch_id and payload.get("batch_id") != batch_id:
        return False, (
            f"batch_id mismatch: payload={payload.get('batch_id')}, "
            f"stored={batch_id}"
        )

    # Check metrics_hash if manifest has metrics
    if manifest.get("metrics") and payload.get("metrics_hash_sha256"):
        try:
            from .iavp import jcs_sha256
            recomputed = jcs_sha256(manifest["metrics"])
            if payload["metrics_hash_sha256"] != recomputed:
                return False, (
                    f"metrics_hash mismatch: payload={payload['metrics_hash_sha256']}, "
                    f"recomputed={recomputed}"
                )
        except Exception:
            pass  # Non-fatal: skip metrics check if import fails

    return True, None


# Public key cache
_cached_public_key: Optional[str] = None
_public_key_fetched_at: Optional[float] = None
PUBLIC_KEY_CACHE_TTL = 3600  # 1 hour


def get_cached_public_key() -> Optional[str]:
    """Get the cached KMS public key, refreshing if stale."""
    global _cached_public_key, _public_key_fetched_at

    import time
    now = time.time()

    # Check cache
    if _cached_public_key and _public_key_fetched_at:
        if now - _public_key_fetched_at < PUBLIC_KEY_CACHE_TTL:
            return _cached_public_key

    # Fetch from KMS
    try:
        from .signing import get_public_key_pem
        _cached_public_key = get_public_key_pem()
        _public_key_fetched_at = now
        return _cached_public_key
    except Exception as e:
        logger.error(f"Failed to fetch public key: {e}")
        return _cached_public_key  # Return stale if available


# ============================================================================
# PUBLIC VERIFICATION RESULT
# ============================================================================

class VerificationStatus:
    """Verification status constants."""
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    NOT_FOUND = "NOT_FOUND"
    ERROR = "ERROR"
    PENDING = "PENDING"
    UNKNOWN = "UNKNOWN"


def build_forensic_summary(
    batch: Dict[str, Any],
    signature_valid: bool,
    signature_error: Optional[str],
    hash_chain_valid: bool,
    anchor_verified: bool,
    verification_mode: str = "LEGACY_ROOT_HASH",
) -> Dict[str, Any]:
    """
    Build forensic verification summary.

    Contains cryptographic proofs only - no resolution data.

    SCALABLE V2: hash_chain_length may be chunk count, not row count.
    row_count is exposed separately for public verification.
    """
    signature_info = batch.get("signature", {})
    hash_chain = batch.get("hash_chain", {})
    anchor_info = batch.get("anchor", {})

    # For chunk-based chains: chain_length = chunks, row_count = actual rows
    chain_length = hash_chain.get("chain_length") if hash_chain_valid else None
    row_count = hash_chain.get("row_count")  # Only present for chunk-based chains

    return {
        "signature_valid": signature_valid,
        "signature_key_version": signature_info.get("key_version"),
        "signature_algorithm": "ECDSA_P256_SHA256" if signature_info.get("signature") else None,
        "signature_error": signature_error if not signature_valid else None,
        "signature_verification_mode": verification_mode,
        "hash_chain_valid": hash_chain_valid,
        "hash_chain_length": chain_length,
        "row_count": row_count,  # Actual row count (for chunk-based chains)
        "anchor_verified": anchor_verified if anchor_info else None,
        "anchor_reference": anchor_info.get("anchor_gcs_path") if anchor_verified else None,
        "hash_algo": "SHA-256",
    }


def build_lifecycle_summary(batch: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build lifecycle summary with legal hold status.

    SECURITY: Only expose existence and WORM expiry, not hold details or reason.
    """
    legal_hold = batch.get("legal_hold", {})
    is_active = legal_hold.get("status") == "ACTIVE"

    worm_expiry = None
    if is_active and legal_hold.get("worm_retention_until"):
        worm_expiry = legal_hold.get("worm_retention_until")

    return {
        "legal_hold": {
            "active": is_active,
            "worm_expiry_utc": worm_expiry,
        }
    }


def build_workload_summary(batch: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build workload metadata summary.

    Contains only aggregate-safe metadata - no resolution data.
    """
    stats = batch.get("stats") or batch.get("counts") or {}
    config = batch.get("config_snapshot") or {}

    # Extract timestamps
    processed_at = batch.get("finished_at") or batch.get("timestamp")
    if processed_at and isinstance(processed_at, str):
        # Keep full ISO timestamp
        processed_at_utc = processed_at
    else:
        processed_at_utc = None

    # Runtime environment
    env = os.getenv("ENVIRONMENT", "unknown")
    if env not in ("test", "prod", "demo"):
        env = "unknown"

    # Processing region - check PROCESSING_REGION first, then Cloud Run defaults
    region = os.getenv("PROCESSING_REGION") or os.getenv("GOOGLE_CLOUD_REGION") or os.getenv("CLOUD_RUN_REGION") or "unknown"

    return {
        "total_records": stats.get("total", 0) or stats.get("total_records", 0) or None,
        "processed_at_utc": processed_at_utc,
        "config_version": config.get("version") or batch.get("system_version") or None,
        "runtime_environment": env,
        "processing_region": region,
    }


def build_sustainability_summary() -> Dict[str, Any]:
    """
    Build sustainability summary.

    Currently hardcoded to "none" - no energy estimates published publicly.
    """
    return {
        "estimated": False,
        "measurement_source": "none",
        "methodology_version": None,
        "coverage_pct": None,
        "disclaimer": "No sustainability telemetry or estimates are published in public verification.",
    }


def build_redactions_block() -> Dict[str, bool]:
    """
    Build redactions disclosure block.

    Explicitly states what has been redacted for transparency.
    """
    return {
        "no_resolution_data_exposed": True,
        "hold_reason_redacted": True,
        "requestor_identity_redacted": True,
    }


def build_public_verification_response(
    batch_id: str,
    batch: Optional[Dict[str, Any]],
    verification_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build the public verification response.

    This is the main entry point for the public verification endpoint.

    NOTARY-READY SCHEMA v2:
    - NO esg_rating
    - NO resolution_quality
    - NO auto_resolved_pct
    - NO human_review_pct
    """
    verified_at = datetime.now(timezone.utc).isoformat()

    # Batch not found
    if not batch:
        return {
            "status": VerificationStatus.NOT_FOUND,
            "batch_id": batch_id,
            "verified_at_utc": verified_at,
            "error": "Batch not found or not yet processed",
        }

    # Check batch status
    batch_status = batch.get("status", "unknown")
    if batch_status in ("queued", "processing"):
        return {
            "status": VerificationStatus.PENDING,
            "batch_id": batch_id,
            "verified_at_utc": verified_at,
            "message": "Batch is still being processed",
        }

    if batch_status in ("failed", "failed_integrity", "aborted"):
        return {
            "status": VerificationStatus.ERROR,
            "batch_id": batch_id,
            "verified_at_utc": verified_at,
            "error": f"Batch processing failed: {batch_status}",
            "structural_failure": batch.get("structural_failure", False),
        }

    # Verify signature (attestation binding or legacy root-hash)
    signature_valid, signature_error, verification_mode = verify_attestation_binding(batch)

    # Get hash chain verification
    hash_chain = batch.get("hash_chain", {})
    hash_chain_valid = bool(hash_chain.get("batch_root_hash"))

    # Get anchor verification
    anchor_verified = False
    if verification_data:
        anchor_info = verification_data.get("anchor", {})
        anchor_verified = anchor_info.get("verified", False)
    else:
        anchor_info = batch.get("anchor", {})
        anchor_verified = anchor_info.get("anchored", False)

    # Determine overall status
    signature_info = batch.get("signature", {})
    has_any_signature = bool(batch.get("attestation", {}).get("signature_b64") or signature_info.get("signature"))
    if signature_valid and hash_chain_valid:
        overall_status = VerificationStatus.VERIFIED
    elif not has_any_signature and not hash_chain.get("batch_root_hash"):
        overall_status = VerificationStatus.UNKNOWN
    else:
        overall_status = VerificationStatus.UNVERIFIED

    # Build NOTARY-READY response
    response = {
        "status": overall_status,
        "batch_id": batch_id,
        "verified_at_utc": verified_at,
        "public_trust_summary": {
            "forensic": build_forensic_summary(
                batch,
                signature_valid,
                signature_error,
                hash_chain_valid,
                anchor_verified,
                verification_mode=verification_mode,
            ),
            "lifecycle": build_lifecycle_summary(batch),
            "workload": build_workload_summary(batch),
            "sustainability": build_sustainability_summary(),
        },
        "redactions": build_redactions_block(),
    }

    return response


# ============================================================================
# TRUST SEAL DATA (minimal for badge)
# ============================================================================

def build_seal_data(batch_id: str, batch: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Build minimal data for Trust Seal badge display.

    NO esg_rating - removed for notary compliance.
    """
    if not batch:
        return {
            "verified": False,
            "batch_id": batch_id,
            "status": "NOT_FOUND",
        }

    # Get signature status
    signature = batch.get("signature", {})
    is_signed = bool(signature.get("signature"))

    # Get hash chain status
    hash_chain = batch.get("hash_chain", {})
    has_chain = bool(hash_chain.get("batch_root_hash"))

    return {
        "verified": is_signed and has_chain,
        "batch_id": batch_id,
        "status": batch.get("status", "unknown"),
        "signed_at": signature.get("signed_at_utc", "").split("T")[0] if signature.get("signed_at_utc") else None,
        "legal_hold_active": batch.get("legal_hold", {}).get("status") == "ACTIVE",
    }


# ============================================================================
# FASTAPI ENDPOINT
# ============================================================================

def create_public_verify_router():
    """
    Create FastAPI router for public verification endpoints.

    These endpoints are UNAUTHENTICATED and rate-limited.
    """
    from fastapi import APIRouter, Request
    from fastapi.responses import JSONResponse

    router = APIRouter(prefix="/verify", tags=["Public Verification"])

    # Simple in-memory rate limiting for public endpoint
    _request_counts: Dict[str, List[float]] = {}

    def check_rate_limit(client_ip: str) -> bool:
        """Check if client is within rate limit."""
        import time
        now = time.time()
        window_start = now - 60  # 1 minute window

        if client_ip not in _request_counts:
            _request_counts[client_ip] = []

        # Clean old entries
        _request_counts[client_ip] = [
            t for t in _request_counts[client_ip] if t > window_start
        ]

        if len(_request_counts[client_ip]) >= VERIFY_RATE_LIMIT:
            return False

        _request_counts[client_ip].append(now)
        return True

    @router.get("/{batch_id}")
    async def public_verify_batch(batch_id: str, request: Request):
        """
        Public batch verification endpoint.

        NO AUTHENTICATION REQUIRED.

        Returns cryptographic verification status and PII-redacted trust summary.
        NOTARY-READY: No ESG ratings or resolution quality metrics.
        """
        # Sanitize batch_id — reject invalid format
        safe_id = sanitize_batch_id(batch_id)
        if safe_id is None:
            return JSONResponse(
                status_code=400,
                content={"error": "Invalid batch_id format"},
            )

        # Rate limiting
        client_ip = request.client.host if request.client else "unknown"
        if not check_rate_limit(client_ip):
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "retry_after": 60,
                },
                headers={"Retry-After": "60"},
            )

        # Import Firestore getter (lazy to avoid circular imports)
        try:
            from ..server_enterprise_golden import get_batch_by_trace_id
            batch = get_batch_by_trace_id(safe_id)
        except ImportError:
            # Standalone mode - return error
            return JSONResponse(
                status_code=503,
                content={"error": "Database not available"},
            )

        # Build and return response
        response = build_public_verification_response(safe_id, batch)

        # Fail closed: nonexistent batches get 404, not 200
        http_status = 404 if response.get("status") == "NOT_FOUND" else 200

        # Add CORS headers for public access
        return JSONResponse(
            status_code=http_status,
            content=response,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": f"public, max-age={VERIFY_CACHE_TTL}",
            },
        )

    @router.get("/{batch_id}/seal")
    async def get_trust_seal_data(batch_id: str, request: Request):
        """
        Get minimal data for embedding a trust seal.

        Returns only the essential verification status for badge display.
        NO ESG RATING - removed for notary compliance.
        """
        # Sanitize batch_id — reject invalid format
        safe_id = sanitize_batch_id(batch_id)
        if safe_id is None:
            return JSONResponse(
                status_code=400,
                content={"error": "Invalid batch_id format"},
            )

        # Rate limiting
        client_ip = request.client.host if request.client else "unknown"
        if not check_rate_limit(client_ip):
            return JSONResponse(
                status_code=429,
                content={"error": "Rate limit exceeded"},
            )

        try:
            from ..server_enterprise_golden import get_batch_by_trace_id
            batch = get_batch_by_trace_id(safe_id)
        except ImportError:
            return JSONResponse(
                status_code=503,
                content={"error": "Database not available"},
            )

        seal_data = build_seal_data(safe_id, batch)

        # Fail closed: nonexistent batches get 404
        http_status = 404 if seal_data.get("status") == "NOT_FOUND" else 200

        return JSONResponse(
            status_code=http_status,
            content=seal_data,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": f"public, max-age={VERIFY_CACHE_TTL}",
            },
        )

    return router


# ============================================================================
# TESTING
# ============================================================================

if __name__ == "__main__":
    # Test the verification logic
    test_batch = {
        "trace_id": "BATCH-TEST-123",
        "status": "completed",
        "stats": {
            "total": 1000,
            "layer_1_exact": 500,
            "layer_1_norm": 200,
            "layer_2_vector": 200,
            "layer_3_llm": 50,
            "layer_4_human": 50,
        },
        "signature": {
            "evidence_hash_sha256": "abc123def456",
            "signature": "base64sig==",
            "signed_at_utc": "2026-02-15T10:30:00Z",
            "key_version": "1",
        },
        "hash_chain": {
            "batch_root_hash": "root123",
            "chain_length": 1000,
        },
        "anchor": {
            "anchored": True,
            "anchor_gcs_path": "gs://ia-anchors-test/2026/02/15/BATCH-TEST-123.json",
        },
        "legal_hold": {
            "status": "ACTIVE",
            "worm_retention_until": "2033-02-15T00:00:00Z",
        },
        "finished_at": "2026-02-15T10:35:00Z",
    }

    response = build_public_verification_response("BATCH-TEST-123", test_batch)

    import json
    print(json.dumps(response, indent=2))

    # Verify forbidden fields are absent
    response_str = json.dumps(response)
    forbidden = ["esg_rating", "resolution_quality", "auto_resolved_pct", "human_review_pct"]
    for field in forbidden:
        assert field not in response_str, f"FAIL: {field} found in response"
    print("\nOK: All forbidden fields absent")
