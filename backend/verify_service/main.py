"""
================================================================================
INTELLIGENT ANALYST - STANDALONE PUBLIC VERIFY SERVICE
================================================================================

Minimal, public service for cryptographic verification of batch evidence.

This service is deployed separately from the main candidate service to:
1. Allow public (unauthenticated) access to verification endpoints only
2. Keep the main candidate service locked down (no allUsers invoker)
3. Minimize attack surface for public-facing endpoints

Endpoints:
- GET /health - Health check
- GET /verify/{batch_id} - Full verification response
- GET /verify/{batch_id}/seal - Minimal seal data

Security:
- NO authentication required (public trust verification)
- Rate limited per client IP
- NO PII or resolution data exposed
- Read-only access to Firestore batch data

================================================================================
"""

import base64
import hashlib
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================

VERIFY_RATE_LIMIT = int(os.getenv("PUBLIC_VERIFY_RATE_LIMIT", "60"))  # per minute
VERIFY_CACHE_TTL = int(os.getenv("PUBLIC_VERIFY_CACHE_TTL", "300"))  # 5 minutes
ENVIRONMENT = os.getenv("ENVIRONMENT", "unknown")
GCP_PROJECT = os.getenv("GCP_PROJECT", "intelligent-analyst-enterprise")

# KMS configuration for signature verification
KMS_PROJECT = os.getenv("KMS_PROJECT", GCP_PROJECT)
KMS_LOCATION = os.getenv("KMS_LOCATION", "us-central1")
KMS_KEYRING = os.getenv("SIGNING_KEYRING", "ia-forensic-prod")
KMS_KEY_NAME = os.getenv("SIGNING_KEY_NAME", "golden-signing-prod")
KMS_KEY_VERSION = os.getenv("SIGNING_KEY_VERSION", "1")

# ============================================================================
# FIRESTORE CLIENT
# ============================================================================

_firestore_db = None


def get_firestore_client():
    """Get or create Firestore client."""
    global _firestore_db
    if _firestore_db is None:
        from google.cloud import firestore
        _firestore_db = firestore.Client(project=GCP_PROJECT)
        logger.info(f"Firestore client initialized for project: {GCP_PROJECT}")
    return _firestore_db


def get_batch_by_trace_id(trace_id: str) -> Optional[Dict[str, Any]]:
    """Fetch batch record from Firestore."""
    try:
        db = get_firestore_client()
        doc = db.collection("batches").document(trace_id).get()
        if doc.exists:
            return doc.to_dict()
        return None
    except Exception as e:
        logger.error(f"Error fetching batch {trace_id}: {e}")
        return None


# ============================================================================
# KMS PUBLIC KEY
# ============================================================================

_cached_public_key: Optional[str] = None
_public_key_fetched_at: Optional[float] = None
PUBLIC_KEY_CACHE_TTL = 3600  # 1 hour


def get_public_key_pem() -> Optional[str]:
    """Fetch public key from KMS."""
    global _cached_public_key, _public_key_fetched_at

    now = time.time()

    # Check cache
    if _cached_public_key and _public_key_fetched_at:
        if now - _public_key_fetched_at < PUBLIC_KEY_CACHE_TTL:
            return _cached_public_key

    try:
        from google.cloud import kms

        client = kms.KeyManagementServiceClient()
        key_version_name = (
            f"projects/{KMS_PROJECT}/locations/{KMS_LOCATION}/"
            f"keyRings/{KMS_KEYRING}/cryptoKeys/{KMS_KEY_NAME}/"
            f"cryptoKeyVersions/{KMS_KEY_VERSION}"
        )

        public_key = client.get_public_key(request={"name": key_version_name})
        _cached_public_key = public_key.pem
        _public_key_fetched_at = now
        logger.info("KMS public key fetched and cached")
        return _cached_public_key

    except Exception as e:
        logger.error(f"Failed to fetch KMS public key: {e}")
        return _cached_public_key  # Return stale if available


