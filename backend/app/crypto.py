"""
================================================================================
INTELLIGENT ANALYST - CRYPTO MODULE FOR MANIFEST SIGNING
================================================================================

Provides RSA-based signing for Evidence Pack manifests.
- Generates or loads RSA 2048-bit key pair
- Signs manifest JSON with SHA-256
- Returns base64-encoded signature

Key loading priority:
1. IA_MANIFEST_PRIVATE_KEY env var (PEM format, base64-encoded)
2. Local file: manifest_key.pem (dev only)
3. Auto-generate ephemeral key (dev only, warns)

================================================================================
"""

import os
import base64
import hashlib
from typing import Tuple, Optional

# Use cryptography library (already available via other deps)
try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa, padding
    from cryptography.hazmat.backends import default_backend
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

_private_key = None
_public_key_pem = None
_key_source = None


def _generate_key_pair() -> Tuple[any, bytes]:
    """Generate a new RSA 2048-bit key pair."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )
    public_key_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return private_key, public_key_pem


def _load_private_key_from_pem(pem_data: bytes) -> any:
    """Load private key from PEM bytes."""
    return serialization.load_pem_private_key(
        pem_data,
        password=None,
        backend=default_backend()
    )


def init_signing_keys() -> bool:
    """
    Initialize signing keys from environment or file.
    Returns True if keys are available.
    """
    global _private_key, _public_key_pem, _key_source

    if not HAS_CRYPTO:
        print("[Crypto] cryptography library not available", flush=True)
        return False

    # Priority 1: Environment variable (base64-encoded PEM)
    env_key = os.getenv("IA_MANIFEST_PRIVATE_KEY")
    if env_key:
        try:
            pem_bytes = base64.b64decode(env_key)
            _private_key = _load_private_key_from_pem(pem_bytes)
            _public_key_pem = _private_key.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )
            _key_source = "env"
            print("[Crypto] Loaded signing key from IA_MANIFEST_PRIVATE_KEY", flush=True)
            return True
        except Exception as e:
            print(f"[Crypto] Failed to load key from env: {e}", flush=True)

    # Priority 2: Local file (dev only)
    key_file = os.path.join(os.path.dirname(__file__), "manifest_key.pem")
    if os.path.exists(key_file):
        try:
            with open(key_file, "rb") as f:
                pem_bytes = f.read()
            _private_key = _load_private_key_from_pem(pem_bytes)
            _public_key_pem = _private_key.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )
            _key_source = "file"
            print(f"[Crypto] Loaded signing key from {key_file}", flush=True)
            return True
        except Exception as e:
            print(f"[Crypto] Failed to load key from file: {e}", flush=True)

    # Priority 3: Generate ephemeral key (dev only)
    try:
        print("[Crypto] WARNING: Generating ephemeral signing key (dev only)", flush=True)
        _private_key, _public_key_pem = _generate_key_pair()
        _key_source = "ephemeral"
        return True
    except Exception as e:
        print(f"[Crypto] Failed to generate ephemeral key: {e}", flush=True)
        return False


def sign_manifest(manifest_json_bytes: bytes) -> Optional[str]:
    """
    Sign manifest JSON bytes using RSA-SHA256.
    Returns base64-encoded signature, or None if signing unavailable.
    """
    global _private_key

    if _private_key is None:
        if not init_signing_keys():
            return None

    if _private_key is None:
        return None

    try:
        signature = _private_key.sign(
            manifest_json_bytes,
            padding.PKCS1v15(),
            hashes.SHA256()
        )
        return base64.b64encode(signature).decode('ascii')
    except Exception as e:
        print(f"[Crypto] Signing failed: {e}", flush=True)
        return None


def get_public_key_pem() -> Optional[str]:
    """
    Get the public key in PEM format.
    Returns None if keys not initialized.
    """
    global _public_key_pem

    if _public_key_pem is None:
        if not init_signing_keys():
            return None

    if _public_key_pem is None:
        return None

    return _public_key_pem.decode('utf-8')


def get_key_source() -> Optional[str]:
    """Get the source of the current signing key."""
    return _key_source


def is_signing_available() -> bool:
    """Check if manifest signing is available."""
    if not HAS_CRYPTO:
        return False
    if _private_key is None:
        init_signing_keys()
    return _private_key is not None
