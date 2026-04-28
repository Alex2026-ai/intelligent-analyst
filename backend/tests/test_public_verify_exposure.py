"""
test_public_verify_exposure.py — Day 7: Public verify endpoint field exposure audit.

Verifies that /verify/{batch_id} and /verify/{batch_id}/seal expose NO:
  - tenant_id
  - credits_reserved / credits_spent / llm_budget_summary
  - internal shard state
  - Firestore document paths
  - cost fields
  - L3 reasoning payloads
  - resolution data (company names, match results)
  - PII
  - esg_rating / resolution_quality (notary removals)
"""

import json
import os
import pytest
from unittest.mock import patch
from app.security.public_verify import (
    build_public_verification_response,
    build_seal_data,
)


# Simulated batch data with ALL internal fields present (worst-case Firestore doc)
_FULL_BATCH = {
    "trace_id": "BATCH-AUDIT-TEST",
    "status": "completed",
    "tenant_id": "tenant_abc123",
    "owner_uid": "user-secret-uid",
    "stats": {"total": 500},
    "counts": {
        "total": 500, "l0": 10, "l1": 300, "l2": 100, "l3": 40, "l4": 50,
        "errors": 0,
    },
    "llm_budget_summary": {
        "budget_usd": 10.0, "spent_usd": 0.20, "calls": 40,
        "l3_yield": 85.0, "l3_failover_count": 1,
    },
    "cost": 0.20,
    "cost_usd": 0.20,
    "credits_reserved_usd": 5.0,
    "credits_spent_usd": 0.20,
    "shard_grid": {"num_shards": 4, "shard_size": 125},
    "shard_statuses": {"shard_0000": "completed", "shard_0001": "completed"},
    "signature": {
        "evidence_hash_sha256": "abc123",
        "signature": "base64sig==",
        "signed_at_utc": "2026-02-24T00:00:00Z",
        "key_version": "1",
    },
    "hash_chain": {
        "batch_root_hash": "rootabc",
        "chain_length": 500,
        "row_count": 500,
    },
    "anchor": {
        "anchored": True,
        "anchor_gcs_path": "gs://ia-anchors-test/2026/02/24/BATCH-AUDIT-TEST.json",
    },
    "legal_hold": {"status": "INACTIVE"},
    "finished_at": "2026-02-24T01:00:00Z",
    "config_snapshot": {"version": "3.0.0"},
    "l3_reasoning": [
        {"input": "Acme Corp", "resolved": "Acme Inc", "confidence": 0.92},
    ],
    "results": [
        {"original": "Acme Corp", "resolved": "Acme Inc", "layer": "L3_LLM"},
    ],
    "firestore_path": "batches/BATCH-AUDIT-TEST",
    "iavp_manifest": {"artifact_mode": "FULL"},
}

# Fields that MUST NOT appear anywhere in the public response JSON
FORBIDDEN_FIELDS = [
    "tenant_id",
    "owner_uid",
    "credits_reserved",
    "credits_spent",
    "credits_reserved_usd",
    "credits_spent_usd",
    "llm_budget_summary",
    "cost_usd",
    "l3_reasoning",
    "l3_failover_count",
    "shard_grid",
    "shard_statuses",
    "shard_0000",
    "shard_0001",
    "firestore_path",
    "esg_rating",
    "resolution_quality",
    "auto_resolved_pct",
    "human_review_pct",
    "results",
    "original",
    "resolved",
    # PII patterns
    "Acme Corp",
    "Acme Inc",
    "user-secret-uid",
    "tenant_abc123",
]

# Fields that MUST be present in the verify response
REQUIRED_VERIFY_FIELDS = [
    "status",
    "batch_id",
    "verified_at_utc",
    "public_trust_summary",
    "redactions",
]

# Fields that MUST be present in the seal response
REQUIRED_SEAL_FIELDS = [
    "verified",
    "batch_id",
    "status",
]


class TestVerifyEndpointNoForbiddenFields:
    def test_no_forbidden_fields_in_verify(self):
        response = build_public_verification_response("BATCH-AUDIT-TEST", _FULL_BATCH)
        response_str = json.dumps(response)
        violations = []
        for field in FORBIDDEN_FIELDS:
            if field in response_str:
                violations.append(field)
        assert violations == [], (
            f"EXPOSURE VIOLATION: forbidden fields found in /verify response: {violations}"
        )

    def test_verify_required_fields_present(self):
        response = build_public_verification_response("BATCH-AUDIT-TEST", _FULL_BATCH)
        for key in REQUIRED_VERIFY_FIELDS:
            assert key in response, f"Missing required field: {key}"

    def test_verify_redactions_block(self):
        response = build_public_verification_response("BATCH-AUDIT-TEST", _FULL_BATCH)
        redactions = response.get("redactions", {})
        assert redactions.get("no_resolution_data_exposed") is True
        assert redactions.get("hold_reason_redacted") is True
        assert redactions.get("requestor_identity_redacted") is True