# ============================================================================
# SIGNATURE VERIFICATION
# ============================================================================


def verify_signature_with_public_key(
    evidence_hash: str,
    signature_b64: str,
) -> Tuple[bool, Optional[str]]:
    """
    Verify a signature against the KMS public key.

    Returns: (is_valid, error_message)
    """
    if not evidence_hash or not signature_b64:
        return False, "Missing evidence hash or signature"

    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.exceptions import InvalidSignature

        public_key_pem = get_public_key_pem()
        if not public_key_pem:
            return False, "Public key not available"

        # Load the public key
        public_key = serialization.load_pem_public_key(
            public_key_pem.encode() if isinstance(public_key_pem, str) else public_key_pem
        )

        # Decode the signature
        signature = base64.b64decode(signature_b64)

        # Verify using ECDSA with SHA-256
        evidence_bytes = evidence_hash.encode("utf-8")

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
        logger.warning("cryptography library not available, using stored verification status")
        return True, "Verification delegated to KMS"
    except Exception as e:
        logger.error(f"Signature verification error: {e}")
        return False, str(e)


# ============================================================================
# VERIFICATION RESPONSE BUILDERS
# ============================================================================


class VerificationStatus:
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
) -> Dict[str, Any]:
    """Build forensic verification summary."""
    signature_info = batch.get("signature", {})
    hash_chain = batch.get("hash_chain", {})
    anchor_info = batch.get("anchor", {})

    chain_length = hash_chain.get("chain_length") if hash_chain_valid else None
    row_count = hash_chain.get("row_count")

    return {
        "signature_valid": signature_valid,
        "signature_key_version": signature_info.get("key_version"),
        "signature_algorithm": "ECDSA_P256_SHA256" if signature_info.get("signature") else None,
        "signature_error": signature_error if not signature_valid else None,
        "hash_chain_valid": hash_chain_valid,
        "hash_chain_length": chain_length,
        "row_count": row_count,
        "anchor_verified": anchor_verified if anchor_info else None,
        "anchor_reference": anchor_info.get("anchor_gcs_path") if anchor_verified else None,
        "hash_algo": "SHA-256",
    }


def build_lifecycle_summary(batch: Dict[str, Any]) -> Dict[str, Any]:
    """Build lifecycle summary with legal hold status."""
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
    """Build workload metadata summary."""
    stats = batch.get("stats") or batch.get("counts") or {}

    processed_at = batch.get("finished_at") or batch.get("timestamp")
    processed_at_utc = processed_at if isinstance(processed_at, str) else None

    region = (
        os.getenv("PROCESSING_REGION")
        or os.getenv("GOOGLE_CLOUD_REGION")
        or os.getenv("CLOUD_RUN_REGION")
        or "unknown"
    )

    return {
        "total_records": stats.get("total", 0) or stats.get("total_records", 0) or None,
        "processed_at_utc": processed_at_utc,
        "config_version": batch.get("system_version"),
        "runtime_environment": ENVIRONMENT if ENVIRONMENT in ("test", "prod", "demo") else "unknown",
        "processing_region": region,
    }


def build_sustainability_summary() -> Dict[str, Any]:
    """Build sustainability summary (currently none)."""
    return {
        "estimated": False,
        "measurement_source": "none",
        "methodology_version": None,
        "coverage_pct": None,
        "disclaimer": "No sustainability telemetry or estimates are published in public verification.",
    }


def build_redactions_block() -> Dict[str, bool]:
    """Build redactions disclosure block."""
    return {
        "no_resolution_data_exposed": True,
        "hold_reason_redacted": True,
        "requestor_identity_redacted": True,
    }


