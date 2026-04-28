"""Integration test: full auth flow with mock IdP."""

from apps.api.tests.conftest import (
    EXPIRED_TOKEN, INVALID_TOKEN, VALID_TOKEN, auth_header,
)


class TestAuthFlow:
    def test_valid_token_full_flow(self, client):
        resp = client.post(
            "/v1/resolve",
            json={"document_id": "d1", "document_type": "regulatory", "content": "test"},
            headers={**auth_header(VALID_TOKEN), "Idempotency-Key": "auth-flow-1"},
        )
        assert resp.status_code == 200

    def test_expired_token_rejected(self, client):
        resp = client.post(
            "/v1/resolve", json={},
            headers=auth_header(EXPIRED_TOKEN),
        )
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "TOKEN_EXPIRED"

    def test_invalid_signature_rejected(self, client):
        resp = client.post("/v1/resolve", json={}, headers=auth_header(INVALID_TOKEN))
        assert resp.status_code == 401

    def test_error_response_format(self, client):
        resp = client.post("/v1/resolve", json={})
        assert resp.status_code == 401
        error = resp.json()["error"]
        assert "code" in error
        assert "message" in error
        assert "correlation_id" in error
        assert "retry" in error