class TestSealEndpointNoForbiddenFields:
    def test_no_forbidden_fields_in_seal(self):
        response = build_seal_data("BATCH-AUDIT-TEST", _FULL_BATCH)
        response_str = json.dumps(response)
        violations = []
        for field in FORBIDDEN_FIELDS:
            if field in response_str:
                violations.append(field)
        assert violations == [], (
            f"EXPOSURE VIOLATION: forbidden fields found in /verify/seal response: {violations}"
        )

    def test_seal_required_fields_present(self):
        response = build_seal_data("BATCH-AUDIT-TEST", _FULL_BATCH)
        for key in REQUIRED_SEAL_FIELDS:
            assert key in response, f"Missing required field: {key}"

    def test_seal_minimal_keys(self):
        """Seal should have at most 5 keys."""
        response = build_seal_data("BATCH-AUDIT-TEST", _FULL_BATCH)
        assert len(response) <= 5, (
            f"Seal response has too many keys ({len(response)}): {list(response.keys())}"
        )


class TestVerifyNotFoundSafe:
    def test_not_found_no_forbidden(self):
        response = build_public_verification_response("BATCH-NONEXISTENT", None)
        response_str = json.dumps(response)
        for field in FORBIDDEN_FIELDS:
            assert field not in response_str, (
                f"EXPOSURE: {field} in NOT_FOUND response"
            )
        assert response["status"] == "NOT_FOUND"


class TestVerifyNoInternalCostFields:
    """Specifically test that no cost/budget/spend fields leak."""
    def test_no_cost_anywhere(self):
        response = build_public_verification_response("BATCH-AUDIT-TEST", _FULL_BATCH)
        response_str = json.dumps(response).lower()
        cost_terms = ["cost", "budget", "spend", "credits", "usd"]
        violations = [t for t in cost_terms if t in response_str]
        assert violations == [], (
            f"Cost-related terms found in public response: {violations}"
        )


# ────────────────────────────────────────────────────────────────────────────
# BUG-003: /verify must return 404 for nonexistent batches (fail-closed)
# ────────────────────────────────────────────────────────────────────────────

def _get_test_client():
    """Return a TestClient for the monolith app."""
    with patch.dict(os.environ, {"HMAC_SCOPE_KEY": "aa" * 32}):
        from app.server_enterprise_golden import app
        from fastapi.testclient import TestClient
        return TestClient(app)


class TestBUG003VerifyReturns404ForNonexistent:
    """BUG-003 regression: /verify/{batch_id} must return 404 for nonexistent batches."""

    def test_nonexistent_batch_returns_404(self):
        with patch("app.server_enterprise_golden.get_batch_by_trace_id", return_value=None):
            client = _get_test_client()
            resp = client.get("/verify/BATCH-DOES-NOT-EXIST")
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
        data = resp.json()
        assert data["status"] == "NOT_FOUND"
        assert data["batch_id"] == "BATCH-DOES-NOT-EXIST"

    def test_nonexistent_batch_seal_returns_404(self):
        with patch("app.server_enterprise_golden.get_batch_by_trace_id", return_value=None):
            client = _get_test_client()
            resp = client.get("/verify/BATCH-DOES-NOT-EXIST/seal")
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
        data = resp.json()
        assert data["status"] == "NOT_FOUND"
        assert data["verified"] is False

    def test_existing_batch_returns_200(self):
        """Valid batch must still return 200 (not regressed by fix)."""
        fake_batch = {
            "trace_id": "BATCH-REAL-123",
            "status": "completed",
            "stats": {"total": 10},
            "signature": {},
            "hash_chain": {},
        }
        with patch("app.server_enterprise_golden.get_batch_by_trace_id", return_value=fake_batch):
            client = _get_test_client()
            resp = client.get("/verify/BATCH-REAL-123")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        assert resp.json()["batch_id"] == "BATCH-REAL-123"

    def test_existing_batch_seal_returns_200(self):
        """Valid batch seal must still return 200."""
        fake_batch = {
            "trace_id": "BATCH-REAL-123",
            "status": "completed",
            "signature": {"signature": "sig==", "signed_at_utc": "2026-03-24T00:00:00Z"},
            "hash_chain": {"batch_root_hash": "abc123"},
        }
        with patch("app.server_enterprise_golden.get_batch_by_trace_id", return_value=fake_batch):
            client = _get_test_client()
            resp = client.get("/verify/BATCH-REAL-123/seal")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        assert resp.json()["verified"] is True

    def test_response_shape_deterministic_on_404(self):
        """NOT_FOUND response shape is stable and fail-closed."""
        with patch("app.server_enterprise_golden.get_batch_by_trace_id", return_value=None):
            client = _get_test_client()
            resp = client.get("/verify/BATCH-NONEXISTENT")
        data = resp.json()
        assert set(data.keys()) == {"status", "batch_id", "verified_at_utc", "error"}
        assert data["status"] == "NOT_FOUND"
        assert "not found" in data["error"].lower()


