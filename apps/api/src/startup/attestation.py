"""Release attestation — validates build integrity on startup.

Verifies:
- Release manifest checksums match running code
- SBOM present
- Build metadata present
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AttestationResult:
    """Result of attestation validation."""
    valid: bool
    checks: dict[str, bool] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


def compute_file_checksum(filepath: str) -> str | None:
    """Compute SHA-256 checksum of a file."""
    try:
        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except FileNotFoundError:
        return None


def validate_attestation(
    manifest: dict[str, Any] | None = None,
    base_path: str = ".",
) -> AttestationResult:
    """Validate release attestation on startup.

    Args:
        manifest: Release manifest with expected checksums.
        base_path: Base path for file lookups.

    Returns:
        AttestationResult with validation details.
    """
    checks: dict[str, bool] = {}
    errors: list[str] = []

    # Check 1: Manifest present
    if manifest is None:
        checks["manifest_present"] = False
        errors.append("Release manifest not provided")
        return AttestationResult(valid=False, checks=checks, errors=errors)

    checks["manifest_present"] = True

    # Check 2: Build metadata
    build_sha = manifest.get("git_commit_sha")
    checks["build_metadata"] = build_sha is not None
    if not build_sha:
        errors.append("Missing git_commit_sha in manifest")

    # Check 3: SBOM reference
    sbom_ref = manifest.get("sbom_hash")
    checks["sbom_present"] = sbom_ref is not None
    if not sbom_ref:
        errors.append("Missing sbom_hash in manifest")

    # Check 4: Critical file checksums
    checksums = manifest.get("file_checksums", {})
    for filepath, expected_hash in checksums.items():
        full_path = os.path.join(base_path, filepath)
        actual = compute_file_checksum(full_path)
        if actual is None:
            checks[f"checksum_{filepath}"] = False
            errors.append(f"Critical file not found: {filepath}")
        elif actual != expected_hash:
            checks[f"checksum_{filepath}"] = False
            errors.append(f"Checksum mismatch for {filepath}: expected {expected_hash}, got {actual}")
        else:
            checks[f"checksum_{filepath}"] = True

    valid = len(errors) == 0
    return AttestationResult(valid=valid, checks=checks, errors=errors)