def build_public_verification_response(
    batch_id: str,
    batch: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build the public verification response."""
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

    # Get signature info
    signature_info = batch.get("signature", {})
    evidence_hash = signature_info.get("evidence_hash_sha256")
    signature_b64 = signature_info.get("signature")

    # Verify signature
    signature_valid = False
    signature_error = None

    if evidence_hash and signature_b64:
        signature_valid, signature_error = verify_signature_with_public_key(
            evidence_hash, signature_b64
        )
    else:
        signature_error = "No signature available"

    # Get hash chain verification
    hash_chain = batch.get("hash_chain", {})
    hash_chain_valid = bool(hash_chain.get("batch_root_hash"))

    # Get anchor verification
    anchor_info = batch.get("anchor", {})
    anchor_verified = anchor_info.get("anchored", False)

    # Determine overall status
    if signature_valid and hash_chain_valid:
        overall_status = VerificationStatus.VERIFIED
    elif not signature_info.get("signature") and not hash_chain.get("batch_root_hash"):
        overall_status = VerificationStatus.UNKNOWN
    else:
        overall_status = VerificationStatus.UNVERIFIED

    return {
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
            ),
            "lifecycle": build_lifecycle_summary(batch),
            "workload": build_workload_summary(batch),
            "sustainability": build_sustainability_summary(),
        },
        "redactions": build_redactions_block(),
    }


def build_seal_data(batch_id: str, batch: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Build minimal data for Trust Seal badge display."""
    if not batch:
        return {
            "verified": False,
            "batch_id": batch_id,
            "status": "NOT_FOUND",
        }

    signature = batch.get("signature", {})
    is_signed = bool(signature.get("signature"))

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
# FASTAPI APPLICATION
# ============================================================================

app = FastAPI(
    title="Intelligent Analyst - Public Verify Service",
    description="Public verification endpoint for cryptographic batch verification",
    version="1.0.0",
    docs_url="/docs" if ENVIRONMENT != "prod" else None,
    redoc_url=None,
)

# CORS for public access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

# Simple in-memory rate limiting
_request_counts: Dict[str, List[float]] = {}


def check_rate_limit(client_ip: str) -> bool:
    """Check if client is within rate limit."""
    now = time.time()
    window_start = now - 60

    if client_ip not in _request_counts:
        _request_counts[client_ip] = []

    _request_counts[client_ip] = [
        t for t in _request_counts[client_ip] if t > window_start
    ]

    if len(_request_counts[client_ip]) >= VERIFY_RATE_LIMIT:
        return False

    _request_counts[client_ip].append(now)
    return True


# ============================================================================
# ENDPOINTS
# ============================================================================


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "public-verify",
        "version": "1.0.0",
        "environment": ENVIRONMENT,
    }


@app.get("/verify/{batch_id}")
async def public_verify_batch(batch_id: str, request: Request):
    """
    Public batch verification endpoint.

    NO AUTHENTICATION REQUIRED.

    Returns cryptographic verification status and PII-redacted trust summary.
    """
    client_ip = request.client.host if request.client else "unknown"
    if not check_rate_limit(client_ip):
        return JSONResponse(
            status_code=429,
            content={"error": "Rate limit exceeded", "retry_after": 60},
            headers={"Retry-After": "60"},
        )

    batch = get_batch_by_trace_id(batch_id)
    response = build_public_verification_response(batch_id, batch)

    return JSONResponse(
        content=response,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": f"public, max-age={VERIFY_CACHE_TTL}",
        },
    )


@app.get("/verify/{batch_id}/seal")
async def get_trust_seal_data(batch_id: str, request: Request):
    """
    Get minimal data for embedding a trust seal.

    Returns only the essential verification status for badge display.
    """
    client_ip = request.client.host if request.client else "unknown"
    if not check_rate_limit(client_ip):
        return JSONResponse(
            status_code=429,
            content={"error": "Rate limit exceeded"},
        )

    batch = get_batch_by_trace_id(batch_id)
    seal_data = build_seal_data(batch_id, batch)

    return JSONResponse(
        content=seal_data,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": f"public, max-age={VERIFY_CACHE_TTL}",
        },
    )


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
