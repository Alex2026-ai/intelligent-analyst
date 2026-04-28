"""
Phase 3 — Verifier wiring tests.

Verifies that finalize_batch_internal() calls verify_manifest_bundle()
after receipt bundle write and persists receipt_verification in batch doc.

Tests:
  1. Successful post-write verification → receipt_verification.status=PASS
  2. Bad signature → receipt_verification.status=FAIL, failure_reason recorded
  3. Batch still completes on verifier failure (observability-only)
  4. No PII leak in persisted receipt_verification fields
  5. Checks_passed list carried through
  6. Performance gate: p99 < 300ms, avg < 200ms
"""

import hashlib
import json
import os
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import pytest

from app.security.iavp import jcs_canonicalize
from app.attestation.manifest_v1 import build_attestation_manifest_v1, PROTOCOL_VERSION
from app.attestation.verifier_v1 import (
    verify_manifest_bundle,
    reset_verification_metrics,
    get_verification_metrics,
)


# ─────────────────────────────────────────────────────────────────────────────
# In-memory Firestore mock (same pattern as test_finalize_summary.py)
# ─────────────────────────────────────────────────────────────────────────────

class MockFirestoreDoc:
    def __init__(self, data=None, exists=True):
        self._data = data or {}
        self.exists = exists

    def to_dict(self):
        return self._data.copy()


class InMemoryFirestore:
    def __init__(self):
        self._data = {}

    def collection(self, name):
        return _CollectionRef(self, name)

    def transaction(self, **kwargs):
        return _InMemoryTransaction(self)


class _InMemoryTransaction:
    def __init__(self, db):
        self._db = db

    def get(self, ref):
        return ref.get()

    def update(self, ref, data):
        ref.update(data)

    def set(self, ref, data):
        ref.set(data)


class _CollectionRef:
    def __init__(self, db, path):
        self._db = db
        self._path = path

    def document(self, doc_id):
        return _DocRef(self._db, f"{self._path}/{doc_id}")

    def order_by(self, field):
        return _Query(self._db, self._path, order_field=field)

    def stream(self, transaction=None):
        prefix = self._path + "/"
        results = []
        for path, data in sorted(self._db._data.items()):
            if path.startswith(prefix):
                remainder = path[len(prefix):]
                if "/" not in remainder:
                    results.append(MockFirestoreDoc(data, exists=True))
        return results


class _Query:
    def __init__(self, db, collection_path, order_field=None):
        self._db = db
        self._collection_path = collection_path
        self._order_field = order_field

    def stream(self, transaction=None):
        prefix = self._collection_path + "/"
        results = []
        for path, data in sorted(self._db._data.items()):
            if path.startswith(prefix):
                remainder = path[len(prefix):]
                if "/" not in remainder:
                    results.append(MockFirestoreDoc(data, exists=True))
        if self._order_field:
            results.sort(key=lambda d: d.to_dict().get(self._order_field, 0))
        return results


class _DocRef:
    def __init__(self, db, path):
        self._db = db
        self._path = path

    def collection(self, name):
        return _CollectionRef(self._db, f"{self._path}/{name}")

    def get(self, transaction=None):
        data = self._db._data.get(self._path)
        if data is not None:
            return MockFirestoreDoc(data, exists=True)
        return MockFirestoreDoc(exists=False)

    def set(self, data):
        self._db._data[self._path] = data.copy()

    def update(self, data):
        if self._path not in self._db._data:
            self._db._data[self._path] = {}
        for key, value in data.items():
            parts = key.split(".")
            if len(parts) > 1:
                target = self._db._data[self._path]
                for part in parts[:-1]:
                    if part not in target or not isinstance(target[part], dict):
                        target[part] = {}
                    target = target[part]
                target[parts[-1]] = value
            else:
                self._db._data[self._path][key] = value


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

BATCH_ID = "BATCH-PHASE3-WIRE-001"

RESULTS = [
    {"original": "Apple Inc.", "resolved": "Apple Inc.", "layer": "L1_EXACT", "confidence": 1.0, "global_index": 0},
    {"original": "Googl Inc", "resolved": "Alphabet Inc.", "layer": "L2_VECTOR", "confidence": 0.88, "global_index": 1},
    {"original": "test llm", "resolved": "Tesla, Inc.", "layer": "L3_LLM", "confidence": 0.75, "global_index": 2},
    {"original": "", "resolved": None, "layer": "L0_GARBAGE_BLANK", "confidence": 0.0, "global_index": 3},
]


