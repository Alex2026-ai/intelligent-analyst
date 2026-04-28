"""
================================================================================
INTELLIGENT ANALYST - SBOM (Software Bill of Materials) MODULE (Phase 0.5)
================================================================================

Computes and caches SBOM hash from locked dependency manifests.
- Hashes requirements.txt + any lock files
- Captures container image digest if available
- Exposes sbom_hash_sha256 for evidence blobs

================================================================================
"""

import os
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime, timezone

# Cached SBOM data (computed once at startup)
_sbom_data: Dict[str, Any] = {}
_sbom_computed = False


def _compute_file_hash(filepath: Path) -> Optional[str]:
    """Compute SHA-256 hash of a file."""
    if not filepath.exists():
        return None
    try:
        h = hashlib.sha256()
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                h.update(chunk)
        return h.hexdigest()
    except Exception as e:
        print(f"[SBOM] Error hashing {filepath}: {e}", flush=True)
        return None


def _find_app_root() -> Path:
    """Find the application root directory."""
    # Start from this file's directory and go up
    current = Path(__file__).resolve().parent

    # Look for requirements.txt going up the tree
    for _ in range(5):
        if (current / "requirements.txt").exists():
            return current
        current = current.parent

    # Fallback to backend directory
    return Path(__file__).resolve().parent.parent.parent


def compute_sbom_hash() -> Dict[str, Any]:
    """
    Compute SBOM hash from dependency manifests.

    Hashes (in order of priority):
    1. requirements.txt
    2. requirements.lock (if exists)
    3. poetry.lock (if exists)
    4. Pipfile.lock (if exists)

    Returns combined hash of all found manifests.
    """
    global _sbom_data, _sbom_computed

    if _sbom_computed:
        return _sbom_data

    app_root = _find_app_root()
    manifest_hashes = []
    manifest_files = []

    # Check various dependency files
    dependency_files = [
        "requirements.txt",
        "requirements.lock",
        "poetry.lock",
        "Pipfile.lock",
    ]

    for filename in dependency_files:
        filepath = app_root / filename
        file_hash = _compute_file_hash(filepath)
        if file_hash:
            manifest_hashes.append(file_hash)
            manifest_files.append(filename)
            print(f"[SBOM] Hashed {filename}: {file_hash[:16]}...", flush=True)

    # Combine all hashes into single SBOM hash
    if manifest_hashes:
        combined = ":".join(sorted(manifest_hashes))
        sbom_hash = hashlib.sha256(combined.encode()).hexdigest()
    else:
        sbom_hash = None
        print("[SBOM] Warning: No dependency manifests found", flush=True)

    # Get container image digest if available
    image_digest = os.getenv("IMAGE_DIGEST", None)

    # K_REVISION contains the Cloud Run revision name
    revision = os.getenv("K_REVISION", "local")

    _sbom_data = {
        "sbom_hash_sha256": sbom_hash,
        "manifest_files": manifest_files,
        "manifest_count": len(manifest_files),
        "image_digest": image_digest,
        "revision": revision,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }

    _sbom_computed = True
    print(f"[SBOM] Computed SBOM hash: {sbom_hash[:16] if sbom_hash else 'None'}...", flush=True)

    return _sbom_data


def get_sbom_hash() -> Optional[str]:
    """Get the computed SBOM hash."""
    data = compute_sbom_hash()
    return data.get("sbom_hash_sha256")


def get_sbom_status() -> Dict[str, Any]:
    """Get SBOM status for /health endpoint."""
    return compute_sbom_hash()


def get_sbom_for_evidence() -> Dict[str, Any]:
    """Get SBOM data formatted for evidence blob inclusion."""
    data = compute_sbom_hash()
    return {
        "sbom_hash_sha256": data.get("sbom_hash_sha256"),
        "image_digest": data.get("image_digest"),
        "manifest_count": data.get("manifest_count"),
    }


# Compute SBOM at import time
compute_sbom_hash()
