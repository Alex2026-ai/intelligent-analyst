"""
Tests for Attestation Manifest v1 — Phase 1A.

Covers:
- dataset hash determinism (SHA256 of JCS array)
- tenant scope uses HMAC, not raw SHA-256
- manifest has exact required fields
- manifest key order is canonical / sorted
- protocol_version fixed to ia-attestation/v1
- source_blob_hash is null for JSON batch path
- field validation fails closed if required inputs missing
"""

import hashlib
import hmac
import json
import os
import uuid

import pytest

# Ensure HMAC_SCOPE_KEY is not required for import
os.environ.setdefault("HMAC_SCOPE_KEY", "aa" * 32)

from app.utils.hashing import (
    compute_dataset_hash_v1,
    compute_tenant_scope,
    compute_source_blob_hash,
)
from app.attestation.manifest_v1 import (
    PROTOCOL_VERSION,
    SIGNATURE_ALGORITHM,
    build_attestation_manifest_v1,
    manifest_to_public_projection,
)
from app.security.iavp import jcs_canonicalize


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TEST_SCOPE_KEY = bytes.fromhex("bb" * 32)

VALID_ANCHOR_REF = {
    "anchor_hash": "a" * 64,
    "anchor_timestamp": "2026-03-13T00:00:00.000000Z",
    "bucket": "ia-anchor-test",
    "object_path": "anchors/abc123/BATCH-TEST0001.json",
}

VALID_METRICS = {
    "l1_pct": 0.85,
    "l2_pct": 0.08,
    "l3_pct": 0.02,
    "l4_pct": 0.05,
    "record_count": 100,
    "replay_method": "STABLE_INPUT_ORDER_V2",
    "replay_runs": 3,
    "replay_variance": 0,
}

VALID_ARTIFACT_HASHES = [
    {"artifact_type": "evidence_pack", "hash": "b" * 64, "size_bytes": 1024},
]


def _make_manifest(**overrides):
    """Build a valid manifest with optional field overrides."""
    defaults = dict(
        batch_id="BATCH-TEST0001",
        root_hash="c" * 64,
        artifact_mode="PRODUCTION_REAL",
        engine_version="8.2.2",
        environment="prod",
        config_hash="d" * 64,
        dataset_hash="e" * 64,
        registry_hash="f" * 64,
        key_id="projects/test/locations/us/keyRings/kr/cryptoKeys/k/cryptoKeyVersions/1",
        metrics=VALID_METRICS,
        tenant_scope="a1b2c3d4e5f6a7b8",
        anchor_ref=VALID_ANCHOR_REF,
        artifact_hashes=VALID_ARTIFACT_HASHES,
        receipt_id="00000000-0000-4000-8000-000000000001",
        timestamp="2026-03-13T00:00:00.000000Z",
    )
    defaults.update(overrides)
    return build_attestation_manifest_v1(**defaults)


# ---------------------------------------------------------------------------
# Dataset hash tests
# ---------------------------------------------------------------------------

