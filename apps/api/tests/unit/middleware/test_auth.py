"""Tests for authentication middleware."""

from apps.api.tests.conftest import (
    ADMIN_TOKEN, EXPIRED_TOKEN, INVALID_TOKEN, MISSING_CLAIMS_TOKEN,
    REVIEWER_TOKEN, VALID_TOKEN, auth_header,
)


class TestAuthRequired:
    def test_no_auth_header_returns_401(self, client):
        resp = client.post("/v1/resolve", json={"content": "test"})
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"

    def test_invalid_token_returns_401(self, client):
        resp = client.post("/v1/resolve", json={}, headers=auth_header(INVALID_TOKEN))
        assert resp.status_code == 401

    def test_expired_token_returns_401(self, client):
        resp = client.post("/v1/resolve", json={}, headers=auth_header(EXPIRED_TOKEN))
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "TOKEN_EXPIRED"

    def test_missing_claims_returns_401(self, client):
        resp = client.post("/v1/resolve", json={}, headers=auth_header(MISSING_CLAIMS_TOKEN))
        assert resp.status_code == 401

    def test_valid_token_passes(self, client):
        resp = client.post(
            "/v1/resolve",
            json={
                "document_id": "550e8400-e29b-41d4-a716-446655440000",
                "document_type": "regulatory",
                "content": "test content",
            },
            headers={**auth_header(VALID_TOKEN), "Idempotency-Key": "k1"},
        )
        assert resp.status_code == 200

    def test_malformed_auth_header(self, client):
        resp = client.post("/v1/resolve", json={}, headers={"Authorization": "Basic abc"})
        assert resp.status_code == 401


class TestHealthProbesSkipAuth:
    def test_liveness_no_auth(self, client):
        resp = client.get("/health/live")
        assert resp.status_code == 200

    def test_startup_no_auth(self, client):
        resp = client.get("/health/startup")
        assert resp.status_code == 200

    def test_ready_no_auth(self, client):
        resp = client.get("/health/ready")
        assert resp.status_code == 200
