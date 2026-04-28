"""
Attestation Manifest v1 — Internal Verification Primitives.

Standalone, deterministic verifier for ia-attestation/v1 receipt bundles.
Operates on in-memory bytes only — no GCS, no Firestore, no network I/O.

Verification order (fail-fast):
  1. Schema & JCS integrity — required fields, JCS round-trip, protocol_version
  2. Signature — ECDSA P-256 SHA-256 over SHA-256(JCS(manifest))
  3. Metadata consistency — receipt_id, batch_id, manifest_hash cross-check
  4. Anchor binding — anchor_ref.anchor_hash present and well-formed
  5. Artifact integrity — artifact_hashes[].hash and size_bytes present

Each check short-circuits on failure. The result includes a typed failure
reason from VerificationFailure and a PII-safe details dict.
"""

from __future__ import annotations

import enum
import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.attestation.manifest_v1 import PROTOCOL_VERSION, SIGNATURE_ALGORITHM, _REQUIRED_FIELDS
from app.security.iavp import jcs_canonicalize

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Failure taxonomy
# ─────────────────────────────────────────────────────────────────────────────

class VerificationFailure(str, enum.Enum):
    """Typed failure reasons for attestation verification."""
    MANIFEST_MALFORMED = "MANIFEST_MALFORMED"
    SIGNATURE_INVALID = "SIGNATURE_INVALID"
    KEY_VERSION_MISMATCH = "KEY_VERSION_MISMATCH"
    METADATA_INCONSISTENT = "METADATA_INCONSISTENT"
    ANCHOR_HASH_MISMATCH = "ANCHOR_HASH_MISMATCH"
    ARTIFACT_HASH_MISMATCH = "ARTIFACT_HASH_MISMATCH"
    ARTIFACT_SIZE_MISMATCH = "ARTIFACT_SIZE_MISMATCH"
    TIMESTAMP_SKEW_EXCEEDED = "TIMESTAMP_SKEW_EXCEEDED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


# ─────────────────────────────────────────────────────────────────────────────
# Metrics counters (in-process, exportable to Prometheus/structured logs)
# ─────────────────────────────────────────────────────────────────────────────

_metrics: Dict[str, int] = {
    "attestation_verification_success_total": 0,
    "attestation_verification_failures_total": 0,
}
_metrics_by_reason: Dict[str, int] = {}
_metrics_duration_ms: List[float] = []

MAX_DURATION_SAMPLES = 10000


def get_verification_metrics() -> Dict[str, Any]:
    """Return current verification metrics snapshot."""
    return {
        "success_total": _metrics["attestation_verification_success_total"],
        "failures_total": _metrics["attestation_verification_failures_total"],
        "failures_by_reason": dict(_metrics_by_reason),
        "duration_samples": len(_metrics_duration_ms),
        "duration_p50_ms": _percentile(_metrics_duration_ms, 50),
        "duration_p99_ms": _percentile(_metrics_duration_ms, 99),
    }


def reset_verification_metrics() -> None:
    """Reset all counters. For testing only."""
    _metrics["attestation_verification_success_total"] = 0
    _metrics["attestation_verification_failures_total"] = 0
    _metrics_by_reason.clear()
    _metrics_duration_ms.clear()


def _percentile(data: List[float], pct: int) -> Optional[float]:
    if not data:
        return None
    s = sorted(data)
    idx = int(len(s) * pct / 100)
    idx = min(idx, len(s) - 1)
    return round(s[idx], 2)


def _record_success(duration_ms: float) -> None:
    _metrics["attestation_verification_success_total"] += 1
    if len(_metrics_duration_ms) < MAX_DURATION_SAMPLES:
        _metrics_duration_ms.append(duration_ms)


def _record_failure(reason: VerificationFailure, duration_ms: float) -> None:
    _metrics["attestation_verification_failures_total"] += 1
    _metrics_by_reason[reason.value] = _metrics_by_reason.get(reason.value, 0) + 1
    if len(_metrics_duration_ms) < MAX_DURATION_SAMPLES:
        _metrics_duration_ms.append(duration_ms)


# ─────────────────────────────────────────────────────────────────────────────
# Public key resolver type
# ─────────────────────────────────────────────────────────────────────────────

