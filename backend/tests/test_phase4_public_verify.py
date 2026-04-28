"""
Phase 4 — Public Receipt Verification Endpoint Tests.

Covers:
  1. Valid receipt → 200 + status=valid
  2. Invalid signature → 200 + status=invalid + failure_reasons
  3. Non-existent receipt → 404
  4. Incomplete bundle → 200 + status=incomplete
  5. Rate limit exceeded → 429
  6. Sanitized response — no internal keys, no PII
  7. Response schema matches contract exactly
  8. No auth required
"""

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.utils import Prehashed

from app.security.iavp import jcs_canonicalize
from app.attestation.manifest_v1 import build_attestation_manifest_v1, PROTOCOL_VERSION


# ─────────────────────────────────────────────────────────────────────────────
# Test fixtures
# ─────────────────────────────────────────────────────────────────────────────

TEST_KEY_ID = "projects/test/locations/us/keyRings/test-ring/cryptoKeys/test-key/cryptoKeyVersions/1"
TEST_RECEIPT_ID = "abcd1234-ef56-7890-abcd-ef1234567890"
TEST_GCS_PREFIX = "gs://ia-test-receipts/receipts/a1b2c3d4e5f6a7b8/abcd1234-ef56-7890-abcd-ef1234567890"

_TEST_PRIVATE_KEY = ec.generate_private_key(ec.SECP256R1())
_TEST_PUBLIC_KEY = _TEST_PRIVATE_KEY.public_key()
_TEST_PUBLIC_PEM = _TEST_PUBLIC_KEY.public_bytes(
    serialization.Encoding.PEM,
    serialization.PublicFormat.SubjectPublicKeyInfo,
).decode("utf-8")


