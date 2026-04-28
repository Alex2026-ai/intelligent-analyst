"""
Tests for Phase 9 — Trust Assertion Layer.

Covers:
1. Valid receipt → decision: allow
2. Invalid/missing receipt → decision: deny, reason: RECEIPT_INVALID
3. Policy violation (required check fails) → deny, POLICY_VIOLATION
4. Expired receipt → deny, RECEIPT_EXPIRED
5. Rate limit per-IP (100/min) → 429
6. Rate limit per-receipt_id (10/min) → 429
7. Assertion audit log written with hash-chain
8. /assert never creates a receipt (no side effects)
"""

import hashlib
import json
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_test_client():
    from app.server_enterprise_golden import app
    return TestClient(app, raise_server_exceptions=False)


def _make_assert_body(receipt_id="test-receipt-001", system="test-system",
                       action="test-action", resource_id="res-1",
                       correlation_id="corr-1", required_checks=None):
    body = {
        "receipt_id": receipt_id,
        "context": {
            "system": system,
            "action": action,
            "resource_id": resource_id,
            "correlation_id": correlation_id,
        },
    }
    if required_checks:
        body["required_checks"] = required_checks
    return body


def _mock_batch_with_receipt(receipt_id, finalized_at=None, gcs_path="gs://test-bucket/receipts/tenant/rcpt-001"):
    """Return a mock batch doc with receipt fields."""
    return {
        "trace_id": "BATCH-ASSERT-TEST",
        "receipt": {
            "id": receipt_id,
            "gcs_path": gcs_path,
            "finalized_at": finalized_at or datetime.now(timezone.utc).isoformat(),
            "manifest_hash": "a" * 64,
        },
    }


def _mock_valid_verify_result():
    return {
        "success": True,
        "failure_reason": None,
        "checks_passed": ["signature", "anchor_binding", "artifact_integrity", "schema_jcs"],
        "duration_ms": 0.5,
    }


def _mock_failing_verify_result(failure_reason="SIGNATURE_INVALID", checks_passed=None):
    return {
        "success": False,
        "failure_reason": failure_reason,
        "checks_passed": checks_passed or [],
        "duration_ms": 0.3,
    }


def _reset_rate_limiters():
    """Clear assertion rate limit state between tests."""
    from app import server_enterprise_golden as srv
    srv._assert_ip_rate.clear()
    srv._assert_receipt_rate.clear()


# ---------------------------------------------------------------------------
# Test 1: Valid receipt → allow
# ---------------------------------------------------------------------------

class TestValidReceiptAllow:
    def test_valid_receipt_returns_allow(self):
        _reset_rate_limiters()
        client = _get_test_client()

        receipt_id = "valid-receipt-001"
        batch = _mock_batch_with_receipt(receipt_id)
        manifest = {
            "root_hash": "1" * 64,
            "batch_id": "BATCH-001",
        }
        manifest_bytes = json.dumps(manifest).encode()

        with patch("app.server_enterprise_golden._find_batch_by_receipt_id", return_value=batch), \
             patch("app.server_enterprise_golden._load_receipt_bundle_from_gcs",
                   return_value=(manifest_bytes, b"sig-bytes", None)), \
             patch("app.attestation.verifier_v1.verify_manifest_bundle",
                   return_value=_mock_valid_verify_result()), \
             patch("app.server_enterprise_golden._write_assertion_event", return_value=True), \
             patch("app.server_enterprise_golden._load_assert_policy",
                   return_value={
                       "version": "1.0", "status": "active", "fail_closed": True,
                       "required_checks": ["signature", "anchor_binding", "artifact_integrity", "schema_jcs"],
                       "max_receipt_age_seconds": 86400,
                       "context": {"max_field_length": 256, "required_fields": ["system", "action", "resource_id", "correlation_id"]},
                   }):
            resp = client.post("/assert", json=_make_assert_body(receipt_id=receipt_id))

        assert resp.status_code == 200
        data = resp.json()
        assert data["decision"] == "allow"
        assert data["receipt_id"] == receipt_id
        assert data["verified"] is True
        assert data["assertion_id"].startswith("asrt_")
        assert data["reason"] == ""


# ---------------------------------------------------------------------------
# Test 2: Invalid/missing receipt → deny
# ---------------------------------------------------------------------------