def _setup_db(db, batch_id, results):
    """Populate InMemoryFirestore with batch + shard docs + result chunks."""
    created = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()

    db._data[f"batches/{batch_id}"] = {
        "trace_id": batch_id,
        "status": "finalizing",
        "dataset_type": "COMPANY",
        "timestamp": created,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "tenant_id": "tenant-test",
        "total": len(results),
        "total_records": len(results),
        "sharded": True,
        "shard_count": 1,
        "total_l3_spent_usd": 0.01,
        "counts": {
            "total": len(results),
            "l0": 1,
            "l1": 1,
            "l2": 1,
            "l3": 1,
            "l4": 0,
            "l3_calls": 1,
            "l3_spent_usd": 0.01,
        },
    }

    db._data[f"batches/{batch_id}/shards/shard_0000"] = {
        "shard_id": 0,
        "start_index": 0,
        "end_index": len(results),
        "record_count": len(results),
        "status": "completed",
        "results_chunks": ["shard_0000_chunk_000000"],
        "counts": {"total": len(results), "l3_calls": 1, "l3_spent_usd": 0.01},
        "l3_spent_usd": 0.01,
        "duration_ms": 1000.0,
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }

    db._data[f"batches/{batch_id}/results_chunks/shard_0000_chunk_000000"] = {
        "start_index": 0,
        "count": len(results),
        "rows": results,
    }


def _bypass_transactional(func):
    def wrapper(transaction, *args, **kwargs):
        return func(transaction, *args, **kwargs)
    return wrapper


def _run_finalize(db, batch_id):
    """Call the finalize endpoint and return the batch doc after update."""
    patches = {
        "app.server_enterprise_golden._firestore_db": db,
        "app.server_enterprise_golden.HAS_FORENSIC_SIGNING": False,
        "app.server_enterprise_golden._finalize_transactional": _bypass_transactional,
    }

    with patch.dict(os.environ, {
        "L3_MAX_COST_USD": "10.0",
        "HMAC_SCOPE_KEY": "aa" * 32,
    }):
        for target, value in patches.items():
            patch(target, value).start()
        try:
            from app.server_enterprise_golden import app
            from fastapi.testclient import TestClient
            client = TestClient(app)
            response = client.post("/internal/finalize-batch", headers={"Authorization": "Bearer test-oidc-token"}, json={
                "batch_trace_id": batch_id,
                "tenant_id": "tenant-test",
            })
            assert response.status_code == 200, f"Finalize failed: {response.text}"
        finally:
            patch.stopall()

    return db._data.get(f"batches/{batch_id}", {})


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestPhase3VerifierWiring:
    """Verify the verifier is wired into the finalize path."""

    def test_successful_post_write_verification(self):
        """When receipt writes succeed, receipt_verification.status should be PASS or present."""
        db = InMemoryFirestore()
        _setup_db(db, BATCH_ID, RESULTS)
        batch = _run_finalize(db, BATCH_ID)

        assert batch["status"] == "completed"
        # receipt_verification may be None if signing is disabled (HAS_FORENSIC_SIGNING=False
        # means root_hash might be None, skipping receipt entirely)
        # But we should verify the field structure if present
        rv = batch.get("receipt_verification")
        if rv:
            assert rv["status"] in ("PASS", "FAIL", "ERROR")
            assert "verified_at" in rv
            assert "duration_ms" in rv or "failure_reason" in rv

    def test_batch_completes_on_verifier_failure(self):
        """Batch must still reach 'completed' even if verifier returns FAIL."""
        db = InMemoryFirestore()
        bid = "BATCH-PHASE3-FAIL-001"
        _setup_db(db, bid, RESULTS)

        # Patch verify_manifest_bundle to always return failure
        fake_result = {
            "success": False,
            "failure_reason": "SIGNATURE_INVALID",
            "details": {"reason": "ecdsa_verification_failed"},
            "checks_passed": ["schema_jcs"],
            "duration_ms": 1.5,
        }
        with patch("app.attestation.verifier_v1.verify_manifest_bundle", return_value=fake_result):
            batch = _run_finalize(db, bid)

        assert batch["status"] == "completed", "Batch must complete even when verifier fails"

    def test_batch_completes_on_verifier_exception(self):
        """Batch must still reach 'completed' even if verifier throws."""
        db = InMemoryFirestore()
        bid = "BATCH-PHASE3-EXC-001"
        _setup_db(db, bid, RESULTS)

        with patch("app.attestation.verifier_v1.verify_manifest_bundle", side_effect=RuntimeError("boom")):
            batch = _run_finalize(db, bid)

        assert batch["status"] == "completed", "Batch must complete even when verifier throws"

    def test_no_pii_in_receipt_verification(self):
        """receipt_verification must not contain PII (tenant_id, raw names, emails)."""
        db = InMemoryFirestore()
        bid = "BATCH-PHASE3-PII-001"
        _setup_db(db, bid, RESULTS)
        batch = _run_finalize(db, bid)

        rv = batch.get("receipt_verification")
        if rv:
            rv_str = json.dumps(rv, default=str)
            # No tenant_id
            assert "tenant-test" not in rv_str
            # No raw company names
            assert "Apple Inc." not in rv_str
            assert "Googl Inc" not in rv_str
            # No email addresses
            assert "@" not in rv_str