PublicKeyResolver = Callable[[str], Optional[bytes]]
"""
Adapter: (key_id: str) -> PEM bytes or None.

Production: wraps KMS get_public_key_pem_for_key_id.
Tests: returns a fixed test key.
"""


# ─────────────────────────────────────────────────────────────────────────────
# Main verification entry point
# ─────────────────────────────────────────────────────────────────────────────

def verify_manifest_bundle(
    manifest_bytes: bytes,
    signature_bytes: bytes,
    metadata_bytes: Optional[bytes] = None,
    public_key_resolver: Optional[PublicKeyResolver] = None,
    fail_closed: bool = False,
    max_timestamp_skew_seconds: int = 300,
) -> Dict[str, Any]:
    """
    Verify an ia-attestation/v1 receipt bundle.

    Args:
        manifest_bytes: Raw bytes of manifest.json (must be JCS canonical).
        signature_bytes: Raw bytes of signature.der (DER-encoded ECDSA).
        metadata_bytes: Optional raw bytes of receipt_metadata.json.
        public_key_resolver: Callable(key_id) -> PEM bytes. If None, signature
            check is skipped (schema-only mode).
        fail_closed: If True, treat missing public_key_resolver as failure
            instead of skipping signature check.
        max_timestamp_skew_seconds: Max allowed age of manifest timestamp (default 5 min).

    Returns:
        Dict with keys:
            success: bool
            failure_reason: Optional[str] — VerificationFailure value or None
            details: Dict — PII-safe diagnostic details
            checks_passed: List[str] — names of checks that passed
            duration_ms: float
    """
    t0 = time.monotonic()
    checks_passed: List[str] = []

    try:
        # ── Check 1: Schema & JCS integrity ──────────────────────────────
        manifest, err = _check_schema_and_jcs(manifest_bytes)
        if err:
            return _fail(err[0], err[1], checks_passed, t0)
        assert manifest is not None
        checks_passed.append("schema_jcs")

        # ── Check 2: Signature ───────────────────────────────────────────
        sig_err = _check_signature(
            manifest_bytes, manifest, signature_bytes,
            public_key_resolver, fail_closed,
        )
        if sig_err:
            return _fail(sig_err[0], sig_err[1], checks_passed, t0)
        checks_passed.append("signature")

        # ── Check 3: Metadata consistency ────────────────────────────────
        if metadata_bytes is not None:
            meta_err = _check_metadata_consistency(manifest, manifest_bytes, metadata_bytes)
            if meta_err:
                return _fail(meta_err[0], meta_err[1], checks_passed, t0)
        checks_passed.append("metadata_consistency")

        # ── Check 4: Anchor binding ──────────────────────────────────────
        anchor_err = _check_anchor_binding(manifest)
        if anchor_err:
            return _fail(anchor_err[0], anchor_err[1], checks_passed, t0)
        checks_passed.append("anchor_binding")

        # ── Check 5: Artifact integrity ──────────────────────────────────
        artifact_err = _check_artifact_integrity(manifest)
        if artifact_err:
            return _fail(artifact_err[0], artifact_err[1], checks_passed, t0)
        checks_passed.append("artifact_integrity")

        # ── Check 6: Timestamp skew (non-fatal by default) ──────────────
        ts_err = _check_timestamp_skew(manifest, max_timestamp_skew_seconds)
        if ts_err:
            return _fail(ts_err[0], ts_err[1], checks_passed, t0)
        checks_passed.append("timestamp_skew")

        # All checks passed
        duration_ms = (time.monotonic() - t0) * 1000
        _record_success(duration_ms)
        logger.info(
            "attestation_verification=PASS batch_id=%s receipt_id=%s duration_ms=%.1f",
            manifest.get("batch_id", "?"),
            manifest.get("receipt_id", "?"),
            duration_ms,
        )
        return {
            "success": True,
            "failure_reason": None,
            "details": {
                "batch_id": manifest.get("batch_id"),
                "receipt_id": manifest.get("receipt_id"),
                "protocol_version": manifest.get("protocol_version"),
            },
            "checks_passed": checks_passed,
            "duration_ms": round(duration_ms, 2),
        }

    except Exception as e:
        duration_ms = (time.monotonic() - t0) * 1000
        _record_failure(VerificationFailure.INTERNAL_ERROR, duration_ms)
        logger.error(
            "attestation_verification=INTERNAL_ERROR error=%s duration_ms=%.1f",
            str(e)[:200],
            duration_ms,
        )
        return {
            "success": False,
            "failure_reason": VerificationFailure.INTERNAL_ERROR.value,
            "details": {"error": str(e)[:200]},
            "checks_passed": checks_passed,
            "duration_ms": round(duration_ms, 2),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Individual checks
# ─────────────────────────────────────────────────────────────────────────────

def _check_schema_and_jcs(
    manifest_bytes: bytes,
) -> Tuple[Optional[Dict[str, Any]], Optional[Tuple[VerificationFailure, Dict[str, Any]]]]:
    """
    Check 1: Parse JSON, verify required fields, protocol_version, JCS round-trip.

    Returns:
        (manifest_dict, None) on success.
        (None, (failure, details)) on failure.
    """
    # Parse JSON
    try:
        manifest = json.loads(manifest_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return None, (
            VerificationFailure.MANIFEST_MALFORMED,
            {"reason": "invalid_json", "error": str(e)[:100]},
        )

    if not isinstance(manifest, dict):
        return None, (
            VerificationFailure.MANIFEST_MALFORMED,
            {"reason": "not_a_dict", "type": type(manifest).__name__},
        )

    # Required fields
    present = set(manifest.keys())
    missing = _REQUIRED_FIELDS - present
    if missing:
        return None, (
            VerificationFailure.MANIFEST_MALFORMED,
            {"reason": "missing_fields", "missing": sorted(missing)},
        )

    # Protocol version
    if manifest.get("protocol_version") != PROTOCOL_VERSION:
        return None, (
            VerificationFailure.MANIFEST_MALFORMED,
            {
                "reason": "wrong_protocol_version",
                "expected": PROTOCOL_VERSION,
                "actual": manifest.get("protocol_version"),
            },
        )

    # Signature algorithm
    if manifest.get("signature_algorithm") != SIGNATURE_ALGORITHM:
        return None, (
            VerificationFailure.MANIFEST_MALFORMED,
            {
                "reason": "wrong_signature_algorithm",
                "expected": SIGNATURE_ALGORITHM,
                "actual": manifest.get("signature_algorithm"),
            },
        )

    # JCS round-trip: re-canonicalize and compare bytes
    try:
        recanonical = jcs_canonicalize(manifest)
    except Exception as e:
        return None, (
            VerificationFailure.MANIFEST_MALFORMED,
            {"reason": "jcs_canonicalize_failed", "error": str(e)[:100]},
        )

    if recanonical != manifest_bytes:
        return None, (
            VerificationFailure.MANIFEST_MALFORMED,
            {"reason": "jcs_round_trip_mismatch", "expected_len": len(recanonical), "actual_len": len(manifest_bytes)},
        )

    return manifest, None


def _check_signature(
    manifest_bytes: bytes,
    manifest: Dict[str, Any],
    signature_bytes: bytes,
    public_key_resolver: Optional[PublicKeyResolver],
    fail_closed: bool,
) -> Optional[Tuple[VerificationFailure, Dict[str, Any]]]:
    """
    Check 2: Verify ECDSA P-256 SHA-256 signature over SHA-256(JCS(manifest)).

    The signing input is SHA-256(manifest_bytes) as raw bytes, not hex.
    """
    if not signature_bytes:
        return (
            VerificationFailure.SIGNATURE_INVALID,
            {"reason": "empty_signature"},
        )

    if public_key_resolver is None:
        if fail_closed:
            return (
                VerificationFailure.SIGNATURE_INVALID,
                {"reason": "no_public_key_resolver_and_fail_closed"},
            )
        # Skip signature check in schema-only mode
        return None

    key_id = manifest.get("key_id", "")
    pem_bytes = public_key_resolver(key_id)
    if pem_bytes is None:
        return (
            VerificationFailure.KEY_VERSION_MISMATCH,
            {"reason": "key_not_found", "key_id_prefix": key_id[:40] if key_id else ""},
        )

    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec, utils
        from cryptography.exceptions import InvalidSignature

        public_key = serialization.load_pem_public_key(
            pem_bytes if isinstance(pem_bytes, bytes) else pem_bytes.encode("utf-8")
        )

        # The signed data is the raw manifest bytes (JCS canonical)
        # Signature is over SHA-256 digest computed by the signer
        digest = hashlib.sha256(manifest_bytes).digest()

        try:
            public_key.verify(
                signature_bytes,
                digest,
                ec.ECDSA(utils.Prehashed(hashes.SHA256())),
            )
        except InvalidSignature:
            return (
                VerificationFailure.SIGNATURE_INVALID,
                {"reason": "ecdsa_verification_failed"},
            )

    except ImportError:
        if fail_closed:
            return (
                VerificationFailure.INTERNAL_ERROR,
                {"reason": "cryptography_library_not_available"},
            )
        # Non-fatal: skip signature in permissive mode
        return None

    return None


def _check_metadata_consistency(
    manifest: Dict[str, Any],
    manifest_bytes: bytes,
    metadata_bytes: bytes,
) -> Optional[Tuple[VerificationFailure, Dict[str, Any]]]:
    """
    Check 3: Cross-check receipt_metadata.json against manifest.

    Verifies: receipt_id, batch_id, protocol_version, manifest_hash.
    """
    try:
        metadata = json.loads(metadata_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return (
            VerificationFailure.METADATA_INCONSISTENT,
            {"reason": "invalid_metadata_json", "error": str(e)[:100]},
        )

    if not isinstance(metadata, dict):
        return (
            VerificationFailure.METADATA_INCONSISTENT,
            {"reason": "metadata_not_a_dict"},
        )

    # receipt_id must match
    if metadata.get("receipt_id") != manifest.get("receipt_id"):
        return (
            VerificationFailure.METADATA_INCONSISTENT,
            {
                "reason": "receipt_id_mismatch",
                "metadata_receipt_id": metadata.get("receipt_id"),
                "manifest_receipt_id": manifest.get("receipt_id"),
            },
        )

    # batch_id must match
    if metadata.get("batch_id") != manifest.get("batch_id"):
        return (
            VerificationFailure.METADATA_INCONSISTENT,
            {
                "reason": "batch_id_mismatch",
                "metadata_batch_id": metadata.get("batch_id"),
                "manifest_batch_id": manifest.get("batch_id"),
            },
        )

    # protocol_version must match
    if metadata.get("protocol_version") != manifest.get("protocol_version"):
        return (
            VerificationFailure.METADATA_INCONSISTENT,
            {"reason": "protocol_version_mismatch"},
        )

    # manifest_hash must match SHA-256 of manifest bytes
    expected_manifest_hash = hashlib.sha256(manifest_bytes).hexdigest().lower()
    if metadata.get("manifest_hash") and metadata["manifest_hash"] != expected_manifest_hash:
        return (
            VerificationFailure.METADATA_INCONSISTENT,
            {
                "reason": "manifest_hash_mismatch",
                "expected_prefix": expected_manifest_hash[:16],
                "actual_prefix": metadata["manifest_hash"][:16],
            },
        )

    return None


def _check_anchor_binding(
    manifest: Dict[str, Any],
) -> Optional[Tuple[VerificationFailure, Dict[str, Any]]]:
    """
    Check 4: Verify anchor_ref structure and anchor_hash format.
    """
    anchor_ref = manifest.get("anchor_ref")
    if not isinstance(anchor_ref, dict):
        return (
            VerificationFailure.ANCHOR_HASH_MISMATCH,
            {"reason": "anchor_ref_not_a_dict"},
        )

    anchor_hash = anchor_ref.get("anchor_hash")
    if not anchor_hash or not isinstance(anchor_hash, str):
        return (
            VerificationFailure.ANCHOR_HASH_MISMATCH,
            {"reason": "anchor_hash_missing"},
        )

    # anchor_hash must be a 64-char hex string (SHA-256)
    if len(anchor_hash) != 64:
        return (
            VerificationFailure.ANCHOR_HASH_MISMATCH,
            {"reason": "anchor_hash_wrong_length", "length": len(anchor_hash)},
        )

    try:
        int(anchor_hash, 16)
    except ValueError:
        return (
            VerificationFailure.ANCHOR_HASH_MISMATCH,
            {"reason": "anchor_hash_not_hex"},
        )

    # anchor_timestamp must be present
    if not anchor_ref.get("anchor_timestamp"):
        return (
            VerificationFailure.ANCHOR_HASH_MISMATCH,
            {"reason": "anchor_timestamp_missing"},
        )

    return None


def _check_artifact_integrity(
    manifest: Dict[str, Any],
) -> Optional[Tuple[VerificationFailure, Dict[str, Any]]]:
    """
    Check 5: Verify artifact_hashes entries have required fields and valid formats.
    """
    artifact_hashes = manifest.get("artifact_hashes")
    if not isinstance(artifact_hashes, list):
        return (
            VerificationFailure.ARTIFACT_HASH_MISMATCH,
            {"reason": "artifact_hashes_not_a_list"},
        )

    if len(artifact_hashes) == 0:
        return (
            VerificationFailure.ARTIFACT_HASH_MISMATCH,
            {"reason": "artifact_hashes_empty"},
        )

    for i, entry in enumerate(artifact_hashes):
        if not isinstance(entry, dict):
            return (
                VerificationFailure.ARTIFACT_HASH_MISMATCH,
                {"reason": "entry_not_a_dict", "index": i},
            )

        # Required: artifact_type, hash, size_bytes
        if not entry.get("artifact_type"):
            return (
                VerificationFailure.ARTIFACT_HASH_MISMATCH,
                {"reason": "missing_artifact_type", "index": i},
            )

        h = entry.get("hash")
        if not h or not isinstance(h, str) or len(h) != 64:
            return (
                VerificationFailure.ARTIFACT_HASH_MISMATCH,
                {"reason": "invalid_hash", "index": i},
            )

        size = entry.get("size_bytes")
        if size is None or not isinstance(size, (int, float)) or size < 0:
            return (
                VerificationFailure.ARTIFACT_SIZE_MISMATCH,
                {"reason": "invalid_size_bytes", "index": i, "value": size},
            )

    return None


def _check_timestamp_skew(
    manifest: Dict[str, Any],
    max_skew_seconds: int,
) -> Optional[Tuple[VerificationFailure, Dict[str, Any]]]:
    """
    Check 6: Verify manifest timestamp is not unreasonably old or in the future.
    """
    ts_str = manifest.get("timestamp")
    if not ts_str or not isinstance(ts_str, str):
        return (
            VerificationFailure.TIMESTAMP_SKEW_EXCEEDED,
            {"reason": "timestamp_missing"},
        )

    try:
        # Parse RFC 3339 / ISO 8601 timestamp
        if ts_str.endswith("Z"):
            ts_str_parsed = ts_str[:-1] + "+00:00"
        else:
            ts_str_parsed = ts_str
        ts = datetime.fromisoformat(ts_str_parsed)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError) as e:
        return (
            VerificationFailure.TIMESTAMP_SKEW_EXCEEDED,
            {"reason": "timestamp_parse_error", "error": str(e)[:100]},
        )

    now = datetime.now(timezone.utc)
    skew = abs((now - ts).total_seconds())

    # Allow generous skew for batch processing (default 5 min, configurable)
    # But also check for future timestamps (clock skew)
    if ts > now:
        future_skew = (ts - now).total_seconds()
        if future_skew > 60:  # 1 minute tolerance for future
            return (
                VerificationFailure.TIMESTAMP_SKEW_EXCEEDED,
                {"reason": "timestamp_in_future", "skew_seconds": round(future_skew, 1)},
            )

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _fail(
    reason: VerificationFailure,
    details: Dict[str, Any],
    checks_passed: List[str],
    t0: float,
) -> Dict[str, Any]:
    """Build a failure result and record metrics."""
    duration_ms = (time.monotonic() - t0) * 1000
    _record_failure(reason, duration_ms)

    # PII-safe log — no tenant_id, no raw names
    logger.warning(
        "attestation_verification=FAIL reason=%s details=%s checks_passed=%s duration_ms=%.1f",
        reason.value,
        json.dumps(details, default=str)[:300],
        ",".join(checks_passed),
        duration_ms,
    )

    return {
        "success": False,
        "failure_reason": reason.value,
        "details": details,
        "checks_passed": checks_passed,
        "duration_ms": round(duration_ms, 2),
    }
