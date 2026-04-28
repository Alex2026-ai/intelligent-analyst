"""
================================================================================
INTELLIGENT ANALYST - KMS SIGNING MODULE (Phase 0.5)
================================================================================

Provides Cloud KMS-based asymmetric signing for evidence blobs.
- Uses EC P-256 with SHA-256 (ec-sign-p256-sha256)
- Canonical JSON serialization for deterministic hashing
- Service identity metadata capture

Key configuration via environment:
- KMS_SIGNING_KEY_ID: Full KMS key resource path
- SIGNING_ENABLED: true/false
- SIGNING_ALG: Algorithm identifier (default: EC_SIGN_P256_SHA256)

================================================================================
"""

import os
import json
import hashlib
import base64
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple
import subprocess

# KMS client - lazy loaded
_kms_client = None
_kms_available = False

try:
    from google.cloud import kms
    _kms_available = True
except ImportError:
    _kms_available = False
    print("[Signing] google-cloud-kms not available", flush=True)


# Configuration
SIGNING_ENABLED = os.getenv("SIGNING_ENABLED", "true").lower() == "true"
KMS_SIGNING_KEY_ID = os.getenv("KMS_SIGNING_KEY_ID", "")
SIGNING_ALG = os.getenv("SIGNING_ALG", "EC_SIGN_P256_SHA256")

# Day 5: Tenant-scoped signing key aliases
# Format: "tenant_a:key_path_a,tenant_b:key_path_b"
_TENANT_SIGNING_KEY_MAP_RAW = os.getenv("TENANT_SIGNING_KEY_MAP", "")


def _parse_tenant_signing_key_map(raw: str) -> Dict[str, str]:
    """Parse comma-separated tenant:key_path pairs."""
    if not raw:
        return {}
    result = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if ":" in entry:
            tenant, key_path = entry.split(":", 1)
            tenant, key_path = tenant.strip(), key_path.strip()
            if tenant and key_path:
                result[tenant] = key_path
    return result


_TENANT_SIGNING_KEY_MAP = _parse_tenant_signing_key_map(_TENANT_SIGNING_KEY_MAP_RAW)


def resolve_signing_key_id(tenant_id: Optional[str] = None) -> str:
    """
    Resolve signing key for a tenant.
    Priority: 1) tenant override, 2) global KMS_SIGNING_KEY_ID, 3) "local-signing-key".
    """
    if tenant_id and tenant_id in _TENANT_SIGNING_KEY_MAP:
        return _TENANT_SIGNING_KEY_MAP[tenant_id]
    return KMS_SIGNING_KEY_ID or "local-signing-key"


# Service identity metadata (captured at startup)
_service_identity: Dict[str, Any] = {}


def _get_kms_client():
    """Lazy-load KMS client."""
    global _kms_client
    if _kms_client is None and _kms_available:
        _kms_client = kms.KeyManagementServiceClient()
    return _kms_client


def _capture_service_identity() -> Dict[str, Any]:
    """Capture service identity metadata at startup."""
    global _service_identity

    if _service_identity:
        return _service_identity

    # Cloud Run service name
    service_name = os.getenv("K_SERVICE", "local-dev")

    # Service account email (from metadata server or env)
    service_account = os.getenv("GOOGLE_CLOUD_SERVICE_ACCOUNT", "")
    if not service_account:
        try:
            # Try metadata server
            import urllib.request
            req = urllib.request.Request(
                "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/email",
                headers={"Metadata-Flavor": "Google"}
            )
            with urllib.request.urlopen(req, timeout=2) as resp:
                service_account = resp.read().decode('utf-8')
        except:
            service_account = "unknown"

    # Git SHA (code version)
    code_version = os.getenv("CODE_VERSION", "")
    if not code_version:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                code_version = result.stdout.strip()[:12]
        except:
            code_version = "unknown"

    _service_identity = {
        "service_name": service_name,
        "service_account": service_account,
        "code_version": code_version,
        "revision": os.getenv("K_REVISION", "local"),
    }

    return _service_identity