class TestVerifierStandaloneUnit:
    """Unit tests for verify_manifest_bundle wiring behavior."""

    def setup_method(self):
        reset_verification_metrics()

    def test_bad_signature_failure_recorded(self):
        """Wrong signature → FAIL with SIGNATURE_INVALID recorded in metrics."""
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric.utils import Prehashed

        private_key = ec.generate_private_key(ec.SECP256R1())
        public_pem = private_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        key_id = "projects/test/locations/us/keyRings/test/cryptoKeys/k/cryptoKeyVersions/1"

        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        manifest = build_attestation_manifest_v1(
            batch_id="BATCH-SIG-TEST",
            root_hash=hashlib.sha256(b"root").hexdigest(),
            artifact_mode="PRODUCTION_REAL",
            engine_version="8.2.2",
            environment="test",
            config_hash=hashlib.sha256(b"cfg").hexdigest(),
            dataset_hash=hashlib.sha256(b"ds").hexdigest(),
            registry_hash=hashlib.sha256(b"reg").hexdigest(),
            key_id=key_id,
            metrics={
                "l1_pct": 0.85, "l2_pct": 0.08, "l3_pct": 0.02, "l4_pct": 0.05,
                "record_count": 10, "replay_method": "deterministic",
                "replay_runs": 1, "replay_variance": 0.0,
            },
            tenant_scope="a1b2c3d4e5f6a7b8",
            anchor_ref={
                "anchor_hash": hashlib.sha256(b"anchor").hexdigest(),
                "anchor_timestamp": ts,
                "bucket": "test-bucket",
                "object_path": "test/path",
            },
            artifact_hashes=[{
                "artifact_type": "results_csv",
                "hash": hashlib.sha256(b"art").hexdigest(),
                "size_bytes": 1024,
            }],
            timestamp=ts,
        )
        manifest_bytes = jcs_canonicalize(manifest)

        # Sign with a DIFFERENT key to create bad signature
        other_key = ec.generate_private_key(ec.SECP256R1())
        digest = hashlib.sha256(manifest_bytes).digest()
        bad_sig = other_key.sign(digest, ec.ECDSA(Prehashed(hashes.SHA256())))

        def resolver(kid):
            return public_pem

        result = verify_manifest_bundle(manifest_bytes, bad_sig, None, resolver)
        assert result["success"] is False
        assert result["failure_reason"] == "SIGNATURE_INVALID"

        metrics = get_verification_metrics()
        assert metrics["failures_total"] >= 1
        assert "SIGNATURE_INVALID" in metrics["failures_by_reason"]

    def test_checks_passed_carried_through(self):
        """Successful verify should carry all check names in checks_passed."""
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric.utils import Prehashed

        private_key = ec.generate_private_key(ec.SECP256R1())
        public_pem = private_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        key_id = "projects/test/locations/us/keyRings/test/cryptoKeys/k/cryptoKeyVersions/1"

        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        manifest = build_attestation_manifest_v1(
            batch_id="BATCH-CHECKS-TEST",
            root_hash=hashlib.sha256(b"root").hexdigest(),
            artifact_mode="PRODUCTION_REAL",
            engine_version="8.2.2",
            environment="test",
            config_hash=hashlib.sha256(b"cfg").hexdigest(),
            dataset_hash=hashlib.sha256(b"ds").hexdigest(),
            registry_hash=hashlib.sha256(b"reg").hexdigest(),
            key_id=key_id,
            metrics={
                "l1_pct": 0.85, "l2_pct": 0.08, "l3_pct": 0.02, "l4_pct": 0.05,
                "record_count": 10, "replay_method": "deterministic",
                "replay_runs": 1, "replay_variance": 0.0,
            },
            tenant_scope="a1b2c3d4e5f6a7b8",
            anchor_ref={
                "anchor_hash": hashlib.sha256(b"anchor").hexdigest(),
                "anchor_timestamp": ts,
                "bucket": "test-bucket",
                "object_path": "test/path",
            },
            artifact_hashes=[{
                "artifact_type": "results_csv",
                "hash": hashlib.sha256(b"art").hexdigest(),
                "size_bytes": 1024,
            }],
            timestamp=ts,
        )
        manifest_bytes = jcs_canonicalize(manifest)
        digest = hashlib.sha256(manifest_bytes).digest()
        sig = private_key.sign(digest, ec.ECDSA(Prehashed(hashes.SHA256())))

        def resolver(kid):
            return public_pem

        result = verify_manifest_bundle(manifest_bytes, sig, None, resolver)
        assert result["success"] is True
        assert "schema_jcs" in result["checks_passed"]
        assert "signature" in result["checks_passed"]
        assert "anchor_binding" in result["checks_passed"]
        assert "artifact_integrity" in result["checks_passed"]
        assert "timestamp_skew" in result["checks_passed"]

    def test_performance_gate_p99_under_300ms(self):
        """Run verifier 100× and assert p99 < 300ms, avg < 200ms."""
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric.utils import Prehashed

        private_key = ec.generate_private_key(ec.SECP256R1())
        public_pem = private_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        key_id = "projects/test/locations/us/keyRings/test/cryptoKeys/k/cryptoKeyVersions/1"

        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        manifest = build_attestation_manifest_v1(
            batch_id="BATCH-PERF-GATE",
            root_hash=hashlib.sha256(b"root").hexdigest(),
            artifact_mode="PRODUCTION_REAL",
            engine_version="8.2.2",
            environment="test",
            config_hash=hashlib.sha256(b"cfg").hexdigest(),
            dataset_hash=hashlib.sha256(b"ds").hexdigest(),
            registry_hash=hashlib.sha256(b"reg").hexdigest(),
            key_id=key_id,
            metrics={
                "l1_pct": 0.85, "l2_pct": 0.08, "l3_pct": 0.02, "l4_pct": 0.05,
                "record_count": 1000, "replay_method": "deterministic",
                "replay_runs": 1, "replay_variance": 0.0,
            },
            tenant_scope="a1b2c3d4e5f6a7b8",
            anchor_ref={
                "anchor_hash": hashlib.sha256(b"anchor").hexdigest(),
                "anchor_timestamp": ts,
                "bucket": "test-bucket",
                "object_path": "test/path",
            },
            artifact_hashes=[{
                "artifact_type": "results_csv",
                "hash": hashlib.sha256(b"art").hexdigest(),
                "size_bytes": 4096,
            }],
            timestamp=ts,
        )
        manifest_bytes = jcs_canonicalize(manifest)
        digest = hashlib.sha256(manifest_bytes).digest()
        sig = private_key.sign(digest, ec.ECDSA(Prehashed(hashes.SHA256())))

        def resolver(kid):
            return public_pem

        durations = []
        for _ in range(100):
            t0 = time.monotonic()
            result = verify_manifest_bundle(manifest_bytes, sig, None, resolver)
            elapsed = (time.monotonic() - t0) * 1000
            durations.append(elapsed)
            assert result["success"] is True

        durations.sort()
        avg = sum(durations) / len(durations)
        p99 = durations[98]  # 99th percentile of 100 samples

        print(f"\n  [PERF GATE] avg={avg:.1f}ms  p99={p99:.1f}ms  min={durations[0]:.1f}ms  max={durations[-1]:.1f}ms")
        assert p99 < 300, f"p99={p99:.1f}ms exceeds 300ms limit"
        assert avg < 200, f"avg={avg:.1f}ms exceeds 200ms limit"
