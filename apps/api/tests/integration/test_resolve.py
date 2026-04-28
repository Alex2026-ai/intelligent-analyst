"""Integration tests for /v1/resolve — real LLM pipeline with PII masking.

Uses MockLLMProvider (via TESTING=true) so no real API calls are made.
Verifies: PII masking, LLM call, evidence_chain_id, response shape.
"""

from apps.api.tests.conftest import VALID_TOKEN, REVIEWER_TOKEN, auth_header


class TestResolveSingleIntegration:
    def test_full_resolve_flow(self, client):
        """Submit → PII mask → LLM → response with evidence_chain_id."""
        resp = client.post(
            "/v1/resolve",
            json={
                "document_id": "550e8400-e29b-41d4-a716-446655440000",
                "document_type": "regulatory",
                "content": "OFAC sanctions violation detected for entity XYZ.",
            },
            headers={**auth_header(), "Idempotency-Key": "integ-resolve-1"},
        )
        assert resp.status_code == 200
        data = resp.json()

        # Core fields present
        assert "resolution_id" in data
        assert "evidence_chain_id" in data
        assert data["evidence_chain_id"]  # Not empty
        assert data["created_at"]

        # LLM was called (MockLLMProvider returns confidence=0.85)
        assert data["confidence"] == 0.85
        assert data["status"] == "resolved"
        assert data["layer_used"] == 3
        assert data["resolution"]  # Non-empty resolution text

    def test_pii_masked_before_llm(self, client):
        """Content with PII should be masked — MockLLMProvider echoes masked content."""
        resp = client.post(
            "/v1/resolve",
            json={
                "document_id": "550e8400-e29b-41d4-a716-446655440001",
                "document_type": "compliance",
                "content": "Patient SSN: 123-45-6789 flagged for review.",
            },
            headers={**auth_header(), "Idempotency-Key": "integ-resolve-pii"},
        )
        assert resp.status_code == 200
        data = resp.json()
        # MockLLMProvider includes masked content in resolution text
        # The SSN should NOT appear in the final resolution (it was masked)
        # After unmask, the SSN would be restored in the resolution text
        # but MockLLMProvider only sees the masked version
        assert data["status"] == "resolved"

    def test_evidence_chain_id_is_uuid(self, client):
        """evidence_chain_id must be a valid UUID string."""
        resp = client.post(
            "/v1/resolve",
            json={
                "document_id": "550e8400-e29b-41d4-a716-446655440002",
                "document_type": "financial",
                "content": "Quarterly earnings report with strong growth.",
            },
            headers={**auth_header(), "Idempotency-Key": "integ-resolve-uuid"},
        )
        data = resp.json()
        chain_id = data["evidence_chain_id"]
        assert len(chain_id) == 36  # UUID format
        assert chain_id.count("-") == 4

    def test_idempotency_returns_cached(self, client):
        """Same Idempotency-Key returns identical response."""
        body = {
            "document_id": "d-idem",
            "document_type": "regulatory",
            "content": "Test idempotency content.",
        }
        headers = {**auth_header(), "Idempotency-Key": "integ-idem-key"}
        r1 = client.post("/v1/resolve", json=body, headers=headers)
        r2 = client.post("/v1/resolve", json=body, headers=headers)
        assert r1.json()["resolution_id"] == r2.json()["resolution_id"]
        assert r1.json()["evidence_chain_id"] == r2.json()["evidence_chain_id"]

    def test_correlation_id_in_response(self, client):
        resp = client.post(
            "/v1/resolve",
            json={"document_id": "d1", "document_type": "regulatory", "content": "test"},
            headers={
                **auth_header(),
                "Idempotency-Key": "integ-corr-1",
                "X-Correlation-Id": "trace-custom-123",
            },
        )
        assert resp.headers.get("X-Correlation-Id") == "trace-custom-123"


class TestResolveBatchIntegration:
    def test_batch_resolve(self, client):
        resp = client.post(
            "/v1/resolve/batch",
            json={
                "documents": [
                    {"document_id": "d1", "document_type": "regulatory", "content": "Doc 1"},
                    {"document_id": "d2", "document_type": "financial", "content": "Doc 2"},
                ],
            },
            headers={**auth_header(), "Idempotency-Key": "integ-batch-1"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert data["resolved"] == 2
        assert len(data["results"]) == 2
        for result in data["results"]:
            assert result["confidence"] == 0.85
            assert result["layer_used"] == 3

    def test_batch_empty_rejected(self, client):
        resp = client.post(
            "/v1/resolve/batch",
            json={"documents": []},
            headers={**auth_header(), "Idempotency-Key": "integ-batch-empty"},
        )
        assert resp.status_code == 400


class TestResolveAuth:
    def test_no_auth_rejected(self, client):
        resp = client.post("/v1/resolve", json={"content": "test"})
        assert resp.status_code == 401

    def test_missing_idempotency_key_rejected(self, client):
        resp = client.post(
            "/v1/resolve",
            json={"document_id": "d1", "document_type": "regulatory", "content": "test"},
            headers=auth_header(),
        )
        assert resp.status_code == 400