class TestDatasetHash:
    """dataset_hash = SHA256( JCS( sorted_originals_array ) )"""

    def test_deterministic_same_order(self):
        """Same inputs in same order produce same hash."""
        records = [
            {"original": "Microsoft Corp", "row_index": 0, "source_timestamp": "2026-01-01T00:00:00.000000Z"},
            {"original": "Apple Inc", "row_index": 1, "source_timestamp": "2026-01-01T00:00:00.000000Z"},
        ]
        h1 = compute_dataset_hash_v1(records)
        h2 = compute_dataset_hash_v1(records)
        assert h1 == h2
        assert len(h1) == 64

    def test_different_order_different_hash(self):
        """Reordering inputs changes the hash (order-sensitive)."""
        records_a = [
            {"original": "Microsoft Corp", "row_index": 0, "source_timestamp": "2026-01-01T00:00:00.000000Z"},
            {"original": "Apple Inc", "row_index": 1, "source_timestamp": "2026-01-01T00:00:00.000000Z"},
        ]
        records_b = [
            {"original": "Apple Inc", "row_index": 0, "source_timestamp": "2026-01-01T00:00:00.000000Z"},
            {"original": "Microsoft Corp", "row_index": 1, "source_timestamp": "2026-01-01T00:00:00.000000Z"},
        ]
        # Both get sorted by STABLE_INPUT_ORDER_V2, but with different row_index
        # assignments the sort may or may not differ. Use different timestamps
        # to guarantee different sort order.
        records_c = [
            {"original": "Microsoft Corp", "row_index": 0, "source_timestamp": "2026-01-02T00:00:00.000000Z"},
            {"original": "Apple Inc", "row_index": 1, "source_timestamp": "2026-01-01T00:00:00.000000Z"},
        ]
        records_d = [
            {"original": "Apple Inc", "row_index": 0, "source_timestamp": "2026-01-02T00:00:00.000000Z"},
            {"original": "Microsoft Corp", "row_index": 1, "source_timestamp": "2026-01-01T00:00:00.000000Z"},
        ]
        h_c = compute_dataset_hash_v1(records_c)
        h_d = compute_dataset_hash_v1(records_d)
        assert h_c != h_d

    def test_uses_jcs_not_newline(self):
        """dataset_hash is SHA256(JCS(array)), not SHA256(newline-joined)."""
        records = [
            {"original": "Acme Corp", "row_index": 0, "source_timestamp": "2026-01-01T00:00:00.000000Z"},
            {"original": "Beta LLC", "row_index": 1, "source_timestamp": "2026-01-01T00:00:00.000000Z"},
        ]
        h = compute_dataset_hash_v1(records)

        # Manually compute expected: sort, extract originals, JCS, SHA256
        from app.security.iavp import sort_records_stable_order
        sorted_recs, _ = sort_records_stable_order(records)
        originals = [str(r.get("original", "")) for r in sorted_recs]
        expected_bytes = jcs_canonicalize(originals)
        expected_hash = hashlib.sha256(expected_bytes).hexdigest().lower()
        assert h == expected_hash

        # Confirm it does NOT match the old newline-join method
        newline_hash = hashlib.sha256("\n".join(originals).encode("utf-8")).hexdigest().lower()
        assert h != newline_hash

    def test_empty_records(self):
        """Empty input produces SHA256(JCS([]))."""
        h = compute_dataset_hash_v1([])
        expected = hashlib.sha256(jcs_canonicalize([])).hexdigest().lower()
        assert h == expected

    def test_format_independent(self):
        """Same logical data from different formats produces same hash."""
        # Simulate CSV vs JSON upload — same original strings, same timestamps
        csv_records = [
            {"original": "Alpha", "row_index": 0, "source_timestamp": "2026-01-01T00:00:00.000000Z", "source": "csv"},
            {"original": "Beta", "row_index": 1, "source_timestamp": "2026-01-01T00:00:00.000000Z", "source": "csv"},
        ]
        json_records = [
            {"original": "Alpha", "row_index": 0, "source_timestamp": "2026-01-01T00:00:00.000000Z", "source": "json"},
            {"original": "Beta", "row_index": 1, "source_timestamp": "2026-01-01T00:00:00.000000Z", "source": "json"},
        ]
        assert compute_dataset_hash_v1(csv_records) == compute_dataset_hash_v1(json_records)


# ---------------------------------------------------------------------------
# Tenant scope tests
# ---------------------------------------------------------------------------

