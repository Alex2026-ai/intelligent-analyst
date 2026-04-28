"""
Day 5 Contract Tests — Version Snapshot, Margin Telemetry, Tenant Binding

Verifies:
- _build_version_snapshot() returns all required keys with non-empty values
- ROUTER_VERSION / MODEL_MAPPING_VERSION constants
- /admin/batch-economics/{trace_id} endpoint access control and field contract
- build_attestation_payload() / build_iavp_manifest() accept tenant_id_hash
"""

import hashlib
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# 1. Version snapshot tests
# ---------------------------------------------------------------------------


def test_version_snapshot_has_all_keys():
    """_build_version_snapshot() returns all 10 required keys."""
    from app.server_enterprise_golden import _build_version_snapshot
    snap = _build_version_snapshot()

    expected_keys = {
        "protocol_version",
        "router_version",
        "model_mapping_version",
        "config_hash",
        "engine_commit_hash",
        "engine_version",
        "embedding_model_id",
        "llm_model_id",
        "canonical_dataset_hash",
    }
    assert expected_keys.issubset(set(snap.keys())), (
        f"Missing keys: {expected_keys - set(snap.keys())}"
    )


def test_version_snapshot_values_non_empty():
    """All values in version snapshot are non-empty strings."""
    from app.server_enterprise_golden import _build_version_snapshot
    snap = _build_version_snapshot()
    for key, value in snap.items():
        assert isinstance(value, str), f"{key} is not a string: {type(value)}"
        assert len(value) > 0, f"{key} is empty"


# ---------------------------------------------------------------------------
# 2. Router / model mapping version constants
# ---------------------------------------------------------------------------


def test_router_version_constant():
    from app.server_enterprise_golden import ROUTER_VERSION
    assert ROUTER_VERSION == "v1-static"


def test_model_mapping_constant():
    from app.server_enterprise_golden import MODEL_MAPPING_VERSION
    assert MODEL_MAPPING_VERSION == "v1-static"


# ---------------------------------------------------------------------------
# 3. Batch economics endpoint
# ---------------------------------------------------------------------------


def test_batch_economics_requires_admin():
    """Non-admin GET → 401/403."""
    from app.server_enterprise_golden import app

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get(
        "/admin/batch-economics/BATCH-FAKE",
        headers={"X-API-Key": "invalid-key"},
    )
    assert resp.status_code in (401, 403)


def _admin_override():
    return {"role": "admin"}


def test_batch_economics_not_found():
    """Missing batch → 404 (with mocked admin auth + Firestore)."""
    from app.server_enterprise_golden import app, require_admin_role

    mock_doc = MagicMock()
    mock_doc.exists = False

    mock_collection = MagicMock()
    mock_collection.document.return_value.get.return_value = mock_doc

    mock_db = MagicMock()
    mock_db.collection.return_value = mock_collection

    app.dependency_overrides[require_admin_role] = _admin_override
    try:
        with patch("app.server_enterprise_golden._firestore_db", mock_db):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/admin/batch-economics/BATCH-NONEXISTENT-12345")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.pop(require_admin_role, None)


def test_batch_economics_returns_fields():
    """Admin GET with mocked Firestore → all margin fields present."""
    from app.server_enterprise_golden import app, require_admin_role

    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc.to_dict.return_value = {
        "total": 1000,
        "total_records": 1000,
        "cost": 5.0,
        "counts": {
            "l0_quarantined": 10,
            "l1_resolved": 800,
            "l2_resolved": 100,
            "l3_resolved": 50,
            "l3_attempted": 200,
            "l4_flagged": 40,
        },
    }

    mock_collection = MagicMock()
    mock_collection.document.return_value.get.return_value = mock_doc

    mock_db = MagicMock()
    mock_db.collection.return_value = mock_collection

    app.dependency_overrides[require_admin_role] = _admin_override
    try:
        with patch("app.server_enterprise_golden._firestore_db", mock_db):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/admin/batch-economics/BATCH-TEST123")

        assert resp.status_code == 200
        data = resp.json()
        assert "trace_id" in data
        assert "batch_total_cost" in data
        assert "total_records" in data
        assert "l3_cost_per_record" in data
        assert "l3_calls" in data
        assert "l3_cost_per_call" in data
        assert "estimated_margin_per_record" in data
        assert "layer_distribution" in data
        ld = data["layer_distribution"]
        assert all(k in ld for k in ("l0", "l1", "l2", "l3", "l4"))
    finally:
        app.dependency_overrides.pop(require_admin_role, None)


# ---------------------------------------------------------------------------
# 4. Attestation payload + manifest — tenant_id_hash
# ---------------------------------------------------------------------------


def test_attestation_payload_version_bumped():
    """ATTESTATION_PAYLOAD_VERSION == 1.2 (bumped from 1.1 to canonicalize lowercase env values)."""
    from app.security.iavp import ATTESTATION_PAYLOAD_VERSION
    assert ATTESTATION_PAYLOAD_VERSION == "1.2"


def test_attestation_payload_includes_tenant_hash():
    """tenant_id_hash_sha256 is present when passed."""
    from app.security.iavp import build_attestation_payload

    payload = build_attestation_payload(
        batch_id="BATCH-TEST",
        root_hash="abc123",
        artifact_mode="PRODUCTION_REAL",
        engine_version="3.0.0",
        environment="test",
        protocol_version="IA-VP-1.0",
        config_hash="cfghash",
        dataset_hash="dshash",
        key_id="key-1",
        metrics_hash="mhash",
        record_count=100,
        signed_at_utc="2026-02-23T00:00:00.000000Z",
        tenant_id_hash="abcdef0123456789",
    )
    assert payload["tenant_id_hash_sha256"] == "abcdef0123456789"


def test_attestation_payload_backward_compat():
    """Works without tenant_id_hash (defaults to None)."""
    from app.security.iavp import build_attestation_payload

    payload = build_attestation_payload(
        batch_id="BATCH-TEST",
        root_hash="abc123",
        artifact_mode="PRODUCTION_REAL",
        engine_version="3.0.0",
        environment="test",
        protocol_version="IA-VP-1.0",
        config_hash="cfghash",
        dataset_hash="dshash",
        key_id="key-1",
        metrics_hash="mhash",
        record_count=100,
        signed_at_utc="2026-02-23T00:00:00.000000Z",
    )
    assert payload["tenant_id_hash_sha256"] is None


def test_manifest_includes_tenant_hash():
    """build_iavp_manifest includes tenant_id_hash_sha256 when passed."""
    from app.security.iavp import build_iavp_manifest, ReplayVerificationResult

    replay = ReplayVerificationResult()
    replay.add_run("fakehash")

    manifest = build_iavp_manifest(
        batch_id="BATCH-TEST",
        artifact_type="BATCH_ATTESTATION",
        artifact_mode="PRODUCTION_REAL",
        engine_version="3.0.0",
        config_hash="cfghash",
        dataset_hash="dshash",
        root_hash="roothash",
        record_count=100,
        metrics={"l1_pct": 80.0, "l2_pct": 10.0, "l3_pct": 5.0, "l4_pct": 5.0},
        replay_result=replay,
        key_id="key-1",
        pubkey_fingerprint="fp-1",
        tenant_id_hash="abcdef0123456789",
    )
    assert manifest["tenant_id_hash_sha256"] == "abcdef0123456789"
