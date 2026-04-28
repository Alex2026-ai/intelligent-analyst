"""Integration test: submit → resolve → check response shape."""

from apps.api.tests.conftest import VALID_TOKEN, auth_header


class TestFullResolutionFlow:
    def test_submit_and_resolve(self, client):
        resp = client.post(
            "/v1/resolve",
            json={
                "document_id": "550e8400-e29b-41d4-a716-446655440000",
                "document_type": "regulatory",
                "content": "OFAC sanctions violation detected.",
            },
            headers={**auth_header(), "Idempotency-Key": "integ-1"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "resolution_id" in data
        assert "evidence_chain_id" in data
        assert data["created_at"]

    def test_correlation_id_in_response(self, client):
        resp = client.post(
            "/v1/resolve",
            json={"document_id": "d1", "document_type": "regulatory", "content": "test"},
            headers={
                **auth_header(),
                "Idempotency-Key": "integ-2",
                "X-Correlation-Id": "trace-custom",
            },
        )
        assert resp.headers.get("X-Correlation-Id") == "trace-custom"

    def test_auto_correlation_id(self, client):
        resp = client.get("/health/live")
        assert "X-Correlation-Id" in resp.headers