class TestTenantScope:
    """tenant_scope = HMAC-SHA256(scope_key, tenant_id)[:16]"""

    def test_uses_hmac_not_sha256(self):
        """tenant_scope must NOT match raw SHA-256(tenant_id)[:16]."""
        tenant_id = "tenant_20bd8f2d2287faee"
        scope = compute_tenant_scope(tenant_id, scope_key=TEST_SCOPE_KEY)

        raw_sha = hashlib.sha256(tenant_id.encode("utf-8")).hexdigest()[:16]
        assert scope != raw_sha
        assert len(scope) == 16

    def test_hmac_matches_stdlib(self):
        """Output matches direct hmac.new computation."""
        tenant_id = "tenant_abc123"
        scope = compute_tenant_scope(tenant_id, scope_key=TEST_SCOPE_KEY)

        expected = hmac.new(
            TEST_SCOPE_KEY, tenant_id.encode("utf-8"), hashlib.sha256
        ).hexdigest()[:16]
        assert scope == expected

    def test_different_keys_different_scope(self):
        """Different scope_key → different tenant_scope for same tenant."""
        tenant_id = "tenant_same"
        key_a = bytes.fromhex("aa" * 32)
        key_b = bytes.fromhex("cc" * 32)

        scope_a = compute_tenant_scope(tenant_id, scope_key=key_a)
        scope_b = compute_tenant_scope(tenant_id, scope_key=key_b)
        assert scope_a != scope_b

    def test_stable_same_key(self):
        """Same tenant + same key → same scope (deterministic)."""
        tenant_id = "tenant_stable"
        s1 = compute_tenant_scope(tenant_id, scope_key=TEST_SCOPE_KEY)
        s2 = compute_tenant_scope(tenant_id, scope_key=TEST_SCOPE_KEY)
        assert s1 == s2

    def test_requires_scope_key(self):
        """Raises ValueError if no scope_key and no env var."""
        env_backup = os.environ.pop("HMAC_SCOPE_KEY", None)
        try:
            with pytest.raises(ValueError, match="HMAC_SCOPE_KEY"):
                compute_tenant_scope("tenant_x", scope_key=None)
        finally:
            if env_backup is not None:
                os.environ["HMAC_SCOPE_KEY"] = env_backup

    def test_reads_env_var(self):
        """Reads HMAC_SCOPE_KEY from env when scope_key not passed."""
        key_hex = "dd" * 32
        os.environ["HMAC_SCOPE_KEY"] = key_hex
        try:
            scope = compute_tenant_scope("tenant_env", scope_key=None)
            expected = hmac.new(
                bytes.fromhex(key_hex), b"tenant_env", hashlib.sha256
            ).hexdigest()[:16]
            assert scope == expected
        finally:
            os.environ["HMAC_SCOPE_KEY"] = "aa" * 32  # restore default


# ---------------------------------------------------------------------------
# Manifest builder tests
# ---------------------------------------------------------------------------

class TestManifestBuilder:
    """build_attestation_manifest_v1() output shape and constraints."""

    def test_exact_field_count(self):
        """Manifest has exactly 18 fields (17 required + 1 optional)."""
        m = _make_manifest()
        assert len(m) == 18

    def test_all_required_fields_present(self):
        """All 17 required fields are present."""
        m = _make_manifest()
        required = {
            "anchor_ref", "artifact_hashes", "artifact_mode", "batch_id",
            "config_hash", "dataset_hash", "engine_version", "environment",
            "key_id", "metrics", "protocol_version", "receipt_id",
            "registry_hash", "root_hash", "signature_algorithm",
            "tenant_scope", "timestamp",
        }
        assert required.issubset(set(m.keys()))

    def test_source_blob_hash_present(self):
        """source_blob_hash is always in the manifest (null or string)."""
        m = _make_manifest()
        assert "source_blob_hash" in m

    def test_key_order_is_canonical(self):
        """Keys are in lexicographic (sorted) order — JCS requirement."""
        m = _make_manifest()
        assert list(m.keys()) == sorted(m.keys())

    def test_protocol_version_fixed(self):
        """protocol_version is always ia-attestation/v1."""
        m = _make_manifest()
        assert m["protocol_version"] == "ia-attestation/v1"

    def test_signature_algorithm_fixed(self):
        """signature_algorithm is always EC_SIGN_P256_SHA256."""
        m = _make_manifest()
        assert m["signature_algorithm"] == "EC_SIGN_P256_SHA256"

    def test_source_blob_hash_null_for_json_batch(self):
        """source_blob_hash is None (serialized as null) when no file uploaded."""
        m = _make_manifest(source_blob_hash=None)
        assert m["source_blob_hash"] is None

    def test_source_blob_hash_set_when_provided(self):
        """source_blob_hash carries the hash when file was uploaded."""
        h = "ab" * 32
        m = _make_manifest(source_blob_hash=h)
        assert m["source_blob_hash"] == h

    def test_auto_generates_receipt_id(self):
        """receipt_id is auto-generated UUID v4 when not provided."""
        m = _make_manifest(receipt_id=None)
        parsed = uuid.UUID(m["receipt_id"])
        assert parsed.version == 4

    def test_auto_generates_timestamp(self):
        """timestamp is auto-generated RFC 3339 when not provided."""
        m = _make_manifest(timestamp=None)
        assert m["timestamp"].endswith("Z")
        assert "T" in m["timestamp"]

    def test_jcs_canonical_bytes_are_deterministic(self):
        """Same manifest → same JCS bytes → same hash."""
        m1 = _make_manifest()
        m2 = _make_manifest()
        b1 = jcs_canonicalize(m1)
        b2 = jcs_canonicalize(m2)
        assert b1 == b2
        assert hashlib.sha256(b1).hexdigest() == hashlib.sha256(b2).hexdigest()