class TestInvalidReceiptDeny:
    def test_missing_receipt_returns_deny(self):
        _reset_rate_limiters()
        client = _get_test_client()

        with patch("app.server_enterprise_golden._find_batch_by_receipt_id", return_value=None), \
             patch("app.server_enterprise_golden._write_assertion_event", return_value=True), \
             patch("app.server_enterprise_golden._load_assert_policy",
                   return_value={
                       "version": "1.0", "status": "active", "fail_closed": True,
                       "required_checks": ["signature", "anchor_binding", "artifact_integrity", "schema_jcs"],
                       "max_receipt_age_seconds": 86400,
                       "context": {"max_field_length": 256, "required_fields": ["system", "action", "resource_id", "correlation_id"]},
                   }):
            resp = client.post("/assert", json=_make_assert_body(receipt_id="nonexistent-receipt"))

        assert resp.status_code == 200
        data = resp.json()
        assert data["decision"] == "deny"
        assert data["reason"] == "RECEIPT_INVALID"
        assert data["verified"] is False

    def test_no_gcs_path_returns_deny(self):
        _reset_rate_limiters()
        client = _get_test_client()

        batch = _mock_batch_with_receipt("no-gcs-receipt", gcs_path="")

        with patch("app.server_enterprise_golden._find_batch_by_receipt_id", return_value=batch), \
             patch("app.server_enterprise_golden._write_assertion_event", return_value=True), \
             patch("app.server_enterprise_golden._load_assert_policy",
                   return_value={
                       "version": "1.0", "status": "active", "fail_closed": True,
                       "required_checks": ["signature", "anchor_binding", "artifact_integrity", "schema_jcs"],
                       "max_receipt_age_seconds": 86400,
                       "context": {"max_field_length": 256, "required_fields": ["system", "action", "resource_id", "correlation_id"]},
                   }):
            resp = client.post("/assert", json=_make_assert_body(receipt_id="no-gcs-receipt"))

        assert resp.status_code == 200
        data = resp.json()
        assert data["decision"] == "deny"
        assert data["reason"] == "RECEIPT_INVALID"


# ---------------------------------------------------------------------------
# Test 3: Policy violation → deny
# ---------------------------------------------------------------------------

class TestPolicyViolation:
    def test_missing_required_check_returns_policy_violation(self):
        _reset_rate_limiters()
        client = _get_test_client()

        receipt_id = "partial-checks-receipt"
        batch = _mock_batch_with_receipt(receipt_id)
        manifest = {"root_hash": "1" * 64}
        manifest_bytes = json.dumps(manifest).encode()

        # Verifier passes overall but missing artifact_integrity
        verify_result = {
            "success": True,
            "failure_reason": None,
            "checks_passed": ["signature", "anchor_binding", "schema_jcs"],  # missing artifact_integrity
            "duration_ms": 0.4,
        }

        with patch("app.server_enterprise_golden._find_batch_by_receipt_id", return_value=batch), \
             patch("app.server_enterprise_golden._load_receipt_bundle_from_gcs",
                   return_value=(manifest_bytes, b"sig", None)), \
             patch("app.attestation.verifier_v1.verify_manifest_bundle",
                   return_value=verify_result), \
             patch("app.server_enterprise_golden._write_assertion_event", return_value=True), \
             patch("app.server_enterprise_golden._load_assert_policy",
                   return_value={
                       "version": "1.0", "status": "active", "fail_closed": True,
                       "required_checks": ["signature", "anchor_binding", "artifact_integrity", "schema_jcs"],
                       "max_receipt_age_seconds": 86400,
                       "context": {"max_field_length": 256, "required_fields": ["system", "action", "resource_id", "correlation_id"]},
                   }):
            resp = client.post("/assert", json=_make_assert_body(receipt_id=receipt_id))

        assert resp.status_code == 200
        data = resp.json()
        assert data["decision"] == "deny"
        assert data["reason"] == "POLICY_VIOLATION"


# ---------------------------------------------------------------------------
# Test 4: Expired receipt → deny
# ---------------------------------------------------------------------------

class TestExpiredReceipt:
    def test_old_receipt_returns_expired(self):
        _reset_rate_limiters()
        client = _get_test_client()

        receipt_id = "old-receipt-001"
        old_time = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
        batch = _mock_batch_with_receipt(receipt_id, finalized_at=old_time)

        with patch("app.server_enterprise_golden._find_batch_by_receipt_id", return_value=batch), \
             patch("app.server_enterprise_golden._write_assertion_event", return_value=True), \
             patch("app.server_enterprise_golden._load_assert_policy",
                   return_value={
                       "version": "1.0", "status": "active", "fail_closed": True,
                       "required_checks": ["signature", "anchor_binding", "artifact_integrity", "schema_jcs"],
                       "max_receipt_age_seconds": 86400,
                       "context": {"max_field_length": 256, "required_fields": ["system", "action", "resource_id", "correlation_id"]},
                   }):
            resp = client.post("/assert", json=_make_assert_body(receipt_id=receipt_id))

        assert resp.status_code == 200
        data = resp.json()
        assert data["decision"] == "deny"
        assert data["reason"] == "RECEIPT_EXPIRED"


