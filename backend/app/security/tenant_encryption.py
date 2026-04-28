"""
================================================================================
INTELLIGENT ANALYST - TENANT ENCRYPTION MODULE (Phase 4)
================================================================================

Implements per-tenant envelope encryption for evidence blobs.

Architecture:
1. Generate random DEK (Data Encryption Key) per blob
2. Encrypt blob with DEK using AES-256-GCM
3. Encrypt DEK with tenant's KMS key (envelope encryption)
4. Store: encrypted_blob, encrypted_dek, nonce, aad, kms_key_id

Decryption:
1. Decrypt DEK using tenant's KMS key
2. Decrypt blob using DEK

Security:
- Each blob has unique DEK and nonce
- AAD (Additional Authenticated Data) binds blob to context
- Tenant isolation via separate KMS keys

Key Caching (v2):
- Tenant KMS keys are cached in memory with TTL
- Key creation is protected by per-tenant locks
- Batch processing resolves key ONCE per batch, not per row

================================================================================
"""

import os
import json
import base64
import hashlib
import secrets
import threading
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple

# Cryptography imports
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False
    print("[TenantEncryption] cryptography not available", flush=True)

# KMS client - lazy loaded
_kms_client = None
_kms_available = False

try:
    from google.cloud import kms
    _kms_available = True
except ImportError:
    _kms_available = False
    print("[TenantEncryption] google-cloud-kms not available", flush=True)


# Configuration
TENANT_ENCRYPTION_ENABLED = os.getenv("TENANT_ENCRYPTION_ENABLED", "false").lower() == "true"
TENANT_KMS_KEYRING = os.getenv("TENANT_KMS_KEYRING", "")
TENANT_KEY_PREFIX = os.getenv("TENANT_KEY_PREFIX", "tenant-")
TENANT_ENCRYPTION_REQUIRED = os.getenv("TENANT_ENCRYPTION_REQUIRED", "false").lower() == "true"
KMS_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "intelligent-analyst-enterprise")
KMS_LOCATION = os.getenv("KMS_LOCATION", "us-central1")

# Encryption constants
DEK_SIZE_BYTES = 32  # AES-256
NONCE_SIZE_BYTES = 12  # GCM standard

class TenantKeyMissingError(Exception):
    """Raised when TENANT_ENCRYPTION_REQUIRED=true and no pre-provisioned key exists."""
    def __init__(self, tenant_id: str, tenant_hash: str):
        self.tenant_id = tenant_id
        self.tenant_hash = tenant_hash
        super().__init__(
            f"No pre-provisioned encryption key for tenant {tenant_id} (hash={tenant_hash}). "
            f"Run eu_provision_tenant_key.sh --tenant-id={tenant_id}"
        )


# ============================================================================
# TENANT KEY CACHING (v2) - Prevents KMS API storms
# ============================================================================

# In-memory cache: tenant_hash -> (key_path, expiry_timestamp)
_tenant_key_cache: Dict[str, Tuple[str, float]] = {}
_tenant_key_cache_lock = threading.Lock()

# Per-tenant creation locks to prevent concurrent creation races
_tenant_creation_locks: Dict[str, threading.Lock] = {}
_creation_locks_lock = threading.Lock()

# Cache TTL (15 minutes)
TENANT_KEY_CACHE_TTL_SECONDS = 15 * 60

# Metrics
_tenant_key_metrics = {
    "cache_hits": 0,
    "cache_misses": 0,
    "creations": 0,
    "creation_failures": 0,
    "already_exists": 0,
}
_metrics_lock = threading.Lock()


def _increment_metric(metric: str) -> None:
    """Thread-safe metric increment."""
    with _metrics_lock:
        _tenant_key_metrics[metric] = _tenant_key_metrics.get(metric, 0) + 1


def get_tenant_key_metrics() -> Dict[str, int]:
    """Get tenant key caching metrics."""
    with _metrics_lock:
        return dict(_tenant_key_metrics)


def _get_tenant_lock(tenant_hash: str) -> threading.Lock:
    """Get or create a lock for a specific tenant."""
    with _creation_locks_lock:
        if tenant_hash not in _tenant_creation_locks:
            _tenant_creation_locks[tenant_hash] = threading.Lock()
        return _tenant_creation_locks[tenant_hash]