# ---------------------------------------------------------------------------
# Validation tests (fail closed)
# ---------------------------------------------------------------------------

class TestManifestValidation:
    """Validation fails closed if required inputs are missing or invalid."""

    def test_missing_batch_id(self):
        with pytest.raises(ValueError, match="batch_id"):
            _make_manifest(batch_id="")

    def test_invalid_root_hash_length(self):
        with pytest.raises(ValueError, match="root_hash"):
            _make_manifest(root_hash="abc")

    def test_invalid_artifact_mode(self):
        with pytest.raises(ValueError, match="artifact_mode"):
            _make_manifest(artifact_mode="INVALID")

    def test_invalid_environment(self):
        with pytest.raises(ValueError, match="environment"):
            _make_manifest(environment="staging")

    def test_invalid_config_hash(self):
        with pytest.raises(ValueError, match="config_hash"):
            _make_manifest(config_hash="short")

    def test_invalid_dataset_hash(self):
        with pytest.raises(ValueError, match="dataset_hash"):
            _make_manifest(dataset_hash="short")

    def test_invalid_registry_hash(self):
        with pytest.raises(ValueError, match="registry_hash"):
            _make_manifest(registry_hash="")

    def test_missing_key_id(self):
        with pytest.raises(ValueError, match="key_id"):
            _make_manifest(key_id="")

    def test_invalid_tenant_scope_length(self):
        with pytest.raises(ValueError, match="tenant_scope"):
            _make_manifest(tenant_scope="abc")

    def test_missing_engine_version(self):
        with pytest.raises(ValueError, match="engine_version"):
            _make_manifest(engine_version="")

    def test_missing_metrics_key(self):
        bad_metrics = {"l1_pct": 0.85}  # missing required keys
        with pytest.raises(ValueError, match="metrics missing"):
            _make_manifest(metrics=bad_metrics)

    def test_missing_anchor_ref_key(self):
        bad_anchor = {"anchor_hash": "a" * 64}  # missing required keys
        with pytest.raises(ValueError, match="anchor_ref missing"):
            _make_manifest(anchor_ref=bad_anchor)

    def test_missing_artifact_hash_key(self):
        bad_artifacts = [{"artifact_type": "test"}]  # missing hash, size_bytes
        with pytest.raises(ValueError, match="artifact_hashes.*missing"):
            _make_manifest(artifact_hashes=bad_artifacts)


# ---------------------------------------------------------------------------
# Public projection tests
# ---------------------------------------------------------------------------

class TestPublicProjection:
    """manifest_to_public_projection() redacts infrastructure fields."""

    def test_redacts_bucket(self):
        m = _make_manifest()
        pub = manifest_to_public_projection(m)
        assert "bucket" not in pub["anchor_ref"]

    def test_redacts_object_path(self):
        m = _make_manifest()
        pub = manifest_to_public_projection(m)
        assert "object_path" not in pub["anchor_ref"]

    def test_keeps_anchor_hash(self):
        m = _make_manifest()
        pub = manifest_to_public_projection(m)
        assert "anchor_hash" in pub["anchor_ref"]
        assert pub["anchor_ref"]["anchor_hash"] == m["anchor_ref"]["anchor_hash"]

    def test_keeps_anchor_timestamp(self):
        m = _make_manifest()
        pub = manifest_to_public_projection(m)
        assert "anchor_timestamp" in pub["anchor_ref"]

    def test_redacts_key_id(self):
        m = _make_manifest()
        pub = manifest_to_public_projection(m)
        assert "key_id" not in pub

    def test_preserves_all_other_fields(self):
        m = _make_manifest()
        pub = manifest_to_public_projection(m)
        # All fields except key_id should be present
        for key in m:
            if key == "key_id":
                assert key not in pub
            else:
                assert key in pub


# ---------------------------------------------------------------------------
# Source blob hash test
# ---------------------------------------------------------------------------

class TestSourceBlobHash:
    def test_compute_source_blob_hash(self):
        data = b"hello world CSV data"
        h = compute_source_blob_hash(data)
        assert h == hashlib.sha256(data).hexdigest().lower()
        assert len(h) == 64