def canonicalize_json(obj: Any) -> bytes:
    """
    Produce canonical JSON bytes for signing.

    - Sorted keys (recursive)
    - No whitespace
    - UTF-8 encoding
    - Consistent float formatting
    """
    def _sort_recursive(item):
        if isinstance(item, dict):
            return {k: _sort_recursive(v) for k, v in sorted(item.items())}
        elif isinstance(item, list):
            return [_sort_recursive(v) for v in item]
        elif isinstance(item, float):
            # Consistent float representation
            if item == int(item):
                return int(item)
            return round(item, 10)
        return item

    sorted_obj = _sort_recursive(obj)
    return json.dumps(sorted_obj, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def sha256_bytes(data: bytes) -> str:
    """Compute SHA-256 hash of bytes, return hex string."""
    return hashlib.sha256(data).hexdigest()


def sha256_str(text: str) -> str:
    """Compute SHA-256 hash of string, return hex string."""
    return sha256_bytes(text.encode('utf-8'))


def sign_bytes_kms(data: bytes, key_id_override: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    """
    Sign bytes using Cloud KMS.

    Args:
        data: Bytes to sign
        key_id_override: Optional tenant-scoped key path (Day 5).
                         Falls back to global KMS_SIGNING_KEY_ID if not provided.

    Returns:
        (signature_b64, error_message)
        - signature_b64: Base64-encoded signature, or None on error
        - error_message: None on success, or error description
    """
    if not SIGNING_ENABLED:
        return None, "signing_disabled"

    if not _kms_available:
        return None, "kms_not_available"

    effective_key_id = key_id_override or KMS_SIGNING_KEY_ID
    if not effective_key_id:
        return None, "kms_key_not_configured"

    client = _get_kms_client()
    if not client:
        return None, "kms_client_init_failed"

    try:
        # Compute digest
        digest = hashlib.sha256(data).digest()

        # Build key version path (use version 1)
        key_version_path = f"{effective_key_id}/cryptoKeyVersions/1"

        # Sign using KMS
        sign_response = client.asymmetric_sign(
            request={
                "name": key_version_path,
                "digest": {"sha256": digest}
            }
        )

        signature_b64 = base64.b64encode(sign_response.signature).decode('ascii')
        return signature_b64, None

    except Exception as e:
        return None, f"kms_sign_error: {str(e)}"


def build_signature_metadata(
    evidence_hash: str,
    signature_b64: Optional[str],
    sign_error: Optional[str]
) -> Dict[str, Any]:
    """
    Build signature metadata fields for evidence blob.

    Required fields per spec:
    - evidence_hash_sha256
    - signature (base64)
    - signature_alg
    - signing_key_id
    - signing_key_version (for key rotation governance)
    - signed_at_utc
    - service_identity (nested)
    """
    identity = _capture_service_identity()

    # Get signing key version for key rotation governance
    signing_key_version = None
    if signature_b64 and KMS_SIGNING_KEY_ID:
        signing_key_version = "1"  # Currently hardcoded to version 1
        # In production with rotation, this would come from get_signing_key_metadata()

    return {
        "evidence_hash_sha256": evidence_hash,
        "signature": signature_b64,
        "signature_alg": SIGNING_ALG if signature_b64 else None,
        "signing_key_id": KMS_SIGNING_KEY_ID if signature_b64 else None,
        "signing_key_version": signing_key_version,
        "signed_at_utc": datetime.now(timezone.utc).isoformat(),
        "signature_error": sign_error,
        "service_identity": {
            "cloud_run_service": identity.get("service_name"),
            "service_account_email": identity.get("service_account"),
            "code_version": identity.get("code_version"),
            "revision": identity.get("revision"),
        }
    }


def get_public_key_pem() -> Optional[str]:
    """
    Get public key PEM from KMS for signature verification.
    Simple wrapper for public_verify.py compatibility.

    Returns:
        PEM string or None on error
    """
    pem, error = get_public_key_pem_kms()
    return pem


def get_public_key_pem_kms() -> Tuple[Optional[str], Optional[str]]:
    """
    Get public key PEM from KMS for signature verification.

    Returns:
        (public_key_pem, error_message)
    """
    if not _kms_available:
        return None, "kms_not_available"

    if not KMS_SIGNING_KEY_ID:
        return None, "kms_key_not_configured"

    client = _get_kms_client()
    if not client:
        return None, "kms_client_init_failed"

    try:
        key_version_path = f"{KMS_SIGNING_KEY_ID}/cryptoKeyVersions/1"
        public_key = client.get_public_key(request={"name": key_version_path})
        return public_key.pem, None
    except Exception as e:
        return None, f"kms_get_public_key_error: {str(e)}"


# Day 5 Gate S3: Per-key public key cache for verifier key awareness
_public_key_cache: Dict[str, str] = {}  # key_id → PEM


def get_public_key_pem_for_key_id(key_id: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Get public key PEM for a specific KMS key path.

    Used by the verifier to dynamically resolve the correct public key
    based on the key_id stored in the batch attestation.

    Returns:
        (public_key_pem, error_message)
    """
    if not key_id:
        return None, "key_id_not_provided"

    # Check cache
    if key_id in _public_key_cache:
        return _public_key_cache[key_id], None

    if not _kms_available:
        return None, "kms_not_available"

    client = _get_kms_client()
    if not client:
        return None, "kms_client_init_failed"

    try:
        key_version_path = f"{key_id}/cryptoKeyVersions/1"
        public_key = client.get_public_key(request={"name": key_version_path})
        _public_key_cache[key_id] = public_key.pem
        return public_key.pem, None
    except Exception as e:
        return None, f"kms_get_public_key_error: {str(e)}"


def get_signing_key_metadata() -> Dict[str, Any]:
    """
    Get signing key metadata including version and creation time.

    Used for key rotation governance and audit trail.
    """
    if not _kms_available:
        return {"error": "kms_not_available"}

    if not KMS_SIGNING_KEY_ID:
        return {"error": "kms_key_not_configured"}

    client = _get_kms_client()
    if not client:
        return {"error": "kms_client_init_failed"}

    try:
        key_version_path = f"{KMS_SIGNING_KEY_ID}/cryptoKeyVersions/1"
        key_version = client.get_crypto_key_version(request={"name": key_version_path})

        return {
            "signing_key_version": key_version.name.split("/")[-1],
            "signing_key_full_path": key_version.name,
            "key_algorithm": str(key_version.algorithm).split(".")[-1] if key_version.algorithm else SIGNING_ALG,
            "key_state": str(key_version.state).split(".")[-1] if key_version.state else "UNKNOWN",
            "key_created_at": key_version.create_time.isoformat() if key_version.create_time else None,
            "key_generate_time": key_version.generate_time.isoformat() if key_version.generate_time else None,
            "key_protection_level": str(key_version.protection_level).split(".")[-1] if key_version.protection_level else "UNKNOWN",
        }
    except Exception as e:
        return {"error": f"kms_get_key_metadata_error: {str(e)}"}


def get_public_key_info() -> Dict[str, Any]:
    """
    Get complete public key information for external verification.

    Returns dict with:
    - public_key_pem: PEM-encoded public key
    - key_metadata: signing key version and creation info
    - verification_instructions: how to verify signatures externally
    """
    pem, pem_error = get_public_key_pem_kms()
    key_meta = get_signing_key_metadata()

    return {
        "public_key_pem": pem,
        "public_key_error": pem_error,
        "key_metadata": key_meta,
        "algorithm": SIGNING_ALG,
        "hash_algorithm": "SHA256",
        "signature_encoding": "base64",
        "verification_instructions": {
            "step_1": "Decode base64 signature to bytes",
            "step_2": "Compute SHA256 hash of canonical JSON evidence",
            "step_3": "Verify ECDSA signature using public key PEM",
            "step_4": "Use P-256 curve (secp256r1) with SHA-256",
            "openssl_command": "openssl dgst -sha256 -verify pubkey.pem -signature sig.bin evidence.json",
            "python_example": "from cryptography.hazmat.primitives.asymmetric import ec; verifier.verify(signature, digest)"
        }
    }


def get_signing_status() -> Dict[str, Any]:
    """Get signing module status for /health endpoint."""
    identity = _capture_service_identity()

    return {
        "enabled": SIGNING_ENABLED,
        "kms_available": _kms_available,
        "key_id": KMS_SIGNING_KEY_ID[:50] + "..." if len(KMS_SIGNING_KEY_ID) > 50 else KMS_SIGNING_KEY_ID,
        "algorithm": SIGNING_ALG,
        "service_identity": identity,
    }


# Hermetic replay metadata helpers
def build_llm_replay_metadata(
    provider: str = "anthropic",
    model: str = "claude-3-haiku-20240307",
    temperature: float = 0.0,
    top_p: float = 1.0,
    seed: Optional[int] = None,
    seed_supported: bool = False
) -> Dict[str, Any]:
    """
    Build LLM replay metadata for hermetic reproducibility.

    Per spec: If provider doesn't support seeding, store seed_supported=false and seed=null.
    """
    return {
        "llm_provider": provider,
        "llm_model": model,
        "llm_temperature": temperature,
        "llm_top_p": top_p,
        "llm_seed": seed,
        "llm_seed_supported": seed_supported,
    }


# Initialize service identity at import
_capture_service_identity()
