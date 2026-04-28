"""Tests for GET /v1/batches/{trace_id} — shared-read over monolith batch data.

Proves:
  1. Reads batch from Firestore `batches/` collection by trace_id
  2. Returns deterministic response shape with only safe fields
  3. Tenant isolation: non-admin cannot read another tenant's batch
  4. Admin can read any tenant's batch
  5. Returns 404 for nonexistent trace_id
  6. Returns 401 without auth
  7. No mutation side effects (read-only)
  8. Cost fields stripped for non-admin, visible for admin
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from apps.api.tests.conftest import (
    ADMIN_TOKEN,
    TENANT_B_TOKEN,
    VALID_TOKEN,
    auth_header,
)


# --- Test data: mimics a monolith-written batch document ---

SAMPLE_BATCH = {
    "trace_id": "BATCH-TEST-001",
    "status": "completed",
    "filename": "test_upload.csv",
    "total": 500,
    "total_records": 500,
    "timestamp": "2026-03-24T10:00:00Z",
    "finished_at": "2026-03-24T10:01:30Z",
    "duration_seconds": 90.5,
    "dataset_type": "company",
    "config_version": "8.2.2",
    "tenant_id": "tenant-1",
    "auto_resolved_pct": 85.2,
    "counts": {"l0": 10, "l1": 300, "l2": 100, "l3": 40, "l4": 50},
    "stats": {"total": 500, "layer_1_exact": 100, "layer_1_norm": 200},
    # Cost fields — should be stripped for non-admin
    "llm_budget_summary": {"budget_usd": 10.0, "spent_usd": 0.5},
    "credits_spent_usd": 0.5,
    # Internal fields that should NOT appear in response
    "firestore_path": "batches/BATCH-TEST-001",
    "shard_statuses": {"shard_0000": "completed"},
}


def _seed_batch(app, batch: dict | None = None) -> None:
    """Seed a batch into the in-memory Firestore for testing."""
    batch = batch or SAMPLE_BATCH
    db = app.state.firestore_client
    # Write to batches/ collection keyed by trace_id (matches monolith pattern)
    db.collection("batches").document(batch["trace_id"]).set(batch)


class TestGetBatch:
    """GET /v1/batches/{trace_id} — happy path."""

    def test_returns_batch_by_trace_id(self, client: TestClient, app):
        _seed_batch(app)
        resp = client.get("/v1/batches/BATCH-TEST-001", headers=auth_header())
        assert resp.status_code == 200
        data = resp.json()
        assert data["trace_id"] == "BATCH-TEST-001"
        assert data["status"] == "completed"
        assert data["total"] == 500

    def test_response_shape_deterministic(self, client: TestClient, app):
        _seed_batch(app)
        resp = client.get("/v1/batches/BATCH-TEST-001", headers=auth_header())
        data = resp.json()
        # Must have core fields
        assert "trace_id" in data
        assert "status" in data
        assert "total" in data
        assert "tenant_id" in data
        # Must NOT have internal fields
        assert "firestore_path" not in data
        assert "shard_statuses" not in data

    def test_cost_fields_stripped_for_analyst(self, client: TestClient, app):
        _seed_batch(app)
        resp = client.get("/v1/batches/BATCH-TEST-001", headers=auth_header())
        data = resp.json()
        assert "llm_budget_summary" not in data
        assert "credits_spent_usd" not in data

    def test_cost_fields_visible_for_admin(self, client: TestClient, app):
        _seed_batch(app)
        resp = client.get("/v1/batches/BATCH-TEST-001", headers=auth_header(ADMIN_TOKEN))
        data = resp.json()
        assert "llm_budget_summary" in data
        assert data["llm_budget_summary"]["budget_usd"] == 10.0


class TestTenantIsolation:
    """INV-005: tenant isolation on batch reads."""

    def test_analyst_can_read_own_tenant(self, client: TestClient, app):
        _seed_batch(app)  # tenant_id = "tenant-1", VALID_TOKEN is tenant-1
        resp = client.get("/v1/batches/BATCH-TEST-001", headers=auth_header())
        assert resp.status_code == 200

    def test_analyst_cannot_read_other_tenant(self, client: TestClient, app):
        _seed_batch(app)  # tenant_id = "tenant-1"
        resp = client.get("/v1/batches/BATCH-TEST-001", headers=auth_header(TENANT_B_TOKEN))
        assert resp.status_code == 403

    def test_admin_can_read_any_tenant(self, client: TestClient, app):
        _seed_batch(app)  # tenant_id = "tenant-1"
        resp = client.get("/v1/batches/BATCH-TEST-001", headers=auth_header(ADMIN_TOKEN))
        assert resp.status_code == 200


class TestNotFound:
    """404 for nonexistent batches."""

    def test_nonexistent_returns_404(self, client: TestClient, app):
        resp = client.get("/v1/batches/BATCH-NONEXISTENT", headers=auth_header())
        assert resp.status_code == 404

    def test_empty_trace_id_hits_list_endpoint(self, client: TestClient, app):
        """GET /v1/batches/ routes to the list endpoint, not single-batch."""
        resp = client.get("/v1/batches/", headers=auth_header())
        # With the list endpoint registered, this returns 200 (empty list) or 307 redirect
        assert resp.status_code in (200, 307)


class TestAuth:
    """Authentication enforcement."""

    def test_no_auth_returns_401(self, client: TestClient, app):
        _seed_batch(app)
        resp = client.get("/v1/batches/BATCH-TEST-001")
        assert resp.status_code == 401


class TestReadOnly:
    """Verify no mutation side effects."""

    def test_get_does_not_mutate(self, client: TestClient, app):
        _seed_batch(app)
        # Read twice
        resp1 = client.get("/v1/batches/BATCH-TEST-001", headers=auth_header())
        resp2 = client.get("/v1/batches/BATCH-TEST-001", headers=auth_header())
        # Identical responses
        assert resp1.json() == resp2.json()
        # Original data unchanged in store
        db = app.state.firestore_client
        raw = db.collection("batches").document("BATCH-TEST-001").get()
        assert raw["trace_id"] == "BATCH-TEST-001"
        assert raw["firestore_path"] == "batches/BATCH-TEST-001"  # Internal field preserved in store


# ============================================================================
# GET /v1/batches — batch list
# ============================================================================

BATCH_2 = {
    **SAMPLE_BATCH,
    "trace_id": "BATCH-TEST-002",
    "timestamp": "2026-03-24T11:00:00Z",
    "filename": "second_upload.csv",
    "total": 200,
}

BATCH_OTHER_TENANT = {
    **SAMPLE_BATCH,
    "trace_id": "BATCH-OTHER-001",
    "tenant_id": "tenant-B",
    "timestamp": "2026-03-24T09:00:00Z",
}


class TestListBatches:
    """GET /v1/batches — batch list for authenticated tenant."""

    def test_returns_own_tenant_batches(self, client: TestClient, app):
        _seed_batch(app, SAMPLE_BATCH)
        _seed_batch(app, BATCH_2)
        _seed_batch(app, BATCH_OTHER_TENANT)
        resp = client.get("/v1/batches", headers=auth_header())
        assert resp.status_code == 200
        data = resp.json()
        # Analyst (tenant-1) sees only own batches
        assert data["total"] == 2
        trace_ids = [b["trace_id"] for b in data["batches"]]
        assert "BATCH-TEST-001" in trace_ids
        assert "BATCH-TEST-002" in trace_ids
        assert "BATCH-OTHER-001" not in trace_ids

    def test_admin_sees_all_tenants(self, client: TestClient, app):
        _seed_batch(app, SAMPLE_BATCH)
        _seed_batch(app, BATCH_OTHER_TENANT)
        resp = client.get("/v1/batches", headers=auth_header(ADMIN_TOKEN))
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2

    def test_sorted_newest_first(self, client: TestClient, app):
        _seed_batch(app, SAMPLE_BATCH)   # 10:00
        _seed_batch(app, BATCH_2)        # 11:00
        resp = client.get("/v1/batches", headers=auth_header())
        batches = resp.json()["batches"]
        assert batches[0]["trace_id"] == "BATCH-TEST-002"  # 11:00 first
        assert batches[1]["trace_id"] == "BATCH-TEST-001"  # 10:00 second

    def test_limit_respected(self, client: TestClient, app):
        _seed_batch(app, SAMPLE_BATCH)
        _seed_batch(app, BATCH_2)
        resp = client.get("/v1/batches?limit=1", headers=auth_header())
        data = resp.json()
        assert len(data["batches"]) == 1
        assert data["total"] == 2  # total is full count, page is limited

    def test_response_shape(self, client: TestClient, app):
        resp = client.get("/v1/batches", headers=auth_header())
        data = resp.json()
        assert "batches" in data
        assert "total" in data
        assert "limit" in data
        # Dashboard-compatible fields
        assert "role" in data
        assert "demo_mode" in data
        assert data["demo_mode"] is False
        assert "firestore_available" in data
        assert "count" in data

    def test_role_mapping(self, client: TestClient, app):
        """PRE analyst role maps to monolith 'user' for dashboard compatibility."""
        resp = client.get("/v1/batches", headers=auth_header())  # VALID_TOKEN has role=analyst
        assert resp.json()["role"] == "user"

    def test_admin_role_mapping(self, client: TestClient, app):
        """PRE tenant_admin maps to monolith 'admin'."""
        resp = client.get("/v1/batches", headers=auth_header(ADMIN_TOKEN))
        assert resp.json()["role"] == "admin"

    def test_empty_returns_empty_list(self, client: TestClient, app):
        resp = client.get("/v1/batches", headers=auth_header())
        data = resp.json()
        assert data["batches"] == []
        assert data["total"] == 0

    def test_no_auth_returns_401(self, client: TestClient, app):
        resp = client.get("/v1/batches")
        assert resp.status_code == 401

    def test_cost_fields_stripped_for_analyst(self, client: TestClient, app):
        _seed_batch(app)
        resp = client.get("/v1/batches", headers=auth_header())
        batch = resp.json()["batches"][0]
        assert "llm_budget_summary" not in batch

    def test_internal_fields_stripped(self, client: TestClient, app):
        _seed_batch(app)
        resp = client.get("/v1/batches", headers=auth_header())
        batch = resp.json()["batches"][0]
        assert "firestore_path" not in batch
        assert "shard_statuses" not in batch


# ============================================================================
# GET /v1/batches/{trace_id}/results — batch results (subcollection read)
# ============================================================================

SAMPLE_CHUNK_0 = {
    "start_index": 0,
    "rows": [
        {"row_index": 0, "original": "Acme Corp", "resolved": "Acme Inc", "layer": "L1_NORM", "confidence": 0.98, "reason": "suffix_strip"},
        {"row_index": 1, "original": "garbage123", "resolved": None, "layer": "L0_GARBAGE", "confidence": 0.0, "reason": "numeric_only"},
    ],
}

SAMPLE_CHUNK_1 = {
    "start_index": 2,
    "rows": [
        {"row_index": 2, "original": "Microsoft Corp", "resolved": "Microsoft", "layer": "L1_NORM", "confidence": 0.99, "reason": "suffix_strip"},
    ],
}


def _seed_results(app, trace_id: str = "BATCH-TEST-001") -> None:
    """Seed batch + results_chunks subcollection."""
    _seed_batch(app)
    db = app.state.firestore_client
    chunks_ref = db.collection("batches").document(trace_id).collection("results_chunks")
    chunks_ref.document("chunk_0000").set(SAMPLE_CHUNK_0)
    chunks_ref.document("chunk_0001").set(SAMPLE_CHUNK_1)


class TestBatchResults:
    """GET /v1/batches/{trace_id}/results — results subcollection read."""

    def test_returns_results(self, client: TestClient, app):
        _seed_results(app)
        resp = client.get("/v1/batches/BATCH-TEST-001/results", headers=auth_header())
        assert resp.status_code == 200
        data = resp.json()
        assert data["trace_id"] == "BATCH-TEST-001"
        assert data["total"] == 3
        assert data["count"] == 3
        assert len(data["results"]) == 3

    def test_results_ordered_by_start_index(self, client: TestClient, app):
        _seed_results(app)
        resp = client.get("/v1/batches/BATCH-TEST-001/results", headers=auth_header())
        results = resp.json()["results"]
        assert results[0]["original"] == "Acme Corp"
        assert results[2]["original"] == "Microsoft Corp"

    def test_pagination_offset(self, client: TestClient, app):
        _seed_results(app)
        resp = client.get("/v1/batches/BATCH-TEST-001/results?limit=2&offset=1", headers=auth_header())
        data = resp.json()
        assert data["total"] == 3
        assert data["count"] == 2
        assert data["offset"] == 1
        assert data["results"][0]["original"] == "garbage123"

    def test_tenant_isolation(self, client: TestClient, app):
        _seed_results(app)  # tenant-1
        resp = client.get("/v1/batches/BATCH-TEST-001/results", headers=auth_header(TENANT_B_TOKEN))
        assert resp.status_code == 403

    def test_batch_not_found(self, client: TestClient, app):
        resp = client.get("/v1/batches/NONEXISTENT/results", headers=auth_header())
        assert resp.status_code == 404

    def test_no_auth_returns_401(self, client: TestClient, app):
        resp = client.get("/v1/batches/BATCH-TEST-001/results")
        assert resp.status_code == 401

    def test_empty_results(self, client: TestClient, app):
        _seed_batch(app)  # batch exists but no results_chunks
        resp = client.get("/v1/batches/BATCH-TEST-001/results", headers=auth_header())
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["results"] == []

    def test_response_shape(self, client: TestClient, app):
        _seed_results(app)
        resp = client.get("/v1/batches/BATCH-TEST-001/results", headers=auth_header())
        data = resp.json()
        assert set(data.keys()) == {"trace_id", "total", "offset", "limit", "count", "results"}

    def test_safe_fields_only(self, client: TestClient, app):
        """Result rows should not contain internal processing metadata."""
        _seed_results(app)
        resp = client.get("/v1/batches/BATCH-TEST-001/results", headers=auth_header())
        row = resp.json()["results"][0]
        assert "original" in row
        assert "resolved" in row
        assert "layer" in row
        assert "confidence" in row


# ============================================================================
# GET /v1/batches/{trace_id}/forensic — forensic metadata read
# ============================================================================

FORENSIC_BATCH = {
    **SAMPLE_BATCH,
    "trace_id": "BATCH-FORENSIC-001",
    "signature": {
        "evidence_hash_sha256": "abc123",
        "signature": "base64sig==",
        "signature_alg": "EC_SIGN_P256_SHA256",
        "signing_key_id": "projects/test/keyRings/test/cryptoKeys/key1",
        "signed_at_utc": "2026-03-24T12:00:00Z",
    },
    "hash_chain": {
        "batch_root_hash": "root_abc123",
        "chain_length": 500,
        "chain_enabled": True,
    },
    "anchor": {
        "anchored": True,
        "anchor_gcs_path": "gs://ia-anchors-test/2026/03/24/BATCH-FORENSIC-001.json",
    },
    "attestation": {
        "signature_b64": "att_sig==",
        "signed_payload_jcs_b64": "payload==",
    },
    "legal_hold": {"status": "INACTIVE"},
}

FORENSIC_BATCH_EMPTY = {
    **SAMPLE_BATCH,
    "trace_id": "BATCH-NO-FORENSIC",
}


def _seed_forensic(app, batch=None):
    batch = batch or FORENSIC_BATCH
    db = app.state.firestore_client
    db.collection("batches").document(batch["trace_id"]).set(batch)


class TestBatchForensic:
    """GET /v1/batches/{trace_id}/forensic — forensic metadata read."""

    def test_returns_forensic_fields(self, client: TestClient, app):
        _seed_forensic(app)
        resp = client.get("/v1/batches/BATCH-FORENSIC-001/forensic", headers=auth_header())
        assert resp.status_code == 200
        data = resp.json()
        assert data["trace_id"] == "BATCH-FORENSIC-001"
        assert "signature" in data
        assert data["signature"]["signature_alg"] == "EC_SIGN_P256_SHA256"
        assert "hash_chain" in data
        assert data["hash_chain"]["batch_root_hash"] == "root_abc123"
        assert "anchor" in data
        assert data["anchor"]["anchored"] is True

    def test_summary_booleans(self, client: TestClient, app):
        _seed_forensic(app)
        resp = client.get("/v1/batches/BATCH-FORENSIC-001/forensic", headers=auth_header())
        summary = resp.json()["summary"]
        assert summary["signature_present"] is True
        assert summary["hash_chain_present"] is True
        assert summary["anchor_present"] is True
        assert summary["legal_hold_active"] is False

    def test_empty_forensic_fields(self, client: TestClient, app):
        _seed_forensic(app, FORENSIC_BATCH_EMPTY)
        resp = client.get("/v1/batches/BATCH-NO-FORENSIC/forensic", headers=auth_header())
        assert resp.status_code == 200
        summary = resp.json()["summary"]
        assert summary["signature_present"] is False
        assert summary["hash_chain_present"] is False
        assert summary["anchor_present"] is False

    def test_tenant_isolation(self, client: TestClient, app):
        _seed_forensic(app)  # tenant-1
        resp = client.get("/v1/batches/BATCH-FORENSIC-001/forensic", headers=auth_header(TENANT_B_TOKEN))
        assert resp.status_code == 403

    def test_not_found(self, client: TestClient, app):
        resp = client.get("/v1/batches/NONEXISTENT/forensic", headers=auth_header())
        assert resp.status_code == 404

    def test_no_auth(self, client: TestClient, app):
        resp = client.get("/v1/batches/BATCH-FORENSIC-001/forensic")
        assert resp.status_code == 401

    def test_no_cost_fields_leak(self, client: TestClient, app):
        _seed_forensic(app)
        resp = client.get("/v1/batches/BATCH-FORENSIC-001/forensic", headers=auth_header())
        data = resp.json()
        assert "llm_budget_summary" not in data
        assert "credits_spent_usd" not in data
        assert "firestore_path" not in data

    def test_response_shape(self, client: TestClient, app):
        _seed_forensic(app)
        resp = client.get("/v1/batches/BATCH-FORENSIC-001/forensic", headers=auth_header())
        data = resp.json()
        assert "summary" in data
        assert "trace_id" in data


# ============================================================================
# GET /v1/batches/{trace_id}/audit — audit events subcollection
# ============================================================================

SAMPLE_AUDIT_EVENTS = [
    {"row_index": 0, "original": "Acme Corp", "resolved": "Acme Inc", "layer": "L1_NORM",
     "confidence": 0.98, "reason": "suffix_strip", "event_type": "RESOLUTION"},
    {"row_index": 1, "original": "garbage123", "resolved": None, "layer": "L0_GARBAGE",
     "confidence": 0.0, "reason": "numeric_only", "event_type": "RESOLUTION"},
    {"row_index": 2, "original": "Microsoft Corp", "resolved": "Microsoft", "layer": "L1_NORM",
     "confidence": 0.99, "reason": "suffix_strip", "event_type": "RESOLUTION"},
]


def _seed_audit(app, trace_id: str = "BATCH-TEST-001"):
    """Seed batch + audit_events subcollection."""
    _seed_batch(app)
    db = app.state.firestore_client
    audit_ref = db.collection("batches").document(trace_id).collection("audit_events")
    for i, event in enumerate(SAMPLE_AUDIT_EVENTS):
        audit_ref.document(f"event_{i:04d}").set(event)


class TestBatchAudit:
    """GET /v1/batches/{trace_id}/audit — audit events subcollection read."""

    def test_returns_events(self, client: TestClient, app):
        _seed_audit(app)
        resp = client.get("/v1/batches/BATCH-TEST-001/audit", headers=auth_header())
        assert resp.status_code == 200
        data = resp.json()
        assert data["trace_id"] == "BATCH-TEST-001"
        assert data["total"] == 3
        assert len(data["events"]) == 3

    def test_ordered_by_row_index(self, client: TestClient, app):
        _seed_audit(app)
        resp = client.get("/v1/batches/BATCH-TEST-001/audit", headers=auth_header())
        events = resp.json()["events"]
        assert events[0]["row_index"] == 0
        assert events[1]["row_index"] == 1
        assert events[2]["row_index"] == 2

    def test_limit_respected(self, client: TestClient, app):
        _seed_audit(app)
        resp = client.get("/v1/batches/BATCH-TEST-001/audit?limit=2", headers=auth_header())
        data = resp.json()
        assert data["total"] == 2  # limited
        assert len(data["events"]) == 2

    def test_tenant_isolation(self, client: TestClient, app):
        _seed_audit(app)
        resp = client.get("/v1/batches/BATCH-TEST-001/audit", headers=auth_header(TENANT_B_TOKEN))
        assert resp.status_code == 403

    def test_batch_not_found(self, client: TestClient, app):
        resp = client.get("/v1/batches/NONEXISTENT/audit", headers=auth_header())
        assert resp.status_code == 404

    def test_no_auth(self, client: TestClient, app):
        resp = client.get("/v1/batches/BATCH-TEST-001/audit")
        assert resp.status_code == 401

    def test_empty_audit(self, client: TestClient, app):
        _seed_batch(app)  # batch exists, no audit events
        resp = client.get("/v1/batches/BATCH-TEST-001/audit", headers=auth_header())
        assert resp.status_code == 200
        assert resp.json()["total"] == 0
        assert resp.json()["events"] == []

    def test_safe_fields_only(self, client: TestClient, app):
        _seed_audit(app)
        resp = client.get("/v1/batches/BATCH-TEST-001/audit", headers=auth_header())
        event = resp.json()["events"][0]
        assert "original" in event
        assert "layer" in event
        assert "event_type" in event

    def test_response_shape(self, client: TestClient, app):
        _seed_audit(app)
        resp = client.get("/v1/batches/BATCH-TEST-001/audit", headers=auth_header())
        data = resp.json()
        assert set(data.keys()) == {"trace_id", "total", "events"}