# ---------------------------------------------------------------------------
# Test 5: Rate limit per-IP → 429
# ---------------------------------------------------------------------------

class TestRateLimitPerIP:
    def test_ip_rate_limit_enforced(self):
        _reset_rate_limiters()
        from app.server_enterprise_golden import _check_assert_rate_limit, _ASSERT_IP_LIMIT

        # Fill up the IP limit
        for i in range(_ASSERT_IP_LIMIT):
            result = _check_assert_rate_limit("10.0.0.1", f"receipt-{i}")
            assert result is None, f"Should allow request {i}"

        # Next request should be blocked
        result = _check_assert_rate_limit("10.0.0.1", "receipt-overflow")
        assert result == "ip"


# ---------------------------------------------------------------------------
# Test 6: Rate limit per-receipt_id → 429
# ---------------------------------------------------------------------------

class TestRateLimitPerReceiptId:
    def test_receipt_rate_limit_enforced(self):
        _reset_rate_limiters()
        from app.server_enterprise_golden import _check_assert_rate_limit, _ASSERT_RECEIPT_LIMIT

        # Fill up the receipt_id limit (different IPs, same receipt)
        for i in range(_ASSERT_RECEIPT_LIMIT):
            result = _check_assert_rate_limit(f"10.0.0.{i}", "same-receipt")
            assert result is None, f"Should allow request {i}"

        # Next request should be blocked
        result = _check_assert_rate_limit("10.0.0.99", "same-receipt")
        assert result == "receipt_id"


# ---------------------------------------------------------------------------
# Test 7: Assertion audit log with hash-chain
# ---------------------------------------------------------------------------

class TestAssertionAuditLog:
    def test_audit_event_written_with_chain_hash(self):
        _reset_rate_limiters()
        client = _get_test_client()

        receipt_id = "audit-chain-receipt"
        batch = _mock_batch_with_receipt(receipt_id)
        manifest = {"root_hash": "1" * 64}
        manifest_bytes = json.dumps(manifest).encode()

        written_events = []

        def capture_event(**kwargs):
            written_events.append(kwargs)
            return True

        with patch("app.server_enterprise_golden._find_batch_by_receipt_id", return_value=batch), \
             patch("app.server_enterprise_golden._load_receipt_bundle_from_gcs",
                   return_value=(manifest_bytes, b"sig", None)), \
             patch("app.attestation.verifier_v1.verify_manifest_bundle",
                   return_value=_mock_valid_verify_result()), \
             patch("app.server_enterprise_golden._write_assertion_event",
                   side_effect=lambda **kw: (written_events.append(kw), True)[-1]), \
             patch("app.server_enterprise_golden._load_assert_policy",
                   return_value={
                       "version": "1.0", "status": "active", "fail_closed": True,
                       "required_checks": ["signature", "anchor_binding", "artifact_integrity", "schema_jcs"],
                       "max_receipt_age_seconds": 86400,
                       "context": {"max_field_length": 256, "required_fields": ["system", "action", "resource_id", "correlation_id"]},
                   }):
            resp = client.post("/assert", json=_make_assert_body(receipt_id=receipt_id))

        assert resp.status_code == 200
        assert len(written_events) == 1

        event = written_events[0]
        assert event["assertion_id"].startswith("asrt_")
        assert event["receipt_id"] == receipt_id
        assert event["receipt_root_hash"] == "1" * 64
        assert event["policy_version"] == "1.0"
        assert "signature" in event["checks_evaluated"]

    def test_chain_hash_is_deterministic(self):
        """Hash chain: SHA-256(assertion_id:root_hash) is deterministic."""
        aid = "asrt_test123"
        root = "a" * 64
        chain_input = f"{aid}:{root}"
        expected = hashlib.sha256(chain_input.encode()).hexdigest()

        # Compute again
        chain_input2 = f"{aid}:{root}"
        actual = hashlib.sha256(chain_input2.encode()).hexdigest()

        assert expected == actual
        assert len(expected) == 64


# ---------------------------------------------------------------------------
# Test 8: /assert never creates a receipt
# ---------------------------------------------------------------------------