# ────────────────────────────────────────────────────────────────────────────
# BUG-005: /verify must include security headers on all response paths
# ────────────────────────────────────────────────────────────────────────────

# These match _VERIFY_SECURITY_HEADERS in server_enterprise_golden.py,
# with Cache-Control overridden to preserve public caching semantics.
_EXPECTED_SECURITY_HEADERS = {
    "content-security-policy": "default-src 'none'; frame-ancestors 'none'",
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "access-control-allow-origin": "*",
}


def _assert_security_headers(resp):
    for key, val in _EXPECTED_SECURITY_HEADERS.items():
        actual = resp.headers.get(key)
        assert actual == val, (
            f"Header {key!r}: expected {val!r}, got {actual!r}"
        )
    # Cache-Control must be present (value depends on endpoint contract)
    assert "cache-control" in resp.headers, "Missing Cache-Control header"


class TestBUG005VerifySecurityHeaders:
    """BUG-005 regression: /verify endpoints must carry security headers."""

    def test_verify_200_has_security_headers(self):
        fake_batch = {
            "trace_id": "BATCH-HDR-200",
            "status": "completed",
            "stats": {"total": 10},
            "signature": {},
            "hash_chain": {},
        }
        with patch("app.server_enterprise_golden.get_batch_by_trace_id", return_value=fake_batch):
            client = _get_test_client()
            resp = client.get("/verify/BATCH-HDR-200")
        assert resp.status_code == 200
        _assert_security_headers(resp)

    def test_verify_404_has_security_headers(self):
        with patch("app.server_enterprise_golden.get_batch_by_trace_id", return_value=None):
            client = _get_test_client()
            resp = client.get("/verify/BATCH-HDR-GONE")
        assert resp.status_code == 404
        _assert_security_headers(resp)

    def test_verify_400_has_security_headers(self):
        client = _get_test_client()
        resp = client.get("/verify/!!!INVALID!!!")
        assert resp.status_code == 400
        _assert_security_headers(resp)

    def test_seal_200_has_security_headers(self):
        fake_batch = {
            "trace_id": "BATCH-HDR-SEAL",
            "status": "completed",
            "signature": {"signature": "sig==", "signed_at_utc": "2026-03-24T00:00:00Z"},
            "hash_chain": {"batch_root_hash": "abc123"},
        }
        with patch("app.server_enterprise_golden.get_batch_by_trace_id", return_value=fake_batch):
            client = _get_test_client()
            resp = client.get("/verify/BATCH-HDR-SEAL/seal")
        assert resp.status_code == 200
        _assert_security_headers(resp)

    def test_seal_404_has_security_headers(self):
        with patch("app.server_enterprise_golden.get_batch_by_trace_id", return_value=None):
            client = _get_test_client()
            resp = client.get("/verify/BATCH-HDR-SEAL-GONE/seal")
        assert resp.status_code == 404
        _assert_security_headers(resp)

    def test_seal_400_has_security_headers(self):
        client = _get_test_client()
        resp = client.get("/verify/!!!INVALID!!!/seal")
        assert resp.status_code == 400
        _assert_security_headers(resp)

    def test_verify_preserves_public_cache_control(self):
        """Cache-Control must remain public+cacheable (not no-store)."""
        fake_batch = {
            "trace_id": "BATCH-CACHE",
            "status": "completed",
            "stats": {"total": 5},
            "signature": {},
            "hash_chain": {},
        }
        with patch("app.server_enterprise_golden.get_batch_by_trace_id", return_value=fake_batch):
            client = _get_test_client()
            resp = client.get("/verify/BATCH-CACHE")
        assert resp.headers.get("cache-control") == "public, max-age=300"