def _build_valid_manifest_and_sig():
    """Build a valid JCS manifest + ECDSA signature for testing."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    manifest = build_attestation_manifest_v1(
        batch_id="BATCH-PV4-001",
        root_hash=hashlib.sha256(b"root-data").hexdigest(),
        artifact_mode="PRODUCTION_REAL",
        engine_version="8.2.2",
        environment="test",
        config_hash=hashlib.sha256(b"config").hexdigest(),
        dataset_hash=hashlib.sha256(b"dataset").hexdigest(),
        registry_hash=hashlib.sha256(b"registry").hexdigest(),
        key_id=TEST_KEY_ID,
        metrics={
            "l1_pct": 0.85, "l2_pct": 0.08, "l3_pct": 0.02, "l4_pct": 0.05,
            "record_count": 100, "replay_method": "deterministic",
            "replay_runs": 1, "replay_variance": 0.0,
        },
        tenant_scope="a1b2c3d4e5f6a7b8",
        anchor_ref={
            "anchor_hash": hashlib.sha256(b"anchor-obj").hexdigest(),
            "anchor_timestamp": ts,
            "bucket": "ia-test-anchors",
            "object_path": "anchors/BATCH-PV4-001.json",
        },
        artifact_hashes=[{
            "artifact_type": "results_csv",
            "hash": hashlib.sha256(b"artifact").hexdigest(),
            "size_bytes": 4096,
        }],
        receipt_id=TEST_RECEIPT_ID,
        timestamp=ts,
    )
    manifest_bytes = jcs_canonicalize(manifest)
    digest = hashlib.sha256(manifest_bytes).digest()
    sig_bytes = _TEST_PRIVATE_KEY.sign(digest, ec.ECDSA(Prehashed(hashes.SHA256())))
    return manifest_bytes, sig_bytes


def _batch_with_receipt(receipt_id=TEST_RECEIPT_ID, gcs_prefix=TEST_GCS_PREFIX):
    """Return a batch dict with receipt pointer."""
    return {
        "trace_id": "BATCH-PV4-001",
        "status": "completed",
        "tenant_id": "tenant-test",
        "receipt": {
            "id": receipt_id,
            "gcs_path": gcs_prefix,
            "version": "ia-attestation/v1",
            "finalized_at": datetime.now(timezone.utc).isoformat(),
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Schema constants
# ─────────────────────────────────────────────────────────────────────────────

REQUIRED_TOP_KEYS = {"receipt_id", "status", "verification_timestamp", "checks", "failure_reasons", "_links"}
REQUIRED_CHECK_KEYS = {"signature_valid", "anchor_valid", "artifact_integrity", "replay_protection"}
ALLOWED_STATUSES = {"valid", "invalid", "incomplete"}
ALLOWED_FAILURE_REASONS = {
    "MANIFEST_MALFORMED", "SIGNATURE_INVALID", "KEY_VERSION_MISMATCH",
    "METADATA_INCONSISTENT", "ANCHOR_HASH_MISMATCH",
    "ARTIFACT_HASH_MISMATCH", "ARTIFACT_SIZE_MISMATCH",
    "TIMESTAMP_SKEW_EXCEEDED", "INTERNAL_ERROR",
    "BUNDLE_NOT_FOUND", "BUNDLE_INCOMPLETE", "VERIFICATION_FAILED",
}


# ─────────────────────────────────────────────────────────────────────────────
# Helper to get test client with mocked Firestore/GCS
# ─────────────────────────────────────────────────────────────────────────────

def _get_client():
    """Return a TestClient for the FastAPI app."""
    # Reset rate limiter between tests
    import app.server_enterprise_golden as srv
    srv._receipt_verify_rate.clear()

    with patch.dict(os.environ, {"HMAC_SCOPE_KEY": "aa" * 32}):
        from app.server_enterprise_golden import app
        return TestClient(app)


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestPublicVerifyReceipt:
    """Phase 4 public verify endpoint tests."""

    def test_valid_receipt_returns_200_valid(self):
        """Valid receipt with good signature → 200 + status=valid."""
        manifest_bytes, sig_bytes = _build_valid_manifest_and_sig()
        batch = _batch_with_receipt()

        with patch("app.server_enterprise_golden._find_batch_by_receipt_id", return_value=batch), \
             patch("app.server_enterprise_golden._load_receipt_bundle_from_gcs",
                   return_value=(manifest_bytes, sig_bytes, None)), \
             patch("app.security.public_verify._resolve_public_key_for_verification",
                   return_value=_TEST_PUBLIC_PEM):
            client = _get_client()
            resp = client.get(f"/verify/receipt/{TEST_RECEIPT_ID}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "valid"
        assert data["receipt_id"] == TEST_RECEIPT_ID
        assert data["checks"]["signature_valid"] is True
        assert data["checks"]["anchor_valid"] is True
        assert data["checks"]["artifact_integrity"] is True
        assert data["checks"]["replay_protection"] is True
        assert data["failure_reasons"] == []
        assert "manifest" in data["_links"]

    def test_invalid_signature_returns_200_invalid(self):
        """Bad signature → 200 + status=invalid + failure_reasons populated."""
        manifest_bytes, _ = _build_valid_manifest_and_sig()
        # Create signature with a different key
        wrong_key = ec.generate_private_key(ec.SECP256R1())
        digest = hashlib.sha256(manifest_bytes).digest()
        bad_sig = wrong_key.sign(digest, ec.ECDSA(Prehashed(hashes.SHA256())))
        batch = _batch_with_receipt()

        with patch("app.server_enterprise_golden._find_batch_by_receipt_id", return_value=batch), \
             patch("app.server_enterprise_golden._load_receipt_bundle_from_gcs",
                   return_value=(manifest_bytes, bad_sig, None)), \
             patch("app.security.public_verify._resolve_public_key_for_verification",
                   return_value=_TEST_PUBLIC_PEM):
            client = _get_client()
            resp = client.get(f"/verify/receipt/{TEST_RECEIPT_ID}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "invalid"
        assert len(data["failure_reasons"]) > 0
        assert data["failure_reasons"][0] in ALLOWED_FAILURE_REASONS
        assert data["checks"]["signature_valid"] is False

    def test_nonexistent_receipt_returns_404(self):
        """Receipt not found → 404."""
        with patch("app.server_enterprise_golden._find_batch_by_receipt_id", return_value=None):
            client = _get_client()
            resp = client.get("/verify/receipt/nonexistent-receipt-id")

        assert resp.status_code == 404
        data = resp.json()
        assert "error" in data
        assert data["receipt_id"] == "nonexistent-receipt-id"

    def test_incomplete_bundle_returns_200_incomplete(self):
        """Missing signature.der → 200 + status=incomplete."""
        manifest_bytes, _ = _build_valid_manifest_and_sig()
        batch = _batch_with_receipt()

        # Signature missing (None)
        with patch("app.server_enterprise_golden._find_batch_by_receipt_id", return_value=batch), \
             patch("app.server_enterprise_golden._load_receipt_bundle_from_gcs",
                   return_value=(manifest_bytes, None, None)):
            client = _get_client()
            resp = client.get(f"/verify/receipt/{TEST_RECEIPT_ID}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "incomplete"
        assert "BUNDLE_INCOMPLETE" in data["failure_reasons"]

    def test_no_gcs_prefix_returns_incomplete(self):
        """Batch exists but receipt has no gcs_path → incomplete."""
        batch = _batch_with_receipt()
        batch["receipt"]["gcs_path"] = ""

        with patch("app.server_enterprise_golden._find_batch_by_receipt_id", return_value=batch):
            client = _get_client()
            resp = client.get(f"/verify/receipt/{TEST_RECEIPT_ID}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "incomplete"
        assert "BUNDLE_NOT_FOUND" in data["failure_reasons"]

    def test_rate_limit_returns_429(self):
        """Exceeding 100 req/min → 429."""
        batch = _batch_with_receipt()

        with patch("app.server_enterprise_golden._find_batch_by_receipt_id", return_value=batch), \
             patch("app.server_enterprise_golden._load_receipt_bundle_from_gcs",
                   return_value=(None, None, "unavailable")):
            client = _get_client()

            # Exhaust rate limit
            import app.server_enterprise_golden as srv
            test_ip = "testclient"
            srv._receipt_verify_rate[test_ip] = [time.time()] * 100

            resp = client.get(f"/verify/receipt/{TEST_RECEIPT_ID}")

        assert resp.status_code == 429
        data = resp.json()
        assert "Rate limit" in data.get("error", "")

    def test_no_auth_required(self):
        """Endpoint works without any auth headers."""
        with patch("app.server_enterprise_golden._find_batch_by_receipt_id", return_value=None):
            client = _get_client()
            # No Authorization header, no X-API-Key
            resp = client.get("/verify/receipt/some-id")

        # Should get 404 (not found), not 401/403
        assert resp.status_code == 404


class TestResponseSchema:
    """Verify exact response schema matches contract."""

    def test_response_has_exact_top_level_keys(self):
        """Response must have exactly the contracted keys."""
        manifest_bytes, sig_bytes = _build_valid_manifest_and_sig()
        batch = _batch_with_receipt()

        with patch("app.server_enterprise_golden._find_batch_by_receipt_id", return_value=batch), \
             patch("app.server_enterprise_golden._load_receipt_bundle_from_gcs",
                   return_value=(manifest_bytes, sig_bytes, None)), \
             patch("app.security.public_verify._resolve_public_key_for_verification",
                   return_value=_TEST_PUBLIC_PEM):
            client = _get_client()
            resp = client.get(f"/verify/receipt/{TEST_RECEIPT_ID}")

        data = resp.json()
        assert set(data.keys()) == REQUIRED_TOP_KEYS

    def test_checks_has_exact_keys(self):
        """checks dict must have exactly the contracted keys."""
        manifest_bytes, sig_bytes = _build_valid_manifest_and_sig()
        batch = _batch_with_receipt()

        with patch("app.server_enterprise_golden._find_batch_by_receipt_id", return_value=batch), \
             patch("app.server_enterprise_golden._load_receipt_bundle_from_gcs",
                   return_value=(manifest_bytes, sig_bytes, None)), \
             patch("app.security.public_verify._resolve_public_key_for_verification",
                   return_value=_TEST_PUBLIC_PEM):
            client = _get_client()
            resp = client.get(f"/verify/receipt/{TEST_RECEIPT_ID}")

        data = resp.json()
        assert set(data["checks"].keys()) == REQUIRED_CHECK_KEYS

    def test_status_uses_allowed_values_only(self):
        """status must be one of: valid, invalid, incomplete."""
        manifest_bytes, sig_bytes = _build_valid_manifest_and_sig()
        batch = _batch_with_receipt()

        with patch("app.server_enterprise_golden._find_batch_by_receipt_id", return_value=batch), \
             patch("app.server_enterprise_golden._load_receipt_bundle_from_gcs",
                   return_value=(manifest_bytes, sig_bytes, None)), \
             patch("app.security.public_verify._resolve_public_key_for_verification",
                   return_value=_TEST_PUBLIC_PEM):
            client = _get_client()
            resp = client.get(f"/verify/receipt/{TEST_RECEIPT_ID}")

        assert resp.json()["status"] in ALLOWED_STATUSES

    def test_failure_reasons_use_locked_taxonomy(self):
        """failure_reasons values must be from the locked taxonomy."""
        manifest_bytes, _ = _build_valid_manifest_and_sig()
        wrong_key = ec.generate_private_key(ec.SECP256R1())
        bad_sig = wrong_key.sign(
            hashlib.sha256(manifest_bytes).digest(),
            ec.ECDSA(Prehashed(hashes.SHA256())),
        )
        batch = _batch_with_receipt()

        with patch("app.server_enterprise_golden._find_batch_by_receipt_id", return_value=batch), \
             patch("app.server_enterprise_golden._load_receipt_bundle_from_gcs",
                   return_value=(manifest_bytes, bad_sig, None)), \
             patch("app.security.public_verify._resolve_public_key_for_verification",
                   return_value=_TEST_PUBLIC_PEM):
            client = _get_client()
            resp = client.get(f"/verify/receipt/{TEST_RECEIPT_ID}")

        data = resp.json()
        for reason in data["failure_reasons"]:
            assert reason in ALLOWED_FAILURE_REASONS, f"Unexpected reason: {reason}"

    def test_manifest_link_present_when_receipt_exists(self):
        """_links.manifest must be present when receipt is found."""
        manifest_bytes, sig_bytes = _build_valid_manifest_and_sig()
        batch = _batch_with_receipt()

        with patch("app.server_enterprise_golden._find_batch_by_receipt_id", return_value=batch), \
             patch("app.server_enterprise_golden._load_receipt_bundle_from_gcs",
                   return_value=(manifest_bytes, sig_bytes, None)), \
             patch("app.security.public_verify._resolve_public_key_for_verification",
                   return_value=_TEST_PUBLIC_PEM):
            client = _get_client()
            resp = client.get(f"/verify/receipt/{TEST_RECEIPT_ID}")

        data = resp.json()
        assert "manifest" in data["_links"]
        assert data["_links"]["manifest"].endswith("/manifest.json")

    def test_invalid_receipt_still_returns_200(self):
        """Invalid receipt returns 200, not 4xx."""
        manifest_bytes, _ = _build_valid_manifest_and_sig()
        wrong_key = ec.generate_private_key(ec.SECP256R1())
        bad_sig = wrong_key.sign(
            hashlib.sha256(manifest_bytes).digest(),
            ec.ECDSA(Prehashed(hashes.SHA256())),
        )
        batch = _batch_with_receipt()

        with patch("app.server_enterprise_golden._find_batch_by_receipt_id", return_value=batch), \
             patch("app.server_enterprise_golden._load_receipt_bundle_from_gcs",
                   return_value=(manifest_bytes, bad_sig, None)), \
             patch("app.security.public_verify._resolve_public_key_for_verification",
                   return_value=_TEST_PUBLIC_PEM):
            client = _get_client()
            resp = client.get(f"/verify/receipt/{TEST_RECEIPT_ID}")

        assert resp.status_code == 200
        assert resp.json()["status"] == "invalid"


class TestSanitization:
    """Verify no internal data leaks in response."""

    def test_no_key_id_in_response(self):
        """Response must not contain key_id or KMS path."""
        manifest_bytes, sig_bytes = _build_valid_manifest_and_sig()
        batch = _batch_with_receipt()

        with patch("app.server_enterprise_golden._find_batch_by_receipt_id", return_value=batch), \
             patch("app.server_enterprise_golden._load_receipt_bundle_from_gcs",
                   return_value=(manifest_bytes, sig_bytes, None)), \
             patch("app.security.public_verify._resolve_public_key_for_verification",
                   return_value=_TEST_PUBLIC_PEM):
            client = _get_client()
            resp = client.get(f"/verify/receipt/{TEST_RECEIPT_ID}")

        resp_str = json.dumps(resp.json())
        assert "keyRings" not in resp_str
        assert "cryptoKeys" not in resp_str
        assert TEST_KEY_ID not in resp_str

    def test_no_pii_in_response(self):
        """Response must not contain tenant_id or any PII."""
        manifest_bytes, sig_bytes = _build_valid_manifest_and_sig()
        batch = _batch_with_receipt()

        with patch("app.server_enterprise_golden._find_batch_by_receipt_id", return_value=batch), \
             patch("app.server_enterprise_golden._load_receipt_bundle_from_gcs",
                   return_value=(manifest_bytes, sig_bytes, None)), \
             patch("app.security.public_verify._resolve_public_key_for_verification",
                   return_value=_TEST_PUBLIC_PEM):
            client = _get_client()
            resp = client.get(f"/verify/receipt/{TEST_RECEIPT_ID}")

        resp_str = json.dumps(resp.json())
        assert "tenant-test" not in resp_str
        assert "tenant_id" not in resp_str

    def test_no_stack_traces_in_response(self):
        """Response must not contain exception class names or tracebacks."""
        batch = _batch_with_receipt()

        # Force verifier to throw
        with patch("app.server_enterprise_golden._find_batch_by_receipt_id", return_value=batch), \
             patch("app.server_enterprise_golden._load_receipt_bundle_from_gcs",
                   return_value=(b"bad-manifest", b"\x00", None)):
            client = _get_client()
            resp = client.get(f"/verify/receipt/{TEST_RECEIPT_ID}")

        resp_str = json.dumps(resp.json())
        assert "Traceback" not in resp_str
        assert "Exception" not in resp_str
        assert resp.status_code == 200

    def test_no_internal_storage_structure_beyond_manifest(self):
        """Response _links should only contain manifest, no bucket/prefix detail."""
        manifest_bytes, sig_bytes = _build_valid_manifest_and_sig()
        batch = _batch_with_receipt()

        with patch("app.server_enterprise_golden._find_batch_by_receipt_id", return_value=batch), \
             patch("app.server_enterprise_golden._load_receipt_bundle_from_gcs",
                   return_value=(manifest_bytes, sig_bytes, None)), \
             patch("app.security.public_verify._resolve_public_key_for_verification",
                   return_value=_TEST_PUBLIC_PEM):
            client = _get_client()
            resp = client.get(f"/verify/receipt/{TEST_RECEIPT_ID}")

        links = resp.json()["_links"]
        # Only manifest link allowed
        assert set(links.keys()) == {"manifest"}

    def test_no_pii_or_internal_leak(self):
        """Response keys must be exactly the contracted set, no internal fields."""
        manifest_bytes, sig_bytes = _build_valid_manifest_and_sig()
        batch = _batch_with_receipt()

        with patch("app.server_enterprise_golden._find_batch_by_receipt_id", return_value=batch), \
             patch("app.server_enterprise_golden._load_receipt_bundle_from_gcs",
                   return_value=(manifest_bytes, sig_bytes, None)), \
             patch("app.security.public_verify._resolve_public_key_for_verification",
                   return_value=_TEST_PUBLIC_PEM):
            client = _get_client()
            resp = client.get(f"/verify/receipt/{TEST_RECEIPT_ID}")

        data = resp.json()
        assert "tenant_scope" not in data
        assert "key_id" not in data
        assert "kms_key_version" not in data
        assert "internal_error" not in data
        assert set(data.keys()) <= {
            "receipt_id",
            "status",
            "verification_timestamp",
            "checks",
            "failure_reasons",
            "_links",
        }


class TestSecurityHeaders:
    """Verify hardening headers on all response codes."""

    EXPECTED_HEADERS = {
        "cache-control": "no-store, no-cache, must-revalidate",
        "content-security-policy": "default-src 'none'; frame-ancestors 'none'",
        "x-content-type-options": "nosniff",
        "x-frame-options": "DENY",
    }

    def _assert_security_headers(self, resp):
        for key, val in self.EXPECTED_HEADERS.items():
            assert resp.headers.get(key) == val, f"Missing/wrong header {key}: {resp.headers.get(key)}"

    def test_headers_on_200_valid(self):
        manifest_bytes, sig_bytes = _build_valid_manifest_and_sig()
        batch = _batch_with_receipt()

        with patch("app.server_enterprise_golden._find_batch_by_receipt_id", return_value=batch), \
             patch("app.server_enterprise_golden._load_receipt_bundle_from_gcs",
                   return_value=(manifest_bytes, sig_bytes, None)), \
             patch("app.security.public_verify._resolve_public_key_for_verification",
                   return_value=_TEST_PUBLIC_PEM):
            client = _get_client()
            resp = client.get(f"/verify/receipt/{TEST_RECEIPT_ID}")

        assert resp.status_code == 200
        self._assert_security_headers(resp)

    def test_headers_on_200_invalid(self):
        manifest_bytes, _ = _build_valid_manifest_and_sig()
        wrong_key = ec.generate_private_key(ec.SECP256R1())
        bad_sig = wrong_key.sign(
            hashlib.sha256(manifest_bytes).digest(),
            ec.ECDSA(Prehashed(hashes.SHA256())),
        )
        batch = _batch_with_receipt()

        with patch("app.server_enterprise_golden._find_batch_by_receipt_id", return_value=batch), \
             patch("app.server_enterprise_golden._load_receipt_bundle_from_gcs",
                   return_value=(manifest_bytes, bad_sig, None)), \
             patch("app.security.public_verify._resolve_public_key_for_verification",
                   return_value=_TEST_PUBLIC_PEM):
            client = _get_client()
            resp = client.get(f"/verify/receipt/{TEST_RECEIPT_ID}")

        assert resp.status_code == 200
        self._assert_security_headers(resp)

    def test_headers_on_200_incomplete(self):
        batch = _batch_with_receipt()
        batch["receipt"]["gcs_path"] = ""

        with patch("app.server_enterprise_golden._find_batch_by_receipt_id", return_value=batch):
            client = _get_client()
            resp = client.get(f"/verify/receipt/{TEST_RECEIPT_ID}")

        assert resp.status_code == 200
        self._assert_security_headers(resp)

    def test_headers_on_404(self):
        with patch("app.server_enterprise_golden._find_batch_by_receipt_id", return_value=None):
            client = _get_client()
            resp = client.get("/verify/receipt/nonexistent")

        assert resp.status_code == 404
        self._assert_security_headers(resp)

    def test_headers_on_429(self):
        batch = _batch_with_receipt()

        with patch("app.server_enterprise_golden._find_batch_by_receipt_id", return_value=batch):
            client = _get_client()
            import app.server_enterprise_golden as srv
            srv._receipt_verify_rate["testclient"] = [time.time()] * 100
            resp = client.get(f"/verify/receipt/{TEST_RECEIPT_ID}")

        assert resp.status_code == 429
        self._assert_security_headers(resp)


class TestRateLimitStress:
    """Rate limit boundary test."""

    def test_rate_limit_enforcement_at_boundary(self):
        """Pre-fill rate limiter to exactly limit-1, next request succeeds, one after gets 429."""
        import app.server_enterprise_golden as srv
        from app.server_enterprise_golden import app, _RECEIPT_VERIFY_LIMIT
        from fastapi.testclient import TestClient

        with patch("app.server_enterprise_golden._find_batch_by_receipt_id", return_value=None):
            client = TestClient(app)
            # Pre-fill to exactly limit - 1 entries
            import time as _t
            srv._receipt_verify_rate["testclient"] = [_t.time()] * (_RECEIPT_VERIFY_LIMIT - 1)

            # Request at limit boundary should succeed (this is request #100)
            resp = client.get("/verify/receipt/test-rate-limit")
            assert resp.status_code == 404, f"Request at limit got {resp.status_code}"

            # Request #101 should get 429
            resp = client.get("/verify/receipt/test-rate-limit")
            assert resp.status_code == 429