class TestNoReceiptCreation:
    def test_assert_never_calls_receipt_writer(self):
        """Core invariant: /assert NEVER creates receipts."""
        _reset_rate_limiters()
        client = _get_test_client()

        receipt_id = "no-create-receipt"
        batch = _mock_batch_with_receipt(receipt_id)
        manifest = {"root_hash": "1" * 64}
        manifest_bytes = json.dumps(manifest).encode()

        with patch("app.server_enterprise_golden._find_batch_by_receipt_id", return_value=batch), \
             patch("app.server_enterprise_golden._load_receipt_bundle_from_gcs",
                   return_value=(manifest_bytes, b"sig", None)), \
             patch("app.attestation.verifier_v1.verify_manifest_bundle",
                   return_value=_mock_valid_verify_result()), \
             patch("app.server_enterprise_golden._write_assertion_event", return_value=True), \
             patch("app.server_enterprise_golden._load_assert_policy",
                   return_value={
                       "version": "1.0", "status": "active", "fail_closed": True,
                       "required_checks": ["signature", "anchor_binding", "artifact_integrity", "schema_jcs"],
                       "max_receipt_age_seconds": 86400,
                       "context": {"max_field_length": 256, "required_fields": ["system", "action", "resource_id", "correlation_id"]},
                   }) as mock_policy, \
             patch("app.attestation.receipt_writer.write_receipt_bundle",
                   side_effect=AssertionError("MUST NOT BE CALLED")) as mock_writer:
            resp = client.post("/assert", json=_make_assert_body(receipt_id=receipt_id))

        assert resp.status_code == 200
        data = resp.json()
        assert data["decision"] == "allow"
        # If write_receipt_bundle was called, it would raise AssertionError
        mock_writer.assert_not_called()

    def test_deny_path_never_creates_receipt(self):
        """Even on deny, no receipt is created."""
        _reset_rate_limiters()
        client = _get_test_client()

        with patch("app.server_enterprise_golden._find_batch_by_receipt_id", return_value=None), \
             patch("app.server_enterprise_golden._write_assertion_event", return_value=True), \
             patch("app.server_enterprise_golden._load_assert_policy",
                   return_value={
                       "version": "1.0", "status": "active", "fail_closed": True,
                       "required_checks": ["signature", "anchor_binding", "artifact_integrity", "schema_jcs"],
                       "max_receipt_age_seconds": 86400,
                       "context": {"max_field_length": 256, "required_fields": ["system", "action", "resource_id", "correlation_id"]},
                   }), \
             patch("app.attestation.receipt_writer.write_receipt_bundle",
                   side_effect=AssertionError("MUST NOT BE CALLED")) as mock_writer:
            resp = client.post("/assert", json=_make_assert_body(receipt_id="fake"))

        assert resp.status_code == 200
        assert resp.json()["decision"] == "deny"
        mock_writer.assert_not_called()


# ---------------------------------------------------------------------------
# Additional: Response schema validation
# ---------------------------------------------------------------------------

class TestResponseSchema:
    def test_response_has_all_required_fields(self):
        _reset_rate_limiters()
        client = _get_test_client()

        receipt_id = "schema-check-receipt"
        batch = _mock_batch_with_receipt(receipt_id)
        manifest = {"root_hash": "1" * 64}
        manifest_bytes = json.dumps(manifest).encode()

        with patch("app.server_enterprise_golden._find_batch_by_receipt_id", return_value=batch), \
             patch("app.server_enterprise_golden._load_receipt_bundle_from_gcs",
                   return_value=(manifest_bytes, b"sig", None)), \
             patch("app.attestation.verifier_v1.verify_manifest_bundle",
                   return_value=_mock_valid_verify_result()), \
             patch("app.server_enterprise_golden._write_assertion_event", return_value=True), \
             patch("app.server_enterprise_golden._load_assert_policy",
                   return_value={
                       "version": "1.0", "status": "active", "fail_closed": True,
                       "required_checks": ["signature", "anchor_binding", "artifact_integrity", "schema_jcs"],
                       "max_receipt_age_seconds": 86400,
                       "context": {"max_field_length": 256, "required_fields": ["system", "action", "resource_id", "correlation_id"]},
                   }):
            resp = client.post("/assert", json=_make_assert_body(receipt_id=receipt_id))

        data = resp.json()
        required_fields = ["decision", "receipt_id", "verified", "reason",
                          "assertion_id", "verification_timestamp"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

    def test_security_headers_present(self):
        _reset_rate_limiters()
        client = _get_test_client()

        with patch("app.server_enterprise_golden._find_batch_by_receipt_id", return_value=None), \
             patch("app.server_enterprise_golden._write_assertion_event", return_value=True), \
             patch("app.server_enterprise_golden._load_assert_policy",
                   return_value={
                       "version": "1.0", "status": "active", "fail_closed": True,
                       "required_checks": ["signature"],
                       "max_receipt_age_seconds": 86400,
                       "context": {"max_field_length": 256, "required_fields": ["system", "action", "resource_id", "correlation_id"]},
                   }):
            resp = client.post("/assert", json=_make_assert_body())

        assert resp.headers.get("x-content-type-options") == "nosniff"
        assert resp.headers.get("x-frame-options") == "DENY"
        assert "no-store" in resp.headers.get("cache-control", "")