def _get_kms_client():
    """Lazy-load KMS client."""
    global _kms_client
    if _kms_client is None and _kms_available:
        _kms_client = kms.KeyManagementServiceClient()
    return _kms_client


def _hash_tenant_id(tenant_id: str) -> str:
    """Hash tenant_id for key naming (privacy + valid key name)."""
    if not tenant_id:
        return "default"
    return hashlib.sha256(tenant_id.encode()).hexdigest()[:16]


def get_or_create_tenant_key(tenant_id: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Get or create KMS key for tenant with caching.

    This function is safe to call multiple times - it will:
    1. Check in-memory cache first (fast path)
    2. If not cached, check KMS API once
    3. If key doesn't exist, create it (with lock to prevent races)
    4. Cache the result with TTL

    Call this ONCE per batch, then pass the key_path to encrypt_evidence_blob().

    Returns: (key_resource_name, error)
    """
    if not _kms_available:
        return None, "kms_not_available"

    if not TENANT_KMS_KEYRING:
        return None, "tenant_keyring_not_configured"

    tenant_hash = _hash_tenant_id(tenant_id)
    current_time = time.time()

    # Fast path: check memory cache
    with _tenant_key_cache_lock:
        if tenant_hash in _tenant_key_cache:
            key_path, expiry = _tenant_key_cache[tenant_hash]
            if current_time < expiry:
                _increment_metric("cache_hits")
                return key_path, None
            # Expired, remove from cache
            del _tenant_key_cache[tenant_hash]

    _increment_metric("cache_misses")

    # Slow path: need to check/create key with per-tenant lock
    tenant_lock = _get_tenant_lock(tenant_hash)

    with tenant_lock:
        # Double-check cache (another thread may have created it)
        with _tenant_key_cache_lock:
            if tenant_hash in _tenant_key_cache:
                key_path, expiry = _tenant_key_cache[tenant_hash]
                if current_time < expiry:
                    _increment_metric("cache_hits")
                    return key_path, None

        # Actually resolve the key
        key_path, error = _resolve_tenant_key_uncached(tenant_id, tenant_hash)

        if key_path and not error:
            # Cache successful result
            with _tenant_key_cache_lock:
                _tenant_key_cache[tenant_hash] = (key_path, current_time + TENANT_KEY_CACHE_TTL_SECONDS)

        return key_path, error


def _resolve_tenant_key_uncached(tenant_id: str, tenant_hash: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Internal: Actually resolve or create tenant key (no caching).
    Called only when cache miss under tenant lock.
    """
    client = _get_kms_client()
    if not client:
        return None, "kms_client_init_failed"

    key_id = f"{TENANT_KEY_PREFIX}{tenant_hash}-v1"

    # Build key path
    keyring_path = f"projects/{KMS_PROJECT}/locations/{KMS_LOCATION}/keyRings/{TENANT_KMS_KEYRING}"
    key_path = f"{keyring_path}/cryptoKeys/{key_id}"

    # Try to get existing key
    try:
        client.get_crypto_key(request={"name": key_path})
        print(f"[TenantEncryption] Using existing KMS key for tenant {tenant_hash}", flush=True)
        return key_path, None
    except Exception as e:
        # Key doesn't exist (404) or other error - try to create
        if "404" not in str(e) and "NOT_FOUND" not in str(e):
            # Unexpected error
            _increment_metric("creation_failures")
            return None, f"key_lookup_failed: {str(e)}"

    # Create new symmetric encryption key for tenant
    try:
        crypto_key = {
            "purpose": kms.CryptoKey.CryptoKeyPurpose.ENCRYPT_DECRYPT,
            "version_template": {
                "algorithm": kms.CryptoKeyVersion.CryptoKeyVersionAlgorithm.GOOGLE_SYMMETRIC_ENCRYPTION,
            },
        }
        created_key = client.create_crypto_key(
            request={
                "parent": keyring_path,
                "crypto_key_id": key_id,
                "crypto_key": crypto_key,
            }
        )
        print(f"[TenantEncryption] Created KMS key for tenant {tenant_hash}: {created_key.name}", flush=True)
        _increment_metric("creations")
        return created_key.name, None

    except Exception as e:
        error_str = str(e)
        # Handle "already exists" as success (race condition)
        if "ALREADY_EXISTS" in error_str or "409" in error_str:
            print(f"[TenantEncryption] Key already exists for tenant {tenant_hash} (concurrent creation)", flush=True)
            _increment_metric("already_exists")
            return key_path, None

        _increment_metric("creation_failures")
        return None, f"key_creation_failed: {error_str}"


def resolve_tenant_key_or_fail(tenant_id: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Resolve tenant KMS key with fail-closed behavior when required.

    When TENANT_ENCRYPTION_REQUIRED=true:
        - Only looks up existing (pre-provisioned) keys, never creates.
        - Raises TenantKeyMissingError if the key does not exist.
    When TENANT_ENCRYPTION_REQUIRED=false:
        - Delegates to get_or_create_tenant_key() (existing behavior).

    Returns: (key_resource_name, error)
    Raises: TenantKeyMissingError when required=true and key is missing.
    """
    if not TENANT_ENCRYPTION_REQUIRED:
        return get_or_create_tenant_key(tenant_id)

    # Fail-closed path: lookup only, never create
    if not _kms_available:
        return None, "kms_not_available"

    if not TENANT_KMS_KEYRING:
        return None, "tenant_keyring_not_configured"

    tenant_hash = _hash_tenant_id(tenant_id)
    current_time = time.time()

    # Check cache first
    with _tenant_key_cache_lock:
        if tenant_hash in _tenant_key_cache:
            key_path, expiry = _tenant_key_cache[tenant_hash]
            if current_time < expiry:
                _increment_metric("cache_hits")
                return key_path, None
            del _tenant_key_cache[tenant_hash]

    _increment_metric("cache_misses")

    # Lookup only (no creation)
    client = _get_kms_client()
    if not client:
        return None, "kms_client_init_failed"

    key_id = f"{TENANT_KEY_PREFIX}{tenant_hash}-v1"
    keyring_path = f"projects/{KMS_PROJECT}/locations/{KMS_LOCATION}/keyRings/{TENANT_KMS_KEYRING}"
    key_path = f"{keyring_path}/cryptoKeys/{key_id}"

    try:
        client.get_crypto_key(request={"name": key_path})
        # Cache the result
        with _tenant_key_cache_lock:
            _tenant_key_cache[tenant_hash] = (key_path, current_time + TENANT_KEY_CACHE_TTL_SECONDS)
        print(f"[TenantEncryption] REQUIRED mode: found pre-provisioned key for tenant {tenant_hash}", flush=True)
        return key_path, None
    except Exception as e:
        if "404" in str(e) or "NOT_FOUND" in str(e):
            raise TenantKeyMissingError(tenant_id, tenant_hash)
        return None, f"key_lookup_failed: {str(e)}"


# Keep old name as alias for backwards compatibility
_get_or_create_tenant_key = get_or_create_tenant_key


def encrypt_evidence_blob(
    evidence_blob: Dict[str, Any],
    tenant_id: str,
    trace_id: str,
    batch_id: str,
    kms_key_path: Optional[str] = None  # Pre-resolved key path (recommended for batch ops)
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Encrypt evidence blob using envelope encryption.

    Args:
        evidence_blob: The evidence data to encrypt
        tenant_id: Tenant identifier
        trace_id: Unique trace ID for this record
        batch_id: Batch identifier
        kms_key_path: Optional pre-resolved KMS key path. If provided, skips key lookup.
                      Use get_or_create_tenant_key() once per batch and pass result here.

    Returns:
        (encrypted_package, error)
        encrypted_package contains: encrypted_blob, encrypted_dek, nonce, aad, kms_key_id
    """
    if not TENANT_ENCRYPTION_ENABLED:
        return None, "tenant_encryption_disabled"

    if not HAS_CRYPTO:
        return None, "cryptography_not_available"

    if not _kms_available:
        return None, "kms_not_available"

    # Use pre-resolved key if provided, otherwise resolve (with caching)
    if kms_key_path:
        key_path = kms_key_path
    else:
        key_path, key_error = get_or_create_tenant_key(tenant_id)
        if key_error:
            return None, f"tenant_key_error: {key_error}"

    client = _get_kms_client()

    try:
        # 1. Generate random DEK
        dek = secrets.token_bytes(DEK_SIZE_BYTES)

        # 2. Generate random nonce
        nonce = secrets.token_bytes(NONCE_SIZE_BYTES)

        # 3. Build AAD (Additional Authenticated Data)
        aad = f"{trace_id}:{tenant_id}:{batch_id}".encode('utf-8')

        # 4. Serialize evidence blob to JSON
        plaintext = json.dumps(evidence_blob, separators=(',', ':'), sort_keys=True).encode('utf-8')

        # 5. Encrypt blob with DEK using AES-256-GCM
        aesgcm = AESGCM(dek)
        encrypted_blob = aesgcm.encrypt(nonce, plaintext, aad)

        # 6. Encrypt DEK with KMS (envelope encryption)
        encrypt_response = client.encrypt(
            request={
                "name": f"{key_path}/cryptoKeyVersions/1",
                "plaintext": dek,
            }
        )
        encrypted_dek = encrypt_response.ciphertext

        # 7. Build encrypted package
        encrypted_package = {
            "encrypted_blob": base64.b64encode(encrypted_blob).decode('ascii'),
            "encrypted_dek": base64.b64encode(encrypted_dek).decode('ascii'),
            "nonce": base64.b64encode(nonce).decode('ascii'),
            "aad": base64.b64encode(aad).decode('ascii'),
            "kms_key_id": key_path,
            "enc_alg": "AES-256-GCM",
            "envelope_alg": "GOOGLE_SYMMETRIC_ENCRYPTION",
            "encrypted_at": datetime.now(timezone.utc).isoformat(),
            "tenant_id_hash": _hash_tenant_id(tenant_id),
        }

        return encrypted_package, None

    except Exception as e:
        return None, f"encryption_failed: {str(e)}"


def decrypt_evidence_blob(
    encrypted_package: Dict[str, Any],
    tenant_id: str,
    trace_id: str,
    batch_id: str
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Decrypt evidence blob.

    Returns:
        (evidence_blob, error)
    """
    if not HAS_CRYPTO:
        return None, "cryptography_not_available"

    if not _kms_available:
        return None, "kms_not_available"

    client = _get_kms_client()

    try:
        # 1. Extract components
        encrypted_blob = base64.b64decode(encrypted_package["encrypted_blob"])
        encrypted_dek = base64.b64decode(encrypted_package["encrypted_dek"])
        nonce = base64.b64decode(encrypted_package["nonce"])
        stored_aad = base64.b64decode(encrypted_package["aad"])
        kms_key_id = encrypted_package["kms_key_id"]

        # 2. Verify AAD matches context
        expected_aad = f"{trace_id}:{tenant_id}:{batch_id}".encode('utf-8')
        if stored_aad != expected_aad:
            return None, "aad_mismatch"

        # 3. Verify tenant has access to this key
        stored_tenant_hash = encrypted_package.get("tenant_id_hash")
        if stored_tenant_hash != _hash_tenant_id(tenant_id):
            return None, "tenant_mismatch"

        # 4. Decrypt DEK with KMS
        decrypt_response = client.decrypt(
            request={
                "name": kms_key_id,
                "ciphertext": encrypted_dek,
            }
        )
        dek = decrypt_response.plaintext

        # 5. Decrypt blob with DEK
        aesgcm = AESGCM(dek)
        plaintext = aesgcm.decrypt(nonce, encrypted_blob, stored_aad)

        # 6. Parse JSON
        evidence_blob = json.loads(plaintext.decode('utf-8'))

        return evidence_blob, None

    except Exception as e:
        return None, f"decryption_failed: {str(e)}"


def get_tenant_encryption_status() -> Dict[str, Any]:
    """Get tenant encryption status for /health endpoint."""
    return {
        "enabled": TENANT_ENCRYPTION_ENABLED,
        "required": TENANT_ENCRYPTION_REQUIRED,
        "kms_available": _kms_available,
        "crypto_available": HAS_CRYPTO,
        "keyring": TENANT_KMS_KEYRING if TENANT_ENCRYPTION_ENABLED else None,
        "key_prefix": TENANT_KEY_PREFIX if TENANT_ENCRYPTION_ENABLED else None,
        "key_cache_ttl_seconds": TENANT_KEY_CACHE_TTL_SECONDS,
        "key_metrics": get_tenant_key_metrics(),
    }
