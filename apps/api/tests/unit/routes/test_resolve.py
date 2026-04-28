"""Tests for resolution endpoints."""

from apps.api.tests.conftest import (
    ADMIN_TOKEN, REVIEWER_TOKEN, VALID_TOKEN, auth_header,
)


class TestResolveSingle:
    def test_valid_resolution(self, client):
        resp = client.post(
            "/v1/resolve",
            json={
                "document_id": "550e8400-e29b-41d4-a716-446655440000",
                "document_type": "regulatory",
                "content": "Test document content",
            },
            headers={**auth_header(), "Idempotency-Key": "test-key-1"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "resolution_id" in data
        assert "evidence_chain_id" in data
        assert data["status"] in ("resolved", "routed_to_review")

    def test_missing_idempotency_key(self, client):
        resp = client.post(
            "/v1/resolve",
            json={"document_id": "d1", "document_type": "regulatory", "content": "test"},
            headers=auth_header(),
        )
        assert resp.status_code == 400

    def test_idempotency_returns_same_result(self, client):
        headers = {**auth_header(), "Idempotency-Key": "idem-1"}
        body = {"document_id": "d1", "document_type": "regulatory", "content": "test"}
        r1 = client.post("/v1/resolve", json=body, headers=headers)
        r2 = client.post("/v1/resolve", json=body, headers=headers)
        assert r1.json()["resolution_id"] == r2.json()["resolution_id"]

    def test_missing_required_field(self, client):
        resp = client.post(
            "/v1/resolve",
            json={"document_type": "regulatory"},
            headers={**auth_header(), "Idempotency-Key": "k2"},
        )
        assert resp.status_code == 400

    def test_invalid_document_type(self, client):
        resp = client.post(
            "/v1/resolve",
            json={"document_id": "d1", "document_type": "unknown", "content": "test"},
            headers={**auth_header(), "Idempotency-Key": "k3"},
        )
        assert resp.status_code == 400

    def test_requires_auth(self, client):
        resp = client.post("/v1/resolve", json={})
        assert resp.status_code == 401


class TestResolveBatch:
    def test_valid_batch(self, client):
        resp = client.post(
            "/v1/resolve/batch",
            json={
                "documents": [
                    {"document_id": "d1", "document_type": "regulatory", "content": "test1"},
                    {"document_id": "d2", "document_type": "financial", "content": "test2"},
                ],
            },
            headers={**auth_header(), "Idempotency-Key": "batch-1"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["results"]) == 2

    def test_empty_batch_rejected(self, client):
        resp = client.post(
            "/v1/resolve/batch",
            json={"documents": []},
            headers={**auth_header(), "Idempotency-Key": "batch-empty"},
        )
        assert resp.status_code == 400

    def test_batch_exceeds_max(self, client):
        docs = [{"document_id": f"d{i}", "document_type": "regulatory", "content": "t"} for i in range(101)]
        resp = client.post(
            "/v1/resolve/batch",
            json={"documents": docs},
            headers={**auth_header(), "Idempotency-Key": "batch-big"},
        )
        assert resp.status_code == 400
